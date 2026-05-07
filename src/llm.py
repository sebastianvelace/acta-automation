import json
import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

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

    response = client.chat.completions.create(
        model=_MODEL,
        temperature=0.2,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_body},
        ],
    )

    content = response.choices[0].message.content

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Model returned invalid JSON: {e}\n--- Raw response ---\n{content}"
        ) from e
