"""Enriquecimiento de invitados por correo (roster Gorila)."""

from __future__ import annotations

from src.aliases import build_invitados_from_attendee_emails
from src.gorila_roster import format_staff_puesto, invitado_fields_from_email, lookup_staff_by_email


def test_marketing_email_maps_to_viviana_blanco() -> None:
    row = invitado_fields_from_email("marketing@gorila.hosting")
    assert row["nombre"] == "Viviana Blanco"
    assert row["puesto"] == "Senior Comunicaciones Gorila"
    assert row["correo"] == "marketing@gorila.hosting"
    assert row["asistencia"] == "Confirmado"


def test_format_staff_puesto_appends_gorila() -> None:
    assert format_staff_puesto("Senior Comunicaciones") == "Senior Comunicaciones Gorila"
    assert format_staff_puesto("Marketing Gorila Hosting") == "Marketing Gorila Hosting"


def test_unknown_email_fallback_to_humanized_name() -> None:
    row = invitado_fields_from_email("cliente@empresa.co", cliente_account="Empresa Co")
    assert row["nombre"] == "Cliente"
    assert row["puesto"] == "Empresa Co"
    assert row["correo"] == "cliente@empresa.co"


def test_build_invitados_deduplicates_and_enriches() -> None:
    rows = build_invitados_from_attendee_emails(
        ["marketing@gorila.hosting", "MARKETING@gorila.hosting", "x@y.com"]
    )
    assert len(rows) == 2
    assert rows[0]["nombre"] == "Viviana Blanco"


def test_universal_gemini_docx_invitados() -> None:
    """Prueba con notas reales Universal (sin LLM): solo parser + roster."""
    from src.parser import extract_text

    path = (
        "/home/sebasvelace/Downloads/Actualización Dashboard - Universal _ "
        "2026_05_21 11_02 GMT-05_00 - Notas de Gemini.docx"
    )
    try:
        parsed = extract_text(path)
    except FileNotFoundError:
        import pytest

        pytest.skip("DOCX Universal no disponible en este entorno")

    emails = parsed["metadata"].get("attendee_emails") or []
    invitados = build_invitados_from_attendee_emails(emails)
    assert len(invitados) == len(emails)
    by_correo = {r["correo"].casefold(): r for r in invitados}
    assert by_correo["davidgutierrez@growfik.com"]["nombre"] == "David Gutiérrez"
    assert by_correo["samuel.villalobos@universal.edu.co"]["nombre"] == "Samuel Villalobos"
    assert lookup_staff_by_email("marketing@gorila.hosting") is not None
