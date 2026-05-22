"""Tests de parseo de fechas para compromisos."""

from datetime import date

from src.dates import extract_fecha_entrega, parse_meeting_date


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


def test_extract_fecha_entrega_manana_tarde_before_manana() -> None:
    meeting = date(2026, 5, 21)
    out = extract_fecha_entrega(
        "Enviar el calendario de contenidos antes de las 5 de la tarde del día de mañana",
        meeting,
    )
    assert out == "22 de mayo de 2026, 5:00 PM"
