"""Tests de parseo de fechas para compromisos."""

from datetime import date

from src.dates import add_hours_to_ampm_time, extract_fecha_entrega, format_meeting_date_prose, parse_meeting_date


def test_parse_meeting_date_english_header() -> None:
    assert parse_meeting_date("may 21, 2026") == date(2026, 5, 21)


def test_parse_meeting_date_spanish_prose() -> None:
    assert parse_meeting_date("21 de mayo de 2026") == date(2026, 5, 21)


def test_extract_fecha_entrega_manana_con_hora() -> None:
    meeting = date(2026, 5, 21)
    out = extract_fecha_entrega(
        "Convocar a una sesión de seguimiento con Pedro para mañana a las 2PM",
        meeting,
    )
    assert out == "22 de mayo de 2026, 2:00 PM"


def test_extract_fecha_entrega_manana_sin_hora() -> None:
    meeting = date(2026, 5, 21)
    out = extract_fecha_entrega("Entregar reporte mañana", meeting)
    assert out == "22 de mayo de 2026"


def test_format_meeting_date_prose_english() -> None:
    assert format_meeting_date_prose("may 22, 2026") == "22 de mayo de 2026"


def test_format_meeting_date_prose_spanish_unchanged() -> None:
    assert format_meeting_date_prose("22 de mayo de 2026") == "22 de mayo de 2026"


def test_add_hours_to_ampm_time() -> None:
    assert add_hours_to_ampm_time("9:00 AM", 1) == "10:00 AM"
    assert add_hours_to_ampm_time("4:01 PM", 1) == "5:01 PM"
    assert add_hours_to_ampm_time("11:30 PM", 1) == "12:30 AM"


def test_extract_fecha_entrega_manana_tarde_before_manana() -> None:
    meeting = date(2026, 5, 21)
    out = extract_fecha_entrega(
        "Enviar el calendario de contenidos antes de las 5 de la tarde del día de mañana",
        meeting,
    )
    assert out == "22 de mayo de 2026, 5:00 PM"
