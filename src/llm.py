import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from groq import APIConnectionError, APIStatusError, BadRequestError, Groq, RateLimitError
from pydantic import ValidationError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_chain
from tenacity.wait import wait_fixed

from src.aliases import post_process_acta
from src.parser import count_detalles_blocks
from src.schemas import ActaSchema

load_dotenv()

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an assistant that turns meeting notes into one JSON meeting acta aligned with Gorila-style minutes.

LANGUAGE
- Prefer Spanish for all textual values (titulo, cliente, objetivo, asuntos descriptions, compromisos, cierre).

OUTPUT FORMAT
- Respond ONLY with valid JSON. No markdown, no backticks/fences, no preamble, no explanation.
- Populate every schema key listed below — never omit a key.
- EVERY compromiso object MUST include fecha_entrega. Use prose like "viernes 23 de mayo de 2026" when explicit;
  otherwise exactly "No especificada".
- NOTE: If the user message says Próximos pasos were parsed deterministically, focus on objetivo, asuntos_tratados
  and cierre; compromisos in your JSON may be overwritten by post-processing.

SOURCE PRIORITY
1. NOTAS COMPLETAS DE LA REUNIÓN — authoritative for cliente/título efectivo de la reunión,
   coverage temática completa y síntesis de compromisos.
2. METADATA EXTRAÍDO — preferred for fecha literal and horas de calendario when present/coherent.
3. Nombre del archivo de origen — **último recurso solo** si el cliente/título jamás aparece en notas/metadata.

MAPPING (Spanish acta headings → JSON)
- **Título de la reunión** → titulo — nombre corto de la reunión o temática, DERIVADO del título/tema real que aparezca en
  las NOTAS o el METADATA. Cualquier ejemplo de formato (p. ej. una temática genérica de seguimiento o de revisión de avances)
  es solo ilustrativo del estilo; NUNCA lo copies literalmente como salida.
  NO incluyas aquí el nombre de la cuenta/cliente; eso va en ``cliente``.
- **Fecha, hora_inicio y hora_fin** — METADATA primera; fallback a menciones claras del cuerpo; "No especificada" solo si tras ambas fuentes no hay evidencia.
- **Lugar / enlace** → lugar — Google Meet / Zoom / oficina, etc.; "No especificada" cuando falte.
- **Cliente (cuenta)** → cliente — solo el nombre de la cuenta o marca del cliente, EXTRAÍDO de las NOTAS/METADATA (o del
  nombre de archivo como último recurso). NUNCA inventes ni copies un nombre de cuenta de ejemplo: usa el cliente real de la reunión.
  Preserve "&" verbatim. NO repitas el nombre de la reunión en ``cliente`` si ya va en ``titulo``; el documento los combina.
  NO inventes prefijos desde el archivo si las notas traen otro cliente.
- **Objetivo** → objetivo — empieza con **verbo en infinitivo** (ej. «Definir…», «Revisar…»); 1 a 3 oraciones sobre el porqué y el alcance.
- **Asuntos tratados** → asuntos_tratados[]
  CRITICAL: Usa EXCLUSIVAMENTE la sección **Detalles** como fuente de asuntos_tratados.
  NUNCA generes asuntos a partir del bloque «Resumen» breve que aparece antes de Próximos pasos
  (el Resumen es solo un eco condensado de lo que ya está en Detalles; incluirlo genera duplicados).
  Si el mensaje de usuario indica ``DETALLES: N bloques detectados``, produce **entre N y N+2 asuntos**
  (máximo 8 salvo que Detalles tenga más de 8 bloques explícitos).
  Un tema que aparezca en el Resumen Y en Detalles cuenta UNA sola vez, tomado de Detalles.
  Incluye **nombres propios** en la descripción cuando las notas los mencionen (no los borres).
  Por ítem:
  • titulo — encabezado corto SIN número. El documento añade la numeración automáticamente; NUNCA incluyas "1.", "2.", etc. al inicio.
  • descripcion — párrafos desarrollados (2 a 6 oraciones) con decisiones, plataformas, problemas mencionados, acuerdos y matices.

- **Compromisos asumidos por Gorila** → compromisos_gorila[]
  • **Regla fija de cartera**: ``compromisos_gorila`` es SIEMPRE para **equipos internos Gorila Hosting / Growfik**
    (Marketing Gorila Hosting, personal @growfik.com, analistas Growfik, etc.).
    **Growfik es marca del equipo Gorila; NUNCA asignes tareas Growfik/Gorila al cliente.**
    ``compromisos_cliente`` es para la **cuenta/cliente** de la reunión.
  • Cuando las notas usan `[Nombre] Tarea: descripción`, clasifica por quién ejecuta:
    - Etiquetas/equipos **Gorila Hosting** o personal interno Growfik/Gorila → compromisos_gorila.
    - Personas claramente del **cliente** → compromisos_cliente; ``responsable`` = **empresa/cuenta**, NO la persona.
    - "[El grupo]" / "[Todos]" → **solo** ``compromisos_gorila``.
  • NUNCA inventes compromisos que no estén explícitamente mencionados en las notas.
- **Compromisos cliente** → compromisos_cliente[] — mismas reglas de atribución.
- **Cierre** → cierre — 2–4 oraciones que DEBEN incluir cuando aparezcan en las notas:
  (1) principales acuerdos y sensación de avance;
  (2) próxima reunión o touchpoint con **fecha/hora** si está en Próximos pasos;
  (3) personas mencionadas con **apellido y rol/empresa** (no dejar "Pedro" sin contexto).

## fecha / hora_inicio / hora_fin (technical rules)
- Use METADATA as **priority** for fecha, hora_inicio, hora_fin when values appear there coherently.
- Always express fecha JSON as Spanish prose, e.g. "29 de abril de 2026" — NOT English variants like "Apr 29, 2026".
- Normalize horas a reloj 12 h tipo "H:MM AM"/"HH:MM PM".
- If still unknown definitivamente, output literally "No especificada".

## invitados (strict shape)
Each item must be exactly: {"correo": string, "puesto": string, "asistencia": string}
- Devuelve **[]** (lista vacía). El sistema rellena invitados después.

## compromisos (shape + tagging)
Each item MUST be: {"tarea": string, "responsable": string, "fecha_entrega": string}
- Personal interno Growfik/Gorila (incl. @growfik.com) → compromisos_gorila con nombre o equipo interno.
- Persona del **cliente** → compromisos_cliente; ``responsable`` = **empresa/cuenta**, no la persona.
- **``[El grupo]`` / ``[Todos]``** → solo ``compromisos_gorila``.

## Final JSON schema (exact keys / nesting)

{
  "titulo": string,
  "fecha": string,
  "hora_inicio": string,
  "hora_fin": string,
  "lugar": string,
  "cliente": string,
  "objetivo": string,
  "cierre": string,
  "invitados": [{"correo": string, "puesto": string, "asistencia": string}],
  "asuntos_tratados": [{"titulo": string, "descripcion": string}],
  "compromisos_gorila": [{"tarea": string, "responsable": string, "fecha_entrega": string}],
  "compromisos_cliente": [{"tarea": string, "responsable": string, "fecha_entrega": string}]
}

Technical hygiene: NEVER fabricate timestamps like "00:00:00". Keep JSON strings UTF-8 without control characters breaking JSON.
"""

# Salida JSON. En tier Groq on_demand el límite (TPD) aplica a prompt + max_tokens de la petición:
# Groq reserva los max_tokens COMPLETOS al contar la cuota, así que sobre-reservar la agota al doble.
# Un acta JSON real ocupa ~1.5k–2.5k tokens; 4096 deja margen amplio. Configurable por entorno.
_MAX_COMPLETION_TOKENS = int(os.getenv("ACTA_MAX_COMPLETION_TOKENS", "4096"))
_GROQ_REQUEST_TOKEN_CEILING = 11_500

_MODEL = "llama-3.3-70b-versatile"
_CHARS_PER_TOKEN = 4

# Caché en disco del JSON crudo del modelo. Reprocesar las mismas notas (arreglos deterministas de
# hora/Growfik/plantilla) reusa la extracción del LLM y cuesta 0 tokens (ni siquiera requiere API key).
# Desactiva con ACTA_LLM_CACHE=0. La clave incluye prompt + modelo + max_tokens: si cambian, se invalida.
_CACHE_ENABLED = os.getenv("ACTA_LLM_CACHE", "1") not in ("0", "false", "False", "")
_CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "llm"

_PROXIMOS_SECTION_RE = re.compile(
    r"(?is)(próximos\s+pasos\s*.*?)(?=^\s*detalles\s*$|\Z)",
    re.MULTILINE,
)
_DETALLES_SECTION_RE = re.compile(r"(?is)(detalles\s*.*)\Z")


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _llm_cache_key(system_prompt: str, user_body: str) -> str:
    """Hash de todo lo que determina la salida del modelo (prompt, notas, modelo, max_tokens)."""
    h = hashlib.sha256()
    for part in (_MODEL, str(_MAX_COMPLETION_TOKENS), system_prompt, user_body):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _cache_get(key: str) -> dict[str, Any] | None:
    if not _CACHE_ENABLED:
        return None
    try:
        return json.loads((_CACHE_DIR / f"{key}.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _cache_set(key: str, data: dict[str, Any]) -> None:
    if not _CACHE_ENABLED:
        return
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (_CACHE_DIR / f"{key}.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as e:
        logger.warning("No se pudo escribir caché LLM (%s): %s", key[:12], e)


def _trim_to_budget(raw_text: str, budget_tokens: int) -> str:
    """
    Trunca preservando siempre Próximos pasos + Detalles completos;
    recorta el prefijo (resumen/cabecera) si hace falta.
    """
    if _estimate_tokens(raw_text) <= budget_tokens:
        return raw_text

    budget_chars = budget_tokens * _CHARS_PER_TOKEN
    prox_m = _PROXIMOS_SECTION_RE.search(raw_text)
    det_m = _DETALLES_SECTION_RE.search(raw_text)
    prox = prox_m.group(1).strip() if prox_m else ""
    det = det_m.group(1).strip() if det_m else ""
    protected = "\n\n".join(part for part in (prox, det) if part)

    if protected and len(protected) <= budget_chars:
        prefix_end = prox_m.start() if prox_m else (det_m.start() if det_m else len(raw_text))
        prefix = raw_text[:prefix_end].strip()
        room = budget_chars - len(protected) - 80
        if room > 0 and prefix:
            if len(prefix) > room:
                head = prefix[: room * 65 // 100].rstrip()
                tail = prefix[-(room - len(head)) :].lstrip()
                prefix = head + "\n\n[... contenido inicial omitido ...]\n\n" + tail
        elif not prefix:
            prefix = ""
        result = "\n\n".join(part for part in (prefix, protected) if part)
        logger.warning(
            "raw_text truncado (secciones protegidas): %d chars → %d chars",
            len(raw_text),
            len(result),
        )
        return result

    if _estimate_tokens(protected) > budget_tokens and det and len(det) > budget_chars // 2:
        head_det = det[: budget_chars * 65 // 100]
        tail_det = det[-(budget_chars * 35 // 100) :]
        protected = head_det + "\n\n[... detalles omitidos ...]\n\n" + tail_det
        logger.warning("raw_text truncado (solo Detalles): %d → %d chars", len(raw_text), len(protected))
        return protected

    head = budget_chars * 65 // 100
    tail = budget_chars - head
    logger.warning(
        "raw_text truncado head/tail: %d chars → %d chars (budget %d tokens)",
        len(raw_text),
        head + tail,
        budget_tokens,
    )
    return (
        raw_text[:head]
        + "\n\n[... contenido central omitido por límite de tokens ...]\n\n"
        + raw_text[-tail:]
    )


def _first_balanced_json_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _strip_markdown_fences(s: str) -> str:
    t = s.strip()
    if not (t.startswith("```") and t.endswith("```")):
        return t
    inner = t[:-3].rstrip()
    if inner.startswith("```json"):
        return inner[7:].lstrip().rstrip()
    if inner.startswith("```"):
        return inner[3:].lstrip().rstrip()
    return t


def _extract_json(raw: str) -> dict[str, Any]:
    s = (raw or "").strip()
    candidate = _strip_markdown_fences(s)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    for blob in (
        _first_balanced_json_object(candidate),
        _first_balanced_json_object(s),
    ):
        if blob:
            try:
                return json.loads(blob)
            except json.JSONDecodeError:
                continue
    raise ValueError(raw)


def parse_json_blob(raw: str) -> dict[str, Any]:
    """Best-effort parse of a model string into JSON (jueces, herramientas)."""
    return _extract_json(raw)


class _LastRaw:
    __slots__ = ("value",)

    def __init__(self) -> None:
        self.value = ""


def _before_sleep_log(retry_state: Any) -> None:
    holder = retry_state.kwargs.get("last_raw_holder")
    raw = holder.value if holder else ""
    logger.warning(
        "Groq parse attempt failed (model=%s, raw_len=%s, raw_preview=%r)",
        _MODEL,
        len(raw),
        raw[:200],
    )


def _should_retry(exc: BaseException) -> bool:
    return isinstance(exc, (ValueError, RateLimitError, APIConnectionError))


@retry(
    retry=retry_if_exception(_should_retry),
    stop=stop_after_attempt(3),
    wait=wait_chain(wait_fixed(1), wait_fixed(2)),
    before_sleep=_before_sleep_log,
    reraise=True,
)
def _chat_completion_parse(
    client: Groq,
    messages: list[dict[str, str]],
    *,
    last_raw_holder: _LastRaw,
) -> dict[str, Any]:
    try:
        response = client.chat.completions.create(
            model=_MODEL,
            temperature=0.2,
            max_tokens=_MAX_COMPLETION_TOKENS,
            messages=messages,
            response_format={"type": "json_object"},
        )
    except (BadRequestError, APIStatusError):
        raise
    raw = response.choices[0].message.content or ""
    last_raw_holder.value = raw
    return _extract_json(raw)


def _schema_retry_errors(exc: ValidationError) -> str:
    return json.dumps(exc.errors(), ensure_ascii=False)


def _validated_and_post_process(
    data: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validated = ActaSchema.model_validate(data).model_dump()
    return post_process_acta(validated, metadata=metadata)


def structure_meeting(
    raw_text: str,
    metadata: dict | None = None,
    source_filename: str | None = None,
) -> dict:
    md = metadata or {}
    attendees = md.get("attendees") or []
    att_join = ", ".join(attendees) if attendees else "(ninguno detectado)"
    teams = md.get("gorila_teams") or []
    teams_m = ", ".join(teams) if teams else "(ninguno detectado)"
    fecha_m = md.get("date") or "(no detectada)"
    hi_m = md.get("hora_inicio") or "(no detectada)"
    hf_m = md.get("hora_fin") or "(no detectada)"
    det_chars, det_blocks = count_detalles_blocks(raw_text)

    meta_block = (
        "METADATA EXTRAÍDO DEL DOCUMENTO:\n"
        f"Fecha: {fecha_m}\n"
        f"Hora inicio detectada: {hi_m}\n"
        f"Hora fin detectada: {hf_m}\n"
        f"Invitados (correos detectados): {att_join}\n"
        f"Equipos Gorila detectados en invitación: {teams_m}\n"
        f"DETALLES: ~{det_chars} caracteres, {det_blocks} bloques/temas detectados "
        f"(genera entre {det_blocks} y {det_blocks + 2} asuntos_tratados, SOLO desde Detalles).\n"
    )
    if md.get("is_virtual"):
        meta_block += "Lugar detectado: Google Meet (reunión virtual con grabación).\n"
    if re.search(r"(?is)próximos\s+pasos", raw_text):
        meta_block += (
            "Próximos pasos detectados en notas: el post-proceso puede sobrescribir "
            "compromisos_gorila/compromisos_cliente de forma determinística.\n"
        )
    if md.get("calendar_url"):
        meta_block += f"URL calendario: {md['calendar_url']}\n"

    head = meta_block + "\nNOTAS COMPLETAS DE LA REUNIÓN:\n"
    tail = ""
    if source_filename:
        tail = (
            "\n\n---\nNombre del archivo de origen: "
            f"{source_filename}\n"
            "(Último recurso para cliente si no aparece en notas. METADATA tiene prioridad para fecha/horas.)\n"
        )

    prompt_prefix_tokens = (
        _estimate_tokens(_SYSTEM_PROMPT)
        + _estimate_tokens(head)
        + _estimate_tokens(tail)
        + 120
    )
    raw_budget = max(
        512,
        _GROQ_REQUEST_TOKEN_CEILING - _MAX_COMPLETION_TOKENS - prompt_prefix_tokens,
    )
    raw_text = _trim_to_budget(raw_text, raw_budget)

    user_body = head + raw_text + tail

    cache_key = _llm_cache_key(_SYSTEM_PROMPT, user_body)
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info("LLM cache hit (%s): se omite la llamada a Groq", cache_key[:12])
        return _validated_and_post_process(cached, metadata=md)

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_body},
    ]

    holder = _LastRaw()
    data = _chat_completion_parse(client, messages, last_raw_holder=holder)

    try:
        result = _validated_and_post_process(data, metadata=md)
    except ValidationError as ve:
        fix_messages: list[dict[str, str]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "system",
                "content": (
                    "Tu respuesta anterior tenía estos errores de schema: "
                    f"{_schema_retry_errors(ve)}. Devuelve SOLO el JSON corregido."
                ),
            },
            {"role": "user", "content": user_body},
        ]
        holder2 = _LastRaw()
        data = _chat_completion_parse(client, fix_messages, last_raw_holder=holder2)
        result = _validated_and_post_process(data, metadata=md)

    # Solo cacheamos el JSON del modelo que ya validó (post-proceso se re-aplica en cada lectura).
    _cache_set(cache_key, data)
    return result
