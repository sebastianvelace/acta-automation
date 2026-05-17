from __future__ import annotations

from src.aliases import (
    build_compromisos_from_proximos_pasos,
    finalize_acta_after_llm,
    infer_gorila_responsable,
)
from src.parser import extract_proximos_pasos_items

REAL_STATE_NOTES_SNIPPET = """
may 15, 2026
Revisión Pauta  - Real State

Próximos pasos
[Marco Gonzalez] Formalizar estrategia: Formalizar la estrategia de pauta inicial en un documento que detalle el tipo de contenido y anuncios requeridos para la fase de reconocimiento de marca.
[Marco Gonzalez] Enviar referencias: Enviar al equipo de trabajo las referencias visuales y de video para la creación de contenido publicitario alineado con la identidad de marca.
[El grupo] Evaluar portales: Evaluar internamente el alcance y la viabilidad de pautar en portales especializados como Finca Raíz o Metro Cuadrado para futuras etapas.

Detalles
foo
"""


def test_extract_proximos_pasos_real_state_fixture() -> None:
    items = extract_proximos_pasos_items(REAL_STATE_NOTES_SNIPPET)
    assert len(items) == 3
    assert items[0]["tag"] == "Marco Gonzalez"
    assert "Formalizar la estrategia de pauta inicial" in items[0]["descripcion"]
    assert items[2]["tag"] == "El grupo"
    assert "Finca Raíz" in items[2]["descripcion"]


def test_infer_gorila_responsable_marketing_admin() -> None:
    assert (
        infer_gorila_responsable(
            ["Administración Gorila Hosting", "Marketing Gorila Hosting"],
        )
        == "Marketing & Administración Gorila Hosting"
    )


def test_infer_grupo_skips_social_media_when_m_and_a_present() -> None:
    teams = [
        "Marketing Gorila Hosting",
        "Administración Gorila Hosting",
        "Social Media Gorila Hosting",
    ]
    assert (
        infer_gorila_responsable(teams, for_grupo_task=True)
        == "Marketing & Administración Gorila Hosting"
    )
    joined = infer_gorila_responsable(teams, for_grupo_task=False)
    assert "Social Media" in joined


def test_build_compromisos_from_proximos_real_state() -> None:
    items = extract_proximos_pasos_items(REAL_STATE_NOTES_SNIPPET)
    teams = ["Marketing Gorila Hosting", "Administración Gorila Hosting"]
    g, c = build_compromisos_from_proximos_pasos(items, teams)
    assert len(g) == 1
    assert "Evaluar internamente el alcance" in g[0]["tarea"]
    assert g[0]["responsable"] == "Marketing & Administración Gorila Hosting"
    assert len(c) == 2
    assert all(row["responsable"] == "Marco Gonzalez" for row in c)
    assert any("Formalizar la estrategia de pauta inicial" in row["tarea"] for row in c)
    assert any("referencias visuales" in row["tarea"] for row in c)


def test_finalize_overrides_compromisos_and_filters_team_attendees() -> None:
    data = {
        "titulo": "Revisión Pauta",
        "fecha": "15 de mayo de 2026",
        "hora_inicio": "x",
        "hora_fin": "y",
        "lugar": "z",
        "cliente": "Real State",
        "objetivo": "o",
        "cierre": "",
        "asistentes": [
            {"nombre": "Camilo Linares Jiménez", "puesto": "Marketing Gorila Hosting"},
            {"nombre": "Marco Gonzalez", "puesto": "Administración Gorila Hosting"},
            {"nombre": "ads.gorilahosting@gmail.com", "puesto": "Social Media Gorila Hosting"},
        ],
        "asuntos_tratados": [],
        "compromisos_gorila": [],
        "compromisos_cliente": [],
    }
    items = extract_proximos_pasos_items(REAL_STATE_NOTES_SNIPPET)
    teams = ["Marketing Gorila Hosting", "Administración Gorila Hosting"]
    out = finalize_acta_after_llm(
        data,
        REAL_STATE_NOTES_SNIPPET,
        proximos_items=items,
        gorila_teams=teams,
    )
    assert len(out["asistentes"]) == 2
    by_n = {a["nombre"]: a["puesto"] for a in out["asistentes"]}
    assert by_n["Camilo Linares Jiménez"] == "Marketing Gorila Hosting"
    assert by_n["Marco Gonzalez"] == "Administración Gorila Hosting"
    assert len(out["compromisos_gorila"]) == 1
    assert len(out["compromisos_cliente"]) == 2
