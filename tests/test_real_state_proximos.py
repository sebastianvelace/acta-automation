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
    assert "Evaluar internamente el alcance" in g[0]["tarea"] or any(
        "Evaluar internamente" in r["tarea"] for r in g
    )
    marco_rows = [r for r in g if r["responsable"] == "Marco Gonzalez"]
    assert len(marco_rows) == 2
    assert "Formalizar la estrategia" in marco_rows[0]["tarea"]
    assert "referencias" in marco_rows[1]["tarea"].casefold()
    assert len(c) == 0
    assert len(g) == 3
    assert all("; " not in r["tarea"] for r in g)


def test_finalize_overrides_compromisos_and_builds_email_invitados() -> None:
    data = {
        "titulo": "Revisión Pauta",
        "fecha": "15 de mayo de 2026",
        "hora_inicio": "x",
        "hora_fin": "y",
        "lugar": "z",
        "cliente": "Real State",
        "objetivo": "o",
        "cierre": "",
        "invitados": [],
        "asuntos_tratados": [],
        "compromisos_gorila": [],
        "compromisos_cliente": [],
    }
    items = extract_proximos_pasos_items(REAL_STATE_NOTES_SNIPPET)
    metadata = {
        "gorila_teams": ["Marketing Gorila Hosting", "Administración Gorila Hosting"],
        "attendee_emails": [
            "camilolinaresj@gmail.com",
            "marco.cliente@empresa.com",
        ],
        "gorila_emails": ["camilolinaresj@gmail.com"],
        "gorila_person_names": ["Camilo Linares Jiménez"],
    }
    out = finalize_acta_after_llm(
        data,
        REAL_STATE_NOTES_SNIPPET,
        proximos_items=items,
        metadata=metadata,
    )
    assert len(out["invitados"]) == 5
    by_nombre = {i["nombre"]: i for i in out["invitados"]}
    assert by_nombre["Administración"]["puesto"] == "Organizador"
    assert by_nombre["Marketing"]["puesto"] == "Gorila Hosting"
    camilo = next(i for i in out["invitados"] if i["correo"] == "camilolinaresj@gmail.com")
    assert camilo["nombre"] == "Camilo Linares Jiménez"
    assert camilo["puesto"] == "Real State"
    assert camilo["asistencia"] == "Confirmado"
    assert any(i["correo"] == "marco.cliente@empresa.com" for i in out["invitados"])
    marco_internal = next(i for i in out["invitados"] if i["nombre"] == "Marco Gonzalez")
    assert marco_internal["puesto"] == "Especialista Paid Media Google Meta Gorila"
    assert len(out["compromisos_gorila"]) == 3
    assert len(out["compromisos_cliente"]) == 0
