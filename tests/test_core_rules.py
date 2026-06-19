"""Unit tests de helpers de alto riesgo: overrides de hora, normalización de nombres, aliases."""
from __future__ import annotations

import pytest

from src import meeting_time_overrides as mto
from src.aliases import (
    _normalize_proximos_person_name,
    compose_cliente_heading,
    infer_gorila_responsable,
    normalize_gorila_compromiso_responsable_display,
)
from src.client_contacts import lookup_client_contact_by_alias


# ---------------------------------------------------------------------------
# meeting_time_overrides — date scoping + guard de hora parseada
# ---------------------------------------------------------------------------


@pytest.fixture
def overrides(tmp_path, monkeypatch):
    """Escribe un YAML temporal de overrides y limpia el cache del loader."""

    def _write(content: str) -> None:
        path = tmp_path / "meeting_time_overrides.yaml"
        path.write_text(content, encoding="utf-8")
        monkeypatch.setattr(mto, "_OVERRIDES_PATH", path)
        mto._load_overrides.cache_clear()

    yield _write
    mto._load_overrides.cache_clear()


def test_override_with_date_applies_only_on_that_date(overrides):
    overrides(
        """
overrides:
  - match: "Seguimiento - Real State"
    date: "2026_06_02"
    hora_inicio: "10:00 AM"
    hora_fin: "11:00 AM"
"""
    )
    hit = mto.apply_meeting_time_overrides(
        {}, source_filename="Seguimiento - Real State _ 2026_06_02 10_59 GMT-05_00.docx"
    )
    assert hit["hora_inicio"] == "10:00 AM"
    assert hit["hora_fin"] == "11:00 AM"

    miss = mto.apply_meeting_time_overrides(
        {"hora_inicio": "11:01 AM"},
        source_filename="Seguimiento - Real State _ 2026_06_09 11_01 GMT-05_00.docx",
    )
    assert miss["hora_inicio"] == "11:01 AM"


def test_override_with_dates_list_applies_to_each_date(overrides):
    overrides(
        """
overrides:
  - match: "Seguimiento - Universal Academia de Idiomas"
    dates: ["2026_06_02", "2026_06_09"]
    hora_inicio: "2:00 PM"
    hora_fin: "3:00 PM"
"""
    )
    for date in ("2026_06_02", "2026_06_09"):
        out = mto.apply_meeting_time_overrides(
            {},
            source_filename=(
                f"Seguimiento - Universal Academia de Idiomas_ {date} 13_56 GMT-05_00.docx"
            ),
        )
        assert out["hora_inicio"] == "2:00 PM", date
    other = mto.apply_meeting_time_overrides(
        {},
        source_filename=(
            "Seguimiento - Universal Academia de Idiomas_ 2026_06_16 14_00 GMT-05_00.docx"
        ),
    )
    assert not other.get("hora_inicio")


def test_dateless_override_prefers_parsed_real_time(overrides, caplog):
    overrides(
        """
overrides:
  - match: "1_1 Elephant"
    hora_inicio: "5:00 PM"
    hora_fin: "6:00 PM"
"""
    )
    with caplog.at_level("WARNING", logger="src.meeting_time_overrides"):
        out = mto.apply_meeting_time_overrides(
            {"hora_inicio": "4:30 PM"},
            source_filename="1_1 Elephant_ 2026_06_11 16_30 GMT-05_00.docx",
        )
    assert out["hora_inicio"] == "4:30 PM"
    assert not out.get("hora_fin")
    assert any("Override de hora sin fecha" in r.message for r in caplog.records)


def test_dateless_override_applies_when_no_parsed_time(overrides):
    overrides(
        """
overrides:
  - match: "1_1 Elephant"
    hora_inicio: "5:00 PM"
    hora_fin: "6:00 PM"
"""
    )
    out = mto.apply_meeting_time_overrides(
        {}, source_filename="1_1 Elephant_ 2026_06_04 16_59 GMT-05_00.docx"
    )
    assert out["hora_inicio"] == "5:00 PM"
    assert out["hora_fin"] == "6:00 PM"


def test_dated_override_wins_over_parsed_time(overrides):
    # Con fecha explícita el override es intencional para esa reunión concreta.
    overrides(
        """
overrides:
  - match: "Estrategia Rebella"
    dates: ["2026_06_05"]
    hora_inicio: "3:00 PM"
    hora_fin: "4:00 PM"
"""
    )
    out = mto.apply_meeting_time_overrides(
        {"hora_inicio": "3:04 PM"},
        source_filename="Estrategia Rebella _ 2026_06_05 15_04 GMT-05_00.docx",
    )
    assert out["hora_inicio"] == "3:00 PM"


def test_override_matches_via_notes_text_when_filename_and_title_differ(overrides):
    # El archivo fue renombrado: ni el nombre ni el título contienen el `match`;
    # el título de la serie solo aparece en el texto de las notas/adjunto (raw_text).
    overrides(
        """
overrides:
  - match: "Actualización Dashboard - Universal"
    dates: ["2026_06_04"]
    hora_inicio: "11:00 AM"
    hora_fin: "12:00 PM"
"""
    )
    notes = (
        "Notas de Gemini\n"
        "Reunión: Actualización Dashboard - Universal\n"
        "Revisamos el avance del dashboard."
    )
    out = mto.apply_meeting_time_overrides(
        {},
        source_filename="Dashboard y Web - Universal = Growfit _ Gorila_ 2026_06_04 10_59 GMT-05_00.docx",
        notes_text=notes,
    )
    assert out["hora_inicio"] == "11:00 AM"
    assert out["hora_fin"] == "12:00 PM"

    # Sin pasar las notas (compat. hacia atrás) el override no casa.
    miss = mto.apply_meeting_time_overrides(
        {},
        source_filename="Dashboard y Web - Universal = Growfit _ Gorila_ 2026_06_04 10_59 GMT-05_00.docx",
    )
    assert not miss.get("hora_inicio")


# ---------------------------------------------------------------------------
# _normalize_proximos_person_name
# ---------------------------------------------------------------------------


def test_normalize_strips_stray_dots():
    assert _normalize_proximos_person_name("Samuel. Villalobos") == "Samuel Villalobos"


def test_normalize_title_cases_all_caps():
    assert _normalize_proximos_person_name("SAMUEL VILLALOBOS") == "Samuel Villalobos"


def test_normalize_title_cases_lowercase():
    assert _normalize_proximos_person_name("samuel villalobos") == "Samuel Villalobos"


def test_normalize_resolves_yaml_alias():
    assert _normalize_proximos_person_name("Sophia7 Marketing") == "Sophia Bello Mendez"
    assert _normalize_proximos_person_name("yaris") == "Jaris Table"


# ---------------------------------------------------------------------------
# lookup_client_contact_by_alias (data/client_contacts.yaml)
# ---------------------------------------------------------------------------


def test_alias_lookup_case_insensitive():
    contact = lookup_client_contact_by_alias("YARIS")
    assert contact is not None
    assert contact.name == "Jaris Table"


def test_alias_lookup_accent_insensitive():
    contact = lookup_client_contact_by_alias("Sophía7 Marketing")
    assert contact is not None
    assert contact.name == "Sophia Bello Mendez"


def test_alias_lookup_unknown_returns_none():
    assert lookup_client_contact_by_alias("Nadie Conocido") is None
    assert lookup_client_contact_by_alias("") is None


# ---------------------------------------------------------------------------
# compose_cliente_heading — puntuación final
# ---------------------------------------------------------------------------


def test_heading_strips_trailing_punctuation_from_title():
    assert (
        compose_cliente_heading("Redes - Universal Idiomas.", "Universal Idiomas")
        == "Redes - Universal Idiomas"
    )


def test_heading_strips_trailing_punctuation_from_cliente():
    assert (
        compose_cliente_heading("Seguimiento - Real State", "Real State.")
        == "Seguimiento - Real State"
    )


def test_heading_without_cliente_strips_punctuation():
    assert compose_cliente_heading("Estrategia Rebella.,;", "") == "Estrategia Rebella"


# ---------------------------------------------------------------------------
# Display de responsable Gorila: espacios y normalización Growfik/Grofit
# ---------------------------------------------------------------------------


def test_responsable_dos_equipos_sin_doble_espacio():
    # DEFECT 1: equipos concatenados llegaban con doble espacio.
    assert (
        normalize_gorila_compromiso_responsable_display(
            "Marketing  Administración Gorila Hosting"
        )
        == "Marketing Administración Gorila Hosting"
    )
    # El armado canónico une los equipos con un separador claro.
    assert (
        infer_gorila_responsable(
            ["Marketing Gorila Hosting", "Administración Gorila Hosting"]
        )
        == "Marketing y Administración Gorila Hosting"
    )


def test_responsable_no_duplica_sufijo_gorila_hosting():
    assert (
        normalize_gorila_compromiso_responsable_display("Gorila Hosting Gorila Hosting")
        == "Gorila Hosting"
    )


def test_grofit_normaliza_a_gorila_hosting():
    # DEFECT 2: la errata "Grofit"/"Grofik" debe tratarse como "Growfik".
    assert (
        normalize_gorila_compromiso_responsable_display("Grofit")
        == "Gorila Hosting"
    )
    assert (
        normalize_gorila_compromiso_responsable_display("Tarea para Grofik mañana")
        == "Tarea para Gorila Hosting mañana"
    )
