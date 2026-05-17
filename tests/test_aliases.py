from __future__ import annotations

import pytest

from src.aliases import (
    TEAM_ALIASES,
    compose_cliente_heading,
    is_gorila_responsable,
    lookup_team_alias,
    normalize_attendee,
    post_process_acta,
    reclassify_compromisos,
)


@pytest.mark.parametrize(
    "alias_key",
    list(TEAM_ALIASES.keys()),
    ids=list(TEAM_ALIASES.keys()),
)
def test_team_alias_normalize_attendee_exact(alias_key: str) -> None:
    expected = TEAM_ALIASES[alias_key]
    assert normalize_attendee(alias_key) == expected


def test_team_alias_case_insensitive() -> None:
    assert normalize_attendee("marketing gorila hosting") == TEAM_ALIASES["Marketing Gorila Hosting"]


def test_normalize_email_plain() -> None:
    assert normalize_attendee("maria.lopez@cliente.com") == {
        "nombre": "Maria Lopez",
        "puesto": "cliente.com",
    }


def test_normalize_human_name_two_tokens() -> None:
    assert normalize_attendee("Pérez García Luis") == {
        "nombre": "Pérez García Luis",
        "puesto": "No especificado",
    }


def test_normalize_single_token_fallback() -> None:
    out = normalize_attendee("Interno")
    assert out["nombre"] == "Interno"
    assert out["puesto"] == "No especificado"


def test_post_process_rewrites_llm_asistente_row() -> None:
    raw = {
        "titulo": "t",
        "fecha": "1",
        "hora_inicio": "x",
        "hora_fin": "y",
        "lugar": "z",
        "cliente": "c",
        "objetivo": "o",
        "cierre": "",
        "asistentes": [
            {"nombre": "Social Media Gorila Hosting", "puesto": "No especificado"}
        ],
        "asuntos_tratados": [{"titulo": "a", "descripcion": "b"}],
        "compromisos_gorila": [],
        "compromisos_cliente": [],
    }
    out = post_process_acta(raw)
    assert out["asistentes"][0] == {"nombre": "Social Media", "puesto": "Gorila Hosting"}


def test_lookup_team_alias_unknown() -> None:
    assert lookup_team_alias("Persona Real") is None


def test_compose_cliente_heading_meeting_plus_account() -> None:
    assert compose_cliente_heading("Revisión Pauta", "Real State") == "Revisión Pauta - Real State"


def test_compose_cliente_heading_preserves_full_cliente() -> None:
    full = "Seguimiento - Eventos & Matrimonios"
    assert compose_cliente_heading("Fixture titulo", full) == full


def test_compose_cliente_heading_avoids_duplicate_suffix() -> None:
    assert compose_cliente_heading("Revisión Pauta - Real State", "Real State") == (
        "Revisión Pauta - Real State"
    )


def test_is_gorila_responsable_team_alias() -> None:
    assert is_gorila_responsable("Marketing Gorila Hosting")
    assert not is_gorila_responsable("Marco Gonzalez")
    assert not is_gorila_responsable("Eventos y Matrominios Portal")


def test_reclassify_moves_person_to_cliente() -> None:
    gorila, cliente = reclassify_compromisos(
        [
            {
                "tarea": "Formalizar estrategia",
                "responsable": "Marco Gonzalez",
                "fecha_entrega": "No especificada",
            }
        ],
        [],
    )
    assert gorila == []
    assert len(cliente) == 1
    assert cliente[0]["responsable"] == "Marco Gonzalez"


def test_reclassify_group_only_gorila() -> None:
    item = {
        "tarea": "Evaluar portales",
        "responsable": "[El grupo]",
        "fecha_entrega": "No especificada",
    }
    gorila, cliente = reclassify_compromisos([item], [])
    assert len(gorila) == 1
    assert len(cliente) == 0
    assert gorila[0]["tarea"] == "Evaluar portales"
    assert gorila[0]["responsable"] == "Gorila Hosting"


def test_post_process_compromisos_real_state_scenario() -> None:
    raw = {
        "titulo": "Revisión Pauta",
        "fecha": "15 de mayo de 2026",
        "hora_inicio": "x",
        "hora_fin": "y",
        "lugar": "z",
        "cliente": "Real State",
        "objetivo": "o",
        "cierre": "",
        "asistentes": [],
        "asuntos_tratados": [{"titulo": "a", "descripcion": "b"}],
        "compromisos_gorila": [
            {
                "tarea": "Formalizar estrategia",
                "responsable": "Marco Gonzalez",
                "fecha_entrega": "No especificada",
            },
            {
                "tarea": "Evaluar portales",
                "responsable": "El grupo",
                "fecha_entrega": "No especificada",
            },
        ],
        "compromisos_cliente": [],
    }
    meta = {
        "gorila_teams": ["Marketing Gorila Hosting", "Administración Gorila Hosting"],
    }
    out = post_process_acta(raw, metadata=meta)
    assert out["cliente"] == "Revisión Pauta - Real State"
    assert len(out["compromisos_gorila"]) == 1
    assert out["compromisos_gorila"][0]["tarea"] == "Evaluar portales"
    assert (
        out["compromisos_gorila"][0]["responsable"]
        == "Marketing & Administración Gorila Hosting"
    )
    assert len(out["compromisos_cliente"]) == 1
    assert out["compromisos_cliente"][0]["tarea"] == "Formalizar estrategia"
    assert out["compromisos_cliente"][0]["responsable"] == "Marco Gonzalez"
