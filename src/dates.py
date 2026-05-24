"""Parseo de fechas de reunión y fechas de entrega en compromisos."""
from __future__ import annotations

import re
from datetime import date, timedelta

_MONTHS_EN: dict[str, int] = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_MONTHS_ES: dict[str, int] = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "set": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

_ES_MONTH_NAMES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

_MANANA_RE = re.compile(
    r"(?is)\bmañana\b"
    r"(?:[^.\n]{0,80}?(?:a\s+las?\s+)?(\d{1,2})(?::(\d{2}))?\s*([ap]\.?\s*m\.?|am|pm|a\.?\s*m\.?|p\.?\s*m\.?)?)?"
)

_EN_HEADER_DATE = re.compile(
    r"(?i)^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\s+(\d{1,2}),\s*(\d{4})$"
)

_ES_PROSE_DATE = re.compile(
    r"(?i)(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})"
)


def parse_meeting_date(date_str: str) -> date | None:
    """Interpreta fecha de reunión desde metadata Gemini o fecha en prosa del acta."""
    s = (date_str or "").strip()
    if not s:
        return None

    m = _ES_PROSE_DATE.search(s)
    if m:
        day, month_name, year = int(m.group(1)), m.group(2).casefold(), int(m.group(3))
        month = _MONTHS_ES.get(month_name)
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                return None

    m = _EN_HEADER_DATE.match(s)
    if m:
        month = _MONTHS_EN.get(m.group(1).casefold())
        if month:
            try:
                return date(int(m.group(3)), month, int(m.group(2)))
            except ValueError:
                return None

    return None


def format_meeting_date_prose(date_str: str) -> str:
    """Normaliza fecha de metadata Gemini a prosa española (ej. may 22, 2026 → 22 de mayo de 2026)."""
    s = (date_str or "").strip()
    if not s:
        return s
    if _ES_PROSE_DATE.search(s):
        return s
    parsed = parse_meeting_date(s)
    if parsed is None:
        return s
    return f"{parsed.day} de {_ES_MONTH_NAMES[parsed.month - 1]} de {parsed.year}"


_AMPM_TIME = re.compile(
    r"^\s*(\d{1,2}):(\d{2})\s*(AM|PM|A\.?\s*M\.?|P\.?\s*M\.?)\s*$",
    re.I,
)


def add_hours_to_ampm_time(time_str: str, hours: int = 1) -> str:
    """Parsea '9:00 AM' / '4:01 PM' y suma horas; devuelve '' si no parsea."""
    s = (time_str or "").strip()
    if not s:
        return ""
    m = _AMPM_TIME.match(s)
    if not m:
        return ""
    hour = int(m.group(1))
    minute = int(m.group(2))
    ampm = m.group(3)
    hour24 = _parse_ampm_hour(hour, ampm)
    total_minutes = hour24 * 60 + minute + hours * 60
    total_minutes %= 24 * 60
    new_hour = total_minutes // 60
    new_minute = total_minutes % 60
    return _format_time_ampm(new_hour, new_minute)


def _format_time_ampm(hour: int, minute: int) -> str:
    suffix = "AM" if hour < 12 else "PM"
    h12 = hour % 12 or 12
    return f"{h12}:{minute:02d} {suffix}"


def _parse_ampm_hour(hour: int, ampm: str | None) -> int:
    if not ampm:
        return hour
    low = re.sub(r"[^a-z]", "", ampm.casefold())
    if "pm" in low or low == "p":
        return hour + 12 if hour < 12 else hour
    if "am" in low or low == "a":
        return 0 if hour == 12 else hour
    return hour


def _extract_hour_from_manana_context(blob: str) -> tuple[int, int] | None:
    """Hora en frases con mañana: '5 de la tarde del día de mañana', '2PM mañana', etc."""
    patterns: list[tuple[str, str | None]] = [
        (
            r"(?i)(?:antes\s+de\s+)?(?:a\s+las?\s+)?(\d{1,2})(?::(\d{2}))?\s*(?:de\s+la\s+)?tarde",
            "pm",
        ),
        (
            r"(?i)(?:a\s+las?\s+)?(\d{1,2})(?::(\d{2}))?\s*(?:de\s+la\s+)?mañana",
            "am",
        ),
        (
            r"(?i)(?:a\s+las?\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.?\s*m\.?|p\.?\s*m\.?)",
            None,
        ),
    ]
    for pat, default_ampm in patterns:
        hm = re.search(pat, blob)
        if not hm:
            continue
        hour = int(hm.group(1))
        minute = int(hm.group(2)) if hm.group(2) else 0
        ampm = hm.group(3) if hm.lastindex and hm.lastindex >= 3 and hm.group(3) else default_ampm
        if ampm:
            hour = _parse_ampm_hour(hour, ampm)
        elif default_ampm == "pm" and hour < 12:
            hour += 12
        return hour, minute
    return None


def extract_fecha_entrega(text: str, meeting_date: date | None) -> str:
    """
    Extrae fecha de entrega desde descripción de compromiso.
    Devuelve prosa en español o cadena vacía si no hay señal clara.
    """
    blob = (text or "").strip()
    if not blob:
        return ""

    has_manana = bool(
        re.search(r"(?i)\bmañana\b", blob) or re.search(r"(?i)d[ií]a\s+de\s+mañana", blob)
    )
    if has_manana and meeting_date:
        target = meeting_date + timedelta(days=1)
        month_name = _ES_MONTH_NAMES[target.month - 1]
        base = f"{target.day} de {month_name} de {target.year}"
        hour_parts = _extract_hour_from_manana_context(blob)
        if hour_parts:
            hour, minute = hour_parts
            return f"{base}, {_format_time_ampm(hour, minute)}"
        return base

    m = _MANANA_RE.search(blob)
    if m and meeting_date:
        target = meeting_date + timedelta(days=1)
        month_name = _ES_MONTH_NAMES[target.month - 1]
        base = f"{target.day} de {month_name} de {target.year}"
        hour_s, minute_s, ampm = m.group(1), m.group(2), m.group(3)
        if hour_s:
            hour = _parse_ampm_hour(int(hour_s), ampm)
            minute = int(minute_s) if minute_s else 0
            return f"{base}, {_format_time_ampm(hour, minute)}"
        return base

    m = _ES_PROSE_DATE.search(blob)
    if m:
        day, month_name, year = int(m.group(1)), m.group(2).casefold(), int(m.group(3))
        month = _MONTHS_ES.get(month_name)
        if month:
            try:
                d = date(year, month, day)
                return f"{d.day} de {_ES_MONTH_NAMES[d.month - 1]} de {d.year}"
            except ValueError:
                pass

    if re.search(r"(?i)\bpor\s+definir\b", blob):
        return "Por definir"

    return ""


def fecha_entrega_for_compromiso(
    descripcion: str,
    meeting_date_str: str,
    *,
    default: str = "No especificada",
) -> str:
    parsed = extract_fecha_entrega(descripcion, parse_meeting_date(meeting_date_str))
    return parsed or default
