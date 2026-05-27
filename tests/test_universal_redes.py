"""Tests del acta Redes - Universal Idiomas (post-proceso determinístico)."""

from __future__ import annotations

import os

from src.aliases import (
    build_compromisos_from_proximos_pasos,
    compose_cliente_heading,
    finalize_acta_after_llm,
)
from src.gorila_roster import invitado_fields_from_email, load_gorila_staff

UNIVERSAL_REDES_PATH = (
    "/home/sebasvelace/Downloads/Redes - Universal Idiomas._ "
    "2026_05_26 16_02 GMT-05_00 - Notas de Gemini.docx"
)

UNIVERSAL_REDES_PROXIMOS = """
Próximos pasos
[Social Media Gorila Hosting] Enviar piezas promocionales: Enviar al grupo las piezas promocionales listas para la próxima semana.
[Social Media Gorila Hosting] Ajustar contenido organico: Modificar los diseños de contenido orgánico eliminando la marca explicita.
[Gresly Growfik] Enviar imagenes carrusel: Compartir las imagenes del carrusel de votaciones.
[Sophia7 Marketing] Definir orden carrusel: Revisar las imagenes enviadas y determinar el orden correcto.
[Social Media Gorila Hosting] Compartir enlaces plantillas: Compartir los enlaces de las plantillas.
[Gresly Growfik] Actualizar parrilla contenido: Agregar el material ajustado a la parrilla de publicaciones programadas.
"""


def test_compose_cliente_heading_strips_trailing_punctuation() -> None:
    assert compose_cliente_heading("Redes - Universal Idiomas.", "Universal Idiomas.") == (
        "Redes - Universal Idiomas"
    )


def test_gresly_growfik_local_part_universal_puesto() -> None:
    load_gorila_staff.cache_clear()
    row = invitado_fields_from_email("community1.growfik@gmail.com", universal=True)
    assert row["nombre"] == "Gresly"
    assert "Growfik" in row["puesto"]


def test_universal_redes_compromisos_routing() -> None:
    from src.parser import extract_proximos_pasos_items

    items = extract_proximos_pasos_items(UNIVERSAL_REDES_PROXIMOS)
    g, c = build_compromisos_from_proximos_pasos(
        items,
        ["Social Media Gorila Hosting", "Marketing Gorila Hosting"],
        cliente_responsable="Universal Idiomas",
        universal=True,
    )
    assert len(g) == 5
    assert len(c) == 1
    gresly_rows = [r for r in g if r["responsable"] == "Gresly"]
    assert len(gresly_rows) == 2
    assert "Growfik" not in gresly_rows[0]["responsable"]
    assert c[0]["responsable"] == "Sophia7 Marketing"


def test_universal_redes_finalize_invitados() -> None:
    from src.parser import extract_proximos_pasos_items

    load_gorila_staff.cache_clear()
    items = extract_proximos_pasos_items(UNIVERSAL_REDES_PROXIMOS)
    out = finalize_acta_after_llm(
        {
            "titulo": "Redes - Universal Idiomas.",
            "fecha": "26 de mayo de 2026",
            "hora_inicio": "4:02 PM",
            "hora_fin": "No especificada",
            "lugar": "Google meet",
            "cliente": "Universal Idiomas.",
            "objetivo": "Revisar estrategia.",
            "cierre": "Cierre.",
            "invitados": [],
            "asuntos_tratados": [],
            "compromisos_gorila": [],
            "compromisos_cliente": [],
        },
        UNIVERSAL_REDES_PROXIMOS,
        proximos_items=items,
        metadata={
            "attendee_emails": [
                "community1.growfik@gmail.com",
                "gorilahosting@gmail.com",
                "sophiabellomendez@gmail.com",
                "annyriios27@gmail.com",
            ],
            "gorila_teams": [
                "Administración Gorila Hosting",
                "Social Media Gorila Hosting",
                "Marketing Gorila Hosting",
                "Redes Gorila Hosting",
            ],
            "gorila_emails": [
                "community1.growfik@gmail.com",
                "gorilahosting@gmail.com",
            ],
        },
        source_filename=UNIVERSAL_REDES_PATH,
    )
    assert out["cliente"] == "Redes - Universal Idiomas"
    by_email = {i["correo"].casefold(): i for i in out["invitados"]}
    assert by_email["community1.growfik@gmail.com"]["nombre"] == "Gresly"
    assert "Growfik" in by_email["community1.growfik@gmail.com"]["puesto"]
    assert by_email["sophiabellomendez@gmail.com"]["nombre"] == "Sophia Bello Mendez"
    assert by_email["annyriios27@gmail.com"]["nombre"] == "Anny Valoyes"
    assert len(out["compromisos_gorila"]) == 5
    assert len(out["compromisos_cliente"]) == 1


def test_universal_redes_real_doc_batch_grade() -> None:
    if not os.path.isfile(UNIVERSAL_REDES_PATH):
        return
    from scripts.batch_grade import build_deterministic_acta, score_compromisos, score_encabezado, score_invitados, titulo_from_filename

    load_gorila_staff.cache_clear()
    acta, meta = build_deterministic_acta(UNIVERSAL_REDES_PATH)
    titulo = titulo_from_filename(UNIVERSAL_REDES_PATH)
    assert score_encabezado(acta, meta, titulo) == 10.0
    assert score_invitados(acta, meta) == 10.0
    assert score_compromisos(acta, (5, 1)) == 10.0
