from __future__ import annotations

import pytest

from src.aliases import TEAM_ALIASES, normalize_attendee, post_process_acta, lookup_team_alias


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
