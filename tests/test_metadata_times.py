"""Horas del acta desde metadata del parser (sin Calendar API)."""

from __future__ import annotations

from src.google_workflow import apply_metadata_times_to_acta


def test_parser_hora_overrides_llm_placeholder() -> None:
    out = apply_metadata_times_to_acta(
        {"hora_inicio": "No especificada", "hora_fin": "No especificada"},
        {"hora_inicio": "4:01 PM"},
    )
    assert out["hora_inicio"] == "4:01 PM"


def test_parser_hora_does_not_override_llm_when_present() -> None:
    out = apply_metadata_times_to_acta(
        {"hora_inicio": "3:00 PM"},
        {"hora_inicio": "4:01 PM"},
    )
    assert out["hora_inicio"] == "3:00 PM"


def test_calendar_event_forces_metadata_hora() -> None:
    out = apply_metadata_times_to_acta(
        {"hora_inicio": "3:00 PM", "hora_fin": "No especificada"},
        {
            "hora_inicio": "4:01 PM",
            "hora_fin": "5:00 PM",
            "calendar_event_id": "evt",
        },
    )
    assert out["hora_inicio"] == "4:01 PM"
    assert out["hora_fin"] == "5:00 PM"
    assert out["hora_final"] == "5:00 PM"


def test_virtual_meeting_sets_google_meet_lugar() -> None:
    out = apply_metadata_times_to_acta(
        {"lugar": "No especificada"},
        {"is_virtual": True},
    )
    assert out["lugar"] == "Google Meet"
