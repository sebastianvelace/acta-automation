from __future__ import annotations

import os
import re
from typing import Any, TypedDict

from docx import Document

from src.aliases import TEAM_ALIASES, looks_like_person_name
from src.gorila_roster import roster_emails
from src.meeting_time_overrides import apply_meeting_time_overrides

# Capture group for a time literal (allows optional am/pm or trailing "h")
_TIME_CAPTURE = (
    r"(\d{1,2}:\d{2}(?::\d{2})?"
    r"(?:\s*[ap]\.?\s*m\.?|\s*h\b)?)"
)

FILENAME_DATETIME_RE = re.compile(
    r"(20\d{2})_(\d{2})_(\d{2})[_\s](\d{2})_(\d{2})"
)

CALENDAR_URL_RE = re.compile(
    r'(https?://(?:www\.)?calendar\.google\.com[^\s\)\]>\"\'<]+)',
    re.IGNORECASE,
)

_FIRST_LINE_DATE = re.compile(
    r"(?i)^(ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic)"
    r"\s+\d{1,2},\s*\d{4}\s*$|"
    r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\s+\d{1,2},\s*\d{4}\s*$",
)


def _empty_metadata() -> dict[str, Any]:
    return {
        "date": "",
        "attendees": [],
        "gorila_teams": [],
        "attendee_emails": [],
        "gorila_emails": [],
        "client_emails": [],
        "gorila_person_names": [],
        "hora_inicio": "",
        "hora_fin": "",
        "calendar_url": "",
        "is_virtual": False,
    }


def _detect_virtual_meeting(full_text: str) -> bool:
    """True when the document shows evidence of a virtual meeting (recording, Meet/Zoom link)."""
    if re.search(r"(?i)meet\.google\.com|zoom\.us/j/", full_text):
        return True
    if re.search(r"(?i)registros\s+de\s+la\s+reuni[oó]n|\bgrabaci[oó]n\b", full_text):
        return True
    m = re.search(
        r"(?is)archivos\s+adjuntos\s*(.{0,800}?)(?=registros\s+de\s+la\s+reuni[oó]n|\Z)",
        full_text,
    )
    if m and re.search(r"(?i)recording|grabaci[oó]n", m.group(1)):
        return True
    return False


_GORILA_EMAIL_MARKERS = ("gorilahosting", "growfik")

_GORILA_ROLE_IN_TEXT = (
    r"(?:Marketing|Administración|Redes|Social Media|Executive|Soporte|Ventas|Diseño|Producto)"
    r"\s+Gorila Hosting"
)


def is_gorila_email(email: str) -> bool:
    """True for correos internos Gorila (dominio, roster o patrones legacy)."""
    e = (email or "").casefold().strip()
    if not e:
        return False
    if e.endswith("@gorila.hosting") or "@gorila.hosting" in e:
        return True
    if any(m in e for m in _GORILA_EMAIL_MARKERS):
        return True
    return e in roster_emails()


_GORILA_PERSON_STOPWORDS = re.compile(
    r"(?i)\b("
    r"estado|gesti[oó]n|planificaci[oó]n|sitio|revisi[oó]n|entrega|proceso|equipo|"
    r"contenido|parrilla|aniversario|aprobaci[oó]n|cronograma|respecto|marketing|"
    r"administraci[oó]n|redes|social|media|executive|soporte|ventas|diseño|producto"
    r")\b"
)


def _is_plausible_gorila_person_name(name: str) -> bool:
    if not looks_like_person_name(name):
        return False
    if _GORILA_PERSON_STOPWORDS.search(name):
        return False
    tokens = name.split()
    if len(tokens) < 2 or len(tokens) > 4:
        return False
    return True


def extract_gorila_person_names(raw_text: str) -> list[str]:
    """
    Nombres de personas internas mencionadas en **Detalles** junto a un equipo Gorila Hosting.
    """
    m = re.search(r"(?is)detalles\s*(.*)", raw_text or "")
    if not m:
        return []
    section = m.group(1)
    patterns = (
        re.compile(
            rf"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){{1,4}})\s*"
            rf"\([^)]*{_GORILA_ROLE_IN_TEXT}[^)]*\)",
            re.I,
        ),
        re.compile(
            rf"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){{1,3}})\s*"
            rf"\([^)]*{_GORILA_ROLE_IN_TEXT}[^)]*\)",
            re.I,
        ),
    )
    found: list[str] = []
    seen: set[str] = set()
    for pat in patterns:
        for match in pat.finditer(section):
            name = " ".join(match.group(1).split())
            key = name.casefold()
            if key in seen or not _is_plausible_gorila_person_name(name):
                continue
            seen.add(key)
            found.append(name)
    return found


class ProximoPasoItem(TypedDict):
    tag: str
    titulo_corto: str
    descripcion: str


_PROXIMO_PASO_LINE_RE = re.compile(
    r"^\s*\[\s*([^\]]+?)\s*\]\s*([^:]+?):\s*(.+?)\s*$",
)


def extract_proximos_pasos_items(raw_text: str) -> list[ProximoPasoItem]:
    """
    Parse Gemini ``Próximos pasos`` lines:
    ``[Tag] Título corto: descripción completa``.
    """
    m = re.search(
        r"(?is)próximos\s+pasos\s*(.*?)(?=^\s*detalles\s*$|\Z)",
        raw_text,
        re.MULTILINE,
    )
    if not m:
        return []
    section = m.group(1)
    items: list[ProximoPasoItem] = []
    for line in section.splitlines():
        line = line.strip()
        if not line:
            continue
        mm = _PROXIMO_PASO_LINE_RE.match(line)
        if mm:
            items.append(
                {
                    "tag": mm.group(1).strip(),
                    "titulo_corto": mm.group(2).strip(),
                    "descripcion": mm.group(3).strip(),
                }
            )
    return items


_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Za-z]{2,}")


def _extract_gorila_team_labels(blob: str) -> list[str]:
    """Ordered unique substring matches for known Gorila Hosting calendar labels."""
    norm = " ".join(blob.split())
    low = norm.casefold()
    keys = [k for k in TEAM_ALIASES if "Gorila Hosting" in k and k != "Gorila Hosting"]
    found: list[str] = []
    seen_cf: set[str] = set()
    for key in sorted(keys, key=len, reverse=True):
        kf = key.casefold()
        if kf in low and kf not in seen_cf:
            found.append(key)
            seen_cf.add(kf)
    # Bare "Gorila Hosting" only if no specific team was found
    if "gorila hosting" in low and not found:
        bare = "Gorila Hosting"
        if bare in TEAM_ALIASES:
            found.append(bare)
    return found


def _parse_invite_blob(blob: str) -> tuple[list[str], list[str], list[str]]:
    """
    From Gemini ``Invitado`` line: return (attendee_display_parts, gorila_teams, client_emails).
    """
    blob = " ".join(blob.strip().split())
    if not blob:
        return [], [], []
    emails = list(dict.fromkeys(_EMAIL_RE.findall(blob)))
    gorila_teams = _extract_gorila_team_labels(blob)
    parts: list[str] = []
    parts.extend(gorila_teams)
    parts.extend(emails)
    return parts, gorila_teams, emails


def _extract_header_date(lines: list[str]) -> str:
    """First non-empty line resembling 'abr 29, 2026' / 'may 6, 2026'."""
    for raw in lines:
        line = (raw or "").strip()
        if not line:
            continue
        if _FIRST_LINE_DATE.match(line):
            return line
    return ""


def _extract_attendees_between_markers(full_text: str) -> list[str]:
    """Everything between Invitado(s)... and Archivos adjuntos."""
    m = re.search(
        r"(?is)invitados?\s*[:\s]*(.{0,8000}?)(?=archivos\s+adjuntos)",
        full_text,
    )
    if not m:
        return []

    blob = m.group(1).strip().replace("\r\n", "\n").replace("\r", "\n")
    parts, _, _ = _parse_invite_blob(blob)
    if parts:
        return parts

    legacy = re.split(r"[,;\n]+", blob)
    dedup: list[str] = []
    seen: set[str] = set()
    for p in legacy:
        t = " ".join(p.split())
        if len(t) < 2:
            continue
        k = t.lower()
        if k not in seen:
            seen.add(k)
            dedup.append(t)
    if not dedup and blob:
        dedup.append(" ".join(blob.split()))
    return dedup


def fill_invite_metadata(meta: dict[str, Any], raw_text: str) -> None:
    """Set equipos Gorila y correos de invitados desde el bloque Invitado."""
    m = re.search(
        r"(?is)invitados?\s*[:\s]*(.{0,8000}?)(?=archivos\s+adjuntos)",
        raw_text,
    )
    if not m:
        meta["gorila_teams"] = []
        meta["attendee_emails"] = []
        meta["gorila_emails"] = []
        meta["client_emails"] = []
        return
    blob = m.group(1).strip().replace("\r\n", "\n").replace("\r", "\n")
    _, teams, emails = _parse_invite_blob(blob)
    meta["gorila_teams"] = teams
    meta["attendee_emails"] = emails
    meta["gorila_emails"] = [e for e in emails if is_gorila_email(e)]
    meta["client_emails"] = [e for e in emails if not is_gorila_email(e)]


def _extract_calendar_url(full_text: str) -> str:
    cal = CALENDAR_URL_RE.search(full_text)
    if cal:
        return cal.group(1).rstrip(".,;)")
    return ""


def _first_match(regexes: list[str], haystack: str) -> str:
    for pat in regexes:
        mx = re.search(pat, haystack, re.IGNORECASE | re.DOTALL)
        if mx:
            return mx.group(1).strip()
    condensed = haystack.replace("\n", " ")
    for pat in regexes:
        mx = re.search(pat, condensed, re.IGNORECASE | re.DOTALL)
        if mx:
            return mx.group(1).strip()
    return ""


def _extract_hora_from_body(full_text: str) -> tuple[str, str]:
    tc = _TIME_CAPTURE
    ini_patterns = [
        rf"(?is)hora\s+de\s+inicio.*?{tc}",
        rf"(?is)fecha\s*y\s+hora\s+de\s+inicio.*?{tc}",
        rf"(?i)hora\s+inicio\b.*?{tc}",
        rf"(?i)\b(?:inicio|start)\s*[: ]\s*{tc}",
    ]
    fin_patterns = [
        rf"(?is)hora\s+de\s+finalizaci[oó]n.*?{tc}",
        rf"(?is)fecha\s*y\s+hora\s+de\s+finalizaci[oó]n.*?{tc}",
        rf"(?is)fecha\s*y\s+hora\s+de\s+finalizacion.*?{tc}",
        rf"(?is)hora\s+de\s+término.*?{tc}",
        rf"(?is)hora\s+de\s+termino.*?{tc}",
        rf"(?is)hora\s+fin\b.*?{tc}",
        rf"(?i)\b(?:fin|end)\s*[: ]\s*{tc}",
    ]

    ini = _first_match(ini_patterns, full_text)
    fin = _first_match(fin_patterns, full_text)

    if not fin:
        rng = list(
            re.finditer(
                rf"(\d{{1,2}}:\d{{2}}(?::\d{{2}})?)\s*[–\-]\s*(\d{{1,2}}:\d{{2}}(?::\d{{2}})?)",
                full_text[:5000],
            )
        )
        if rng:
            ini = ini or rng[0].group(1).strip()
            fin = fin or rng[0].group(2).strip()

    combined = list(
        re.finditer(
            rf"(?i)(\d{{1,2}})[:/](\d{{2}})\s*[–\-]\s*(\d{{1,2}})[:/](\d{{2}})",
            full_text[:3000],
        )
    )
    if not ini and combined:
        c = combined[0]
        ini = f"{c.group(1)}:{c.group(2)}"
    if not fin and combined:
        c = combined[0]
        fin = fin or f"{c.group(3)}:{c.group(4)}"

    return ini, fin


def _format_hora_ampm(hour: int, minute: int) -> str:
    """Reloj 12 h tipo '11:02 AM' / '4:07 PM'."""
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return ""
    suffix = "AM" if hour < 12 else "PM"
    h12 = hour % 12
    if h12 == 0:
        h12 = 12
    return f"{h12}:{minute:02d} {suffix}"


def _extract_times_from_filename(basename: str) -> tuple[str, str]:
    m = FILENAME_DATETIME_RE.search(basename)
    if not m:
        return "", ""
    h, mi = int(m.group(4)), int(m.group(5))
    formatted = _format_hora_ampm(h, mi)
    return formatted, ""


def _filename_time_likely_gemini_export(basename: str, minute: int) -> bool:
    """Gemini export filenames often end in ``…_15_59 GMT`` (export stamp), not meeting start."""
    if not re.search(r"(?i)GMT", basename or ""):
        return False
    return minute >= 59


def count_detalles_blocks(raw_text: str) -> tuple[int, int]:
    """
    Estima cobertura de asuntos: (caracteres en Detalles, bloques/temas detectados).
    """
    m = re.search(r"(?is)detalles\s*(.*)", raw_text or "")
    if not m:
        return 0, 0
    section = m.group(1).strip()
    if not section:
        return 0, 0
    tema_lines = len(re.findall(r"(?im)^\s*[^:]+:\s*\S", section))
    paragraphs = [p for p in re.split(r"\n\s*\n", section) if p.strip()]
    blocks = max(tema_lines, len(paragraphs), 1) if section else 0
    return len(section), blocks


def extract_text(docx_path: str) -> dict[str, Any]:
    """
    Read Gemini-style meeting docx: full text plus metadata from headers and patterns.
    Returns {"raw_text": str, "metadata": {date, attendees, hora_inicio, hora_fin, calendar_url}}
    """
    doc = Document(docx_path)
    raw_lines = [p.text for p in doc.paragraphs]
    raw_text = "\n".join(raw_lines)

    meta = _empty_metadata()
    meta["date"] = _extract_header_date(raw_lines)
    meta["attendees"] = _extract_attendees_between_markers(raw_text)
    fill_invite_metadata(meta, raw_text)
    meta["gorila_person_names"] = extract_gorila_person_names(raw_text)
    meta["calendar_url"] = _extract_calendar_url(raw_text)
    meta["is_virtual"] = _detect_virtual_meeting(raw_text)

    body_ini, body_fin = _extract_hora_from_body(raw_text)
    basename = os.path.basename(docx_path)
    file_ini, _ = _extract_times_from_filename(basename)
    if not body_ini and file_ini:
        fm = FILENAME_DATETIME_RE.search(basename)
        if fm and _filename_time_likely_gemini_export(basename, int(fm.group(5))):
            file_ini = ""

    meta["hora_inicio"] = body_ini or file_ini or ""
    meta["hora_fin"] = body_fin or ""
    meta = apply_meeting_time_overrides(meta, source_filename=basename)

    return {"raw_text": raw_text, "metadata": meta}
