import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from groq import APIConnectionError, APIStatusError, BadRequestError, Groq, RateLimitError
from pydantic import ValidationError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_chain
from tenacity.wait import wait_fixed

from src.aliases import post_process_acta
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

SOURCE PRIORITY
1. NOTAS COMPLETAS DE LA REUNIÓN — authoritative for cliente/título efectivo de la reunión, roles de asistentes,
   coverage temática completa y síntesis de compromisos.
2. METADATA EXTRAÍDO — preferred for fecha literal and horas de calendario when present/coherent.
3. Nombre del archivo de origen — **último recurso solo** si el cliente/título jamás aparece en notas/metadata.

MAPPING (Spanish acta headings → JSON)
- **Título de la reunión** → titulo — nombre corto de la reunión o temática (ej. "Revisión Pauta", "Seguimiento mensual").
  NO incluyas aquí el nombre de la cuenta/cliente; eso va en ``cliente``.
- **Fecha, hora_inicio y hora_fin** — METADATA primera; fallback a menciones claras del cuerpo; "No especificada" solo si tras ambas fuentes no hay evidencia.
- **Lugar / enlace** → lugar — Google Meet / Zoom / oficina, etc.; "No especificada" cuando falte.
- **Cliente (cuenta)** → cliente — solo el nombre de la cuenta o marca del cliente (ej. "Real State", "Eventos & Matrimonios", "Universal").
  Preserve "&" verbatim. NO repitas el nombre de la reunión en ``cliente`` si ya va en ``titulo``; el documento los combina.
  NO inventes prefijos desde el archivo si las notas traen otro cliente.
- **Objetivo** → objetivo — empieza con **verbo en infinitivo** (ej. «Definir…», «Revisar…»); 1 a 3 oraciones sobre el porqué y el alcance.
- **Asuntos tratados** → asuntos_tratados[]
  CRITICAL: Ancla los temas en la sección **Detalles** (o cuerpo equivalente) de las notas. NO repitas como asunto aparte un bullet que sea solo eco del **Resumen** si el mismo matiz ya está desarrollado en **Detalles**.
  Lista **cada tema sustantivo diferente** que aparezca en **Detalles**; cuando las notas usan líneas tipo «Tema: párrafo», un asunto por bloque con título breve coherente con el primer sustantivo.
  Incluye **nombres propios** en la descripción cuando las notas los mencionen (no los borres).
  Por ítem:
  • titulo — encabezado corto SIN número (ej. “Revisión técnica de reportes”, “Migración a Power BI”). El documento añade la numeración automáticamente; NUNCA incluyas “1.”, “2.”, etc. al inicio.
  • descripcion — párrafos desarrollados (2 a 6 oraciones) con decisiones, plataformas, problemas mencionados, acuerdos y matices; evita telegramas sin contexto.

- **Compromisos asumidos por Gorila** → compromisos_gorila[]
  • La sección “Próximos pasos” de las notas es la FUENTE PRIMARIA para compromisos. NO omitas ningún ítem de esa sección.
  • **Regla fija de cartera**: ``compromisos_gorila`` es SIEMPRE para **Gorila Hosting / Growfik** (equipos internos:
    Marketing Gorila Hosting, Administración Gorila Hosting, Social Media Gorila Hosting, etc.).
    ``compromisos_cliente`` es para la **cuenta/cliente** de la reunión (personas del cliente, consultores del cliente,
    responsables externos que NO son equipos Gorila).
  • Cuando las notas usan `[Nombre] Tarea: descripción`, clasifica por quién ejecuta:
    - Etiquetas/equipos con “Gorila Hosting” o “Growfik” → compromisos_gorila; ``responsable`` = etiqueta del equipo.
    - Nombres de personas del lado del cliente (propietarios, directores, consultores del cliente) → compromisos_cliente.
    - Si el responsable es “[El grupo]” o “[Todos]” → **solo** ``compromisos_gorila`` (no en cliente); el sistema puede reemplazar el texto del responsable por equipos inferidos de la invitación.
  • **Estilo ejecutivo/consolidado** cuando no haya lista explícita ``[Tag]`` …: fusiona bullets duplicadas del mismo frente.
  • Mantén todas las obligaciones distintas; agrupa sólo donde la redundancia es obvia desde las notas.
  • NUNCA inventes compromisos que no estén explícitamente mencionados en las notas.
- **Compromisos cliente** → compromisos_cliente[] — mismas reglas de atribución y consolidación.
- **Cierre** → cierre — 2–4 oraciones sintetizando principales acuerdos, sensación de avance y qué debe ocurrir antes de próximos touchpoints.

## fecha / hora_inicio / hora_fin (technical rules)
- Use METADATA as **priority** for fecha, hora_inicio, hora_fin when values appear there coherently.
- Always express fecha JSON as Spanish prose, e.g. "29 de abril de 2026" — NOT English variants like "Apr 29, 2026".
- Normalize horas a reloj 12 h tipo "H:MM AM"/"HH:MM PM" usando hora singular 1–9 cuando aplique si ya traen AM/PM.
- METADATA marcado "(no detectada)" or truly missing → derive from NOTAS (keywords como "Hora de inicio/fin", duraciones, agendas).
- If still unknown definitivamente, output literally "No especificada".

## asistentes (strict shape)
Each item must be exactly: {"nombre": "...", "puesto": "..."}
- Lista **solo personas reales** que participen según el **Detalle** de las notas (nombres y apellidos). Una fila por persona.
- NO incluyas como filas: correos sueltos, cuentas genéricas (ej. ads@…), ni etiquetas sueltas tipo “Marketing Gorila Hosting” si ya identificaste **personas** del equipo interno en el detalle.
- Para **personal de Gorila Hosting** cuya persona aparece en el detalle: ``puesto`` = rol/equipo breve (ej. “Marketing Gorila Hosting”, “Administración Gorila Hosting”) sin inventar cargos.
- **Cliente / terceros**: ``puesto`` puede ser empresa o “Cliente”; usa lo que indiquen las notas.
- METADATA “Invitado” es **orientativa** para equipos; no sustituye la lista final de personas cuando el detalle nombra a alguien.
- "puesto" NO debe tener frases “Líder de …”; mejor rol/org conciso — si sólo aparece equipo, asígnalo ahí sin inventar cargos falsos.

## compromisos (shape + tagging)
Each item MUST be: {"tarea": string, "responsable": string, "fecha_entrega": string}
- Tagging **[Marketing Gorila Hosting]** u similar → compromisos_gorila; ``responsable`` = etiqueta completa del equipo.
- Formato ``[Persona] Título: descripción`` → ``tarea`` = texto **completo** tras el primer ``:`` (descripción); nunca sustituyas por solo el título corto.
- **``[El grupo]`` / ``[Todos]``** → solo ``compromisos_gorila`` (nunca en cliente).
- Persona nombrada en el tag → ``compromisos_cliente`` aunque en la reunión sea colaborador de Gorila, salvo que el tag sea explícitamente un equipo Gorila Hosting.
- "tarea" = QUÉ hacer; "responsable" = QUIÉN (equipo/persona) — jamás invertir columnas.

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
  "asistentes": [{"nombre": string, "puesto": string}],
  "asuntos_tratados": [{"titulo": string, "descripcion": string}],
  "compromisos_gorila": [{"tarea": string, "responsable": string, "fecha_entrega": string}],
  "compromisos_cliente": [{"tarea": string, "responsable": string, "fecha_entrega": string}]
}

Technical hygiene: NEVER fabricate timestamps like "00:00:00". Keep JSON strings UTF-8 without control characters breaking JSON.
"""

# Salida JSON. En tier Groq on_demand (~12k TPM) el límite suele aplicar a prompt + max_tokens en la petición.
_MAX_COMPLETION_TOKENS = 6144
# Techo seguro: prompt (system+user) estimado + max_tokens por debajo del TPM de la organización.
_GROQ_REQUEST_TOKEN_CEILING = 11_500

_MODEL = "llama-3.3-70b-versatile"
_CHARS_PER_TOKEN = 4  # rough estimate for Spanish text


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _trim_to_budget(raw_text: str, budget_tokens: int) -> str:
    """Truncate keeping head (65 %) + tail (35 %) when over budget."""
    if _estimate_tokens(raw_text) <= budget_tokens:
        return raw_text
    budget_chars = budget_tokens * _CHARS_PER_TOKEN
    head = budget_chars * 65 // 100
    tail = budget_chars - head
    logger.warning(
        "raw_text truncado: %d chars → %d chars (budget %d tokens)",
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
    client = Groq(api_key=os.environ["GROQ_API_KEY"])

    md = metadata or {}
    attendees = md.get("attendees") or []
    att_join = ", ".join(attendees) if attendees else "(ninguno detectado)"
    teams = md.get("gorila_teams") or []
    teams_m = ", ".join(teams) if teams else "(ninguno detectado)"
    fecha_m = md.get("date") or "(no detectada)"
    hi_m = md.get("hora_inicio") or "(no detectada)"
    hf_m = md.get("hora_fin") or "(no detectada)"

    meta_block = (
        "METADATA EXTRAÍDO DEL DOCUMENTO:\n"
        f"Fecha: {fecha_m}\n"
        f"Hora inicio detectada: {hi_m}\n"
        f"Hora fin detectada: {hf_m}\n"
        f"Asistentes (display names): {att_join}\n"
        f"Equipos Gorila detectados en invitación: {teams_m}\n"
    )
    if md.get("calendar_url"):
        meta_block += f"URL calendario: {md['calendar_url']}\n"

    head = meta_block + "\nNOTAS COMPLETAS DE LA REUNIÓN:\n"
    tail = ""
    if source_filename:
        tail = (
            "\n\n---\nNombre del archivo de origen: "
            f"{source_filename}\n"
            "(Último recurso para cliente si no aparece en notas. METADATA tiene prioridad para fecha/horas; "
            "asistentes, asuntos completos y consolidación de compromisos priorizando NOTAS COMPLETAS.)\n"
        )

    prompt_prefix_tokens = (
        _estimate_tokens(_SYSTEM_PROMPT)
        + _estimate_tokens(head)
        + _estimate_tokens(tail)
        + 120  # slack
    )
    raw_budget = max(
        512,
        _GROQ_REQUEST_TOKEN_CEILING - _MAX_COMPLETION_TOKENS - prompt_prefix_tokens,
    )
    raw_text = _trim_to_budget(raw_text, raw_budget)

    user_body = head + raw_text + tail

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_body},
    ]

    holder = _LastRaw()
    data = _chat_completion_parse(client, messages, last_raw_holder=holder)

    try:
        return _validated_and_post_process(data, metadata=md)
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
        data2 = _chat_completion_parse(client, fix_messages, last_raw_holder=holder2)
        return _validated_and_post_process(data2, metadata=md)
