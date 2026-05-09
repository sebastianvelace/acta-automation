import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from groq import APIConnectionError, BadRequestError, Groq, RateLimitError
from pydantic import ValidationError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_chain
from tenacity.wait import wait_fixed

from src.aliases import post_process_acta
from src.schemas import ActaSchema

load_dotenv()

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an assistant that structures meeting summaries into JSON.

Rules:
- Respond ONLY with valid JSON. No markdown, no backticks, no preamble, no explanation.
- Extract all fields from "NOTAS COMPLETAS DE LA REUNIÓN" and cross-check with METADATA EXTRAÍDO when present.
- Generate a descriptive "titulo" based on the meeting content.
- For "fecha", return Spanish prose format only, e.g. "29 de abril de 2026" — never English like "Apr 29, 2026".
  Prefer converting the METADATA date line (e.g. "abr 29, 2026") into that Spanish format.

The user's message begins with METADATA EXTRAÍDO DEL DOCUMENTO (parser output) followed by NOTAS COMPLETAS.

## fecha, hora_inicio and hora_fin (priority)
- Use the METADATA section as **priority source** for fecha, hora_inicio, and hora_fin when values are detected there.
- If METADATA fecha is present but in English/month-abbr style, normalize to Spanish "d de mes de yyyy" for the JSON fecha field.
- If METADATA hora_inicio / hora_fin are present, use them — normalize both to 12-hour clock strings: "H:MM AM" or "HH:MM AM",
  unless the value already includes explicit am/pm. Use single-digit hour when 1–9.
- Only if METADATA horas are absent or explicitly "(no detectada)", derive times from NOTAS COMPLETAS (keywords like
  "Hora de inicio", durations, narrative "inicio"/"fin", etc.).
- If after METADATA + body you truly cannot determine a value, output exactly "No especificada".

## cliente
- Preserve "&" when the original uses "&"; do not replace with "y".
- Extract the **full meeting title** as cliente, including subtitle/context **after em dash/dash/hyphen** if present,
  similar to "(Área/Tema ) – subtítulo estratégico" (e.g. "Eventos & Matrimonios – Seguimiento Estrategia Digital").

## asuntos_tratados
Each item: {"titulo": string, "descripcion": string}
- "titulo": short numbered-topic heading only; "descripcion": explanatory paragraph — no long narrative inside titulo.

## asistentes (strict shape)
Each item must be exactly: {"nombre": "...", "puesto": "..."}
- Prefer **real full person names** from NOTAS COMPLETAS (body / Detalles) when explicitly stated there.
- The METADATA **Asistentes (display names)** are email/calendar aliases, not reliably legal names.
  • When real name unknown: derive "nombre" as the **most human-readable concise label** from the alias
    (example: display "Social Media Gorila Hosting" → nombre: "Social Media", puesto: "Gorila Hosting").
  • Raw emails (e.g. info@…) → nombre: derive from local-part/domain or concise role; use "Correo" / domain as hint.
    Put organization or channel in "puesto" when clear.
- "puesto" must NOT embed relational phrases ("Líder de X"); use organization/role/concise fallback or "No especificado".

## compromisos_gorila and compromisos_cliente
Each item: {"tarea": string, "responsable": string}
- CRITICAL: Extract **every** commitment. Count bullets before answering; never truncate.
- Extract commitments from BOTH the **Próximos pasos** section **and** the **Detalles** section (tasks may recur or extend there).
  Cross-reference both; one bullet equals one commitment.
- Count every bullet/list item labeled or implied per party (e.g. "-", "•", numbering).
- Entries tagged/bracketed for Gorila such as **[Marketing Gorila Hosting] Informe Mensual: ...** belong under **compromisos_gorila**:
  bracket team → responsable slice; remainder → tarea. Client-side bracketed bullets → compromisos_cliente similarly.
- "tarea" = WHAT; "responsable" = WHO (person or team). Never swap columns.

## JSON schema

{
  "titulo": string,
  "fecha": string,
  "hora_inicio": string,
  "hora_fin": string,
  "lugar": string,
  "cliente": string,
  "objetivo": string,
  "asistentes": [{"nombre": string, "puesto": string}],
  "asuntos_tratados": [{"titulo": string, "descripcion": string}],
  "compromisos_gorila": [{"tarea": string, "responsable": string}],
  "compromisos_cliente": [{"tarea": string, "responsable": string}]
}

Do not emit placeholder clocks like "00:00:00". "objetivo" must be one sentence summarizing the meeting purpose.
"""

_MODEL = "llama-3.3-70b-versatile"


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
            max_tokens=2000,
            messages=messages,
            response_format={"type": "json_object"},
        )
    except BadRequestError:
        raise
    raw = response.choices[0].message.content or ""
    last_raw_holder.value = raw
    return _extract_json(raw)


def _schema_retry_errors(exc: ValidationError) -> str:
    return json.dumps(exc.errors(), ensure_ascii=False)


def _validated_and_post_process(data: dict[str, Any]) -> dict[str, Any]:
    validated = ActaSchema.model_validate(data).model_dump()
    return post_process_acta(validated)


def structure_meeting(
    raw_text: str,
    metadata: dict | None = None,
    source_filename: str | None = None,
) -> dict:
    client = Groq(api_key=os.environ["GROQ_API_KEY"])

    md = metadata or {}
    attendees = md.get("attendees") or []
    att_join = ", ".join(attendees) if attendees else "(ninguno detectado)"
    fecha_m = md.get("date") or "(no detectada)"
    hi_m = md.get("hora_inicio") or "(no detectada)"
    hf_m = md.get("hora_fin") or "(no detectada)"

    meta_block = (
        "METADATA EXTRAÍDO DEL DOCUMENTO:\n"
        f"Fecha: {fecha_m}\n"
        f"Hora inicio detectada: {hi_m}\n"
        f"Hora fin detectada: {hf_m}\n"
        f"Asistentes (display names): {att_join}\n"
    )
    if md.get("calendar_url"):
        meta_block += f"URL calendario: {md['calendar_url']}\n"

    user_body = meta_block + "\nNOTAS COMPLETAS DE LA REUNIÓN:\n" + raw_text

    if source_filename:
        user_body += (
            "\n\n---\nNombre del archivo de origen: "
            f"{source_filename}\n(Solo referencia; horas explícitas en METADATA tienen prioridad.)\n"
        )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_body},
    ]

    holder = _LastRaw()
    data = _chat_completion_parse(client, messages, last_raw_holder=holder)

    try:
        return _validated_and_post_process(data)
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
        return _validated_and_post_process(data2)
