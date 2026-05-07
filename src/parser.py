from __future__ import annotations

import os
import re
from typing import Any

from docx import Document

# Capture group for a time literal (allows optional am/pm or trailing "h")
_TIME_CAPTURE = (
    r"(\d{1,2}:\d{2}(?::\d{2})?"
    r"(?:\s*[ap]\.?\s*m\.?|\s*h\b)?)"
)

FILENAME_DATETIME_RE = re.compile(r"(20\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})")

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
        "hora_inicio": "",
        "hora_fin": "",
        "calendar_url": "",
    }


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
    parts = re.split(r"[,;\n]+", blob)

    dedup: list[str] = []
    seen = set()
    for p in parts:
        t = " ".join(p.split())
        if len(t) < 2:
            continue
        k = t.lower()
        if k not in seen:
            seen.add(k)
            dedup.append(t)

    # If split failed (single comma-free line), return whole trimmed blob once
    if not dedup and blob:
        dedup.append(" ".join(blob.split()))

    return dedup


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


def _extract_times_from_filename(basename: str) -> tuple[str, str]:
    m = FILENAME_DATETIME_RE.search(basename)
    if not m:
        return "", ""
    h, mi = int(m.group(4)), int(m.group(5))
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return "", ""
    return f"{h}:{mi:02d}", ""


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
    meta["calendar_url"] = _extract_calendar_url(raw_text)

    body_ini, body_fin = _extract_hora_from_body(raw_text)
    file_ini, _ = _extract_times_from_filename(os.path.basename(docx_path))

    meta["hora_inicio"] = body_ini or file_ini or ""
    meta["hora_fin"] = body_fin or ""

    return {"raw_text": raw_text, "metadata": meta}
