from __future__ import annotations

import pytest

from src.aliases import (
    TEAM_ALIASES,
    apply_growfik_visibility_policy,
    build_compromisos_from_proximos_pasos,
    client_account_responsable,
    client_compromiso_responsable_from_tag,
    compose_cliente_heading,
    dedupe_asuntos_tratados,
    is_gorila_responsable,
    lookup_team_alias,
    merge_invitados_from_gorila_teams,
    normalize_attendee,
    post_process_acta,
    reclassify_compromisos,
)
from src.parser import extract_proximos_pasos_items


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


def test_post_process_keeps_invitados_empty_from_llm() -> None:
    raw = {
        "titulo": "t",
        "fecha": "1",
        "hora_inicio": "x",
        "hora_fin": "y",
        "lugar": "z",
        "cliente": "c",
        "objetivo": "o",
        "cierre": "",
        "invitados": [],
        "asuntos_tratados": [{"titulo": "a", "descripcion": "b"}],
        "compromisos_gorila": [],
        "compromisos_cliente": [],
    }
    out = post_process_acta(raw)
    assert out["invitados"] == []


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


def test_reclassify_normalizes_legacy_growfik_label() -> None:
    gorila, _ = reclassify_compromisos(
        [
            {
                "tarea": "Enviar informe",
                "responsable": "[Marketing Growfik]",
                "fecha_entrega": "No especificada",
            }
        ],
        [],
    )
    assert len(gorila) == 1
    assert "growfik" not in gorila[0]["responsable"].casefold()
    assert gorila[0]["responsable"] == "Marketing Gorila Hosting"


def test_reclassify_moves_person_to_cliente() -> None:
    gorila, cliente = reclassify_compromisos(
        [],
        [
            {
                "tarea": "Formalizar estrategia",
                "responsable": "Pedro Cliente Externo",
                "fecha_entrega": "No especificada",
            }
        ],
        cliente_responsable="Real State",
    )
    assert gorila == []
    assert len(cliente) == 1
    assert cliente[0]["responsable"] == "Pedro Cliente Externo"


def test_client_account_responsable_extracts_account_suffix() -> None:
    assert client_account_responsable("Revisión Pauta - Real State", "Revisión Pauta") == "Real State"
    assert (
        client_account_responsable("Seguimiento - Eventos & Matrimonios")
        == "Eventos & Matrimonios"
    )


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
        "invitados": [],
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
    assert len(out["compromisos_gorila"]) == 2
    marco_row = next(r for r in out["compromisos_gorila"] if r["tarea"] == "Formalizar estrategia")
    assert marco_row["responsable"] == "Marco Gonzalez"
    eval_row = next(r for r in out["compromisos_gorila"] if r["tarea"] == "Evaluar portales")
    assert eval_row["responsable"] == "Marketing & Administración Gorila Hosting"
    assert len(out["compromisos_cliente"]) == 0


REAL_STATE_PROXIMOS = """
Próximos pasos
[Marco Gonzalez] Formalizar estrategia: Formalizar la estrategia de pauta inicial en un documento.
[Marco Gonzalez] Enviar referencias: Enviar al equipo de trabajo las referencias visuales.
[El grupo] Evaluar portales: Evaluar internamente el alcance de pautar en portales especializados.
"""


def test_each_proximo_paso_is_one_table_row() -> None:
    items = extract_proximos_pasos_items(REAL_STATE_PROXIMOS)
    g, c = build_compromisos_from_proximos_pasos(
        items,
        ["Marketing Gorila Hosting", "Administración Gorila Hosting"],
    )
    assert len(g) + len(c) == len(items)
    for row in g + c:
        assert "; " not in row["tarea"]


def test_merge_invitados_from_gorila_teams() -> None:
    teams = [
        "Social Media Gorila Hosting",
        "Administración Gorila Hosting",
        "Marketing Gorila Hosting",
    ]
    email_rows = [
        {
            "correo": "camilolinaresj@gmail.com",
            "nombre": "Camilo Linares Jiménez",
            "puesto": "Real State",
            "asistencia": "Confirmado",
        }
    ]
    merged = merge_invitados_from_gorila_teams(email_rows, teams)
    assert len(merged) == 4
    assert merged[0]["nombre"] == "Administración"
    assert merged[0]["puesto"] == "Organizador"
    assert merged[1]["nombre"] == "Marketing"
    assert merged[2]["nombre"] == "Social Media"
    assert merged[3]["nombre"] == "Camilo Linares Jiménez"


def test_client_compromiso_responsable_all_caps_pedro() -> None:
    name = client_compromiso_responsable_from_tag(
        "PEDRO ANTONIO RODRIGUEZ HERNANDEZ",
        client_label="Universal",
    )
    assert name == "Pedro Antonio Rodríguez Hernández"


def test_dedupe_asuntos_substring_overlap() -> None:
    out = dedupe_asuntos_tratados(
        [
            {"titulo": "Estado del informe", "descripcion": "Corto."},
            {
                "titulo": "Estado del informe pendiente",
                "descripcion": "Descripción larga con más detalle del informe pendiente.",
            },
        ]
    )
    assert len(out) == 1
    assert "larga" in out[0]["descripcion"]


def test_scrub_growfik_non_universal() -> None:
    out = apply_growfik_visibility_policy(
        {
            "objetivo": "Coordinación con Growfik y Gorila.",
            "invitados": [{"nombre": "David", "puesto": "Analítica Growfik", "correo": "x@growfik.com"}],
        },
        universal=False,
    )
    assert "growfik" not in out["objetivo"].casefold()
    assert "Gorila Hosting" in out["objetivo"]
    assert "growfik" not in out["invitados"][0]["puesto"].casefold()


def test_universal_keeps_growfik_in_puesto() -> None:
    out = apply_growfik_visibility_policy(
        {"invitados": [{"nombre": "David", "puesto": "Analítica Growfik", "correo": "x@growfik.com"}]},
        universal=True,
    )
    assert "Growfik" in out["invitados"][0]["puesto"]
