"""Prueba determinística Seguimiento Real State (22 may 2026, sin Groq)."""

from __future__ import annotations

import os

import pytest

from src.aliases import build_compromisos_from_proximos_pasos, finalize_acta_after_llm
from src.google_workflow import apply_metadata_times_to_acta
from src.gorila_roster import invitado_fields_from_email
from src.parser import extract_proximos_pasos_items

REAL_STATE_DOCX = (
    "/home/sebasvelace/Downloads/Seguimiento - Real State _ "
    "2026_05_22 09_00 GMT-05_00 - Notas de Gemini.docx"
)

REAL_STATE_PROXIMOS = """
Próximos pasos
[Camilo Linares Jiménez] Enviar comentarios: Enviar los comentarios y correcciones sobre la parrilla de contenidos y los videos al grupo de WhatsApp del proyecto.
[Social Media Gorila Hosting] Actualizar diseño: Sustituir los apoyos visuales actuales por imágenes relacionadas con asesoría financiera o inversión. Ajustar el color del logo en las piezas gráficas según lo acordado.
[Camilo Linares Jiménez] Revisar y grabar: Revisar el guion de presentación compartido hoy para realizar ajustes y preparar la grabación. Entregar el material grabado siguiendo la organización por escenas en la carpeta compartida.
[Camilo Linares Jiménez] Revisar sitio web: Evaluar la versión preliminar de la página web una vez recibida la URL. Documentar cualquier modificación necesaria en un archivo Word para facilitar la edición del equipo web.
[Camilo Linares Jiménez] Revisar guion: Validar el contenido propuesto para asegurar su calidad.
[Camilo Linares Jiménez] Enviar inmuebles: Remitir la información completa de las propiedades para su procesamiento.
[El grupo] Notificar usuario: Informar al cliente cuando el proceso esté listo para la configuración de la tarjeta.
"""


def test_camilo_contact_from_yaml() -> None:
    row = invitado_fields_from_email("camilolinaresj@gmail.com", cliente_account="Real State")
    assert row["nombre"] == "Camilo Linares Jiménez"
    assert row["puesto"] == "Real State"


def test_compromisos_one_row_per_proximo() -> None:
    items = extract_proximos_pasos_items(REAL_STATE_PROXIMOS)
    g, c = build_compromisos_from_proximos_pasos(
        items,
        ["Administración Gorila Hosting", "Social Media Gorila Hosting", "Marketing Gorila Hosting"],
        cliente_responsable="Real State",
        meeting_date_str="22 de mayo de 2026",
    )
    assert len(items) == 7
    assert len(g) == 2
    assert len(c) == 5
    assert len(g) + len(c) == len(items)
    for row in g + c:
        assert "; " not in row["tarea"]
    assert all(r["responsable"] == "Real State" for r in c)
    assert any(r["responsable"] == "Social Media Gorila Hosting" for r in g)


def test_finalize_real_state_seguimiento_snippet() -> None:
    items = extract_proximos_pasos_items(REAL_STATE_PROXIMOS)
    out = finalize_acta_after_llm(
        {
            "titulo": "Seguimiento - Real State",
            "fecha": "may 22, 2026",
            "hora_inicio": "9:00 AM",
            "hora_fin": "No especificada",
            "lugar": "No especificada",
            "cliente": "Real State",
            "objetivo": "Stub.",
            "cierre": "Stub.",
            "invitados": [],
            "asuntos_tratados": [],
            "compromisos_gorila": [],
            "compromisos_cliente": [],
        },
        REAL_STATE_PROXIMOS,
        proximos_items=items,
        metadata={
            "attendee_emails": ["camilolinaresj@gmail.com"],
            "gorila_teams": [
                "Administración Gorila Hosting",
                "Social Media Gorila Hosting",
                "Marketing Gorila Hosting",
            ],
            "date": "may 22, 2026",
            "hora_inicio": "9:00 AM",
        },
    )
    assert out["cliente"] == "Seguimiento - Real State"
    assert len(out["compromisos_gorila"]) == 2
    assert len(out["compromisos_cliente"]) == 5
    assert len(out["invitados"]) == 4
    by_nombre = {i["nombre"]: i for i in out["invitados"]}
    assert by_nombre["Administración"]["puesto"] == "Organizador"
    assert by_nombre["Marketing"]["puesto"] == "Gorila Hosting"
    assert by_nombre["Social Media"]["puesto"] == "Gorila Hosting"
    assert by_nombre["Camilo Linares Jiménez"]["puesto"] == "Real State"
    patched = apply_metadata_times_to_acta(out, {"date": "may 22, 2026", "hora_inicio": "9:00 AM"})
    assert patched["fecha"] == "22 de mayo de 2026"
    assert patched["hora_inicio"] == "9:00 AM"
    assert patched["hora_fin"] == "10:00 AM"
    assert patched["hora_final"] == "10:00 AM"


@pytest.mark.skipif(not os.path.isfile(REAL_STATE_DOCX), reason="DOCX Real State no disponible")
def test_real_state_docx_batch_counts() -> None:
    from scripts.batch_grade import EXPECTED_COUNTS, build_deterministic_acta

    acta, _ = build_deterministic_acta(REAL_STATE_DOCX)
    eg, ec = EXPECTED_COUNTS["Real State Seguimiento"]
    assert len(acta["compromisos_gorila"]) == eg
    assert len(acta["compromisos_cliente"]) == ec
    assert acta["fecha"] == "22 de mayo de 2026"
    assert len(acta["invitados"]) == 4
    assert acta["hora_fin"] == "10:00 AM"


@pytest.mark.skipif(not os.path.isfile(REAL_STATE_DOCX), reason="DOCX Real State no disponible")
def test_real_state_e2e_groq_when_configured() -> None:
    import os

    if not os.environ.get("GROQ_API_KEY"):
        pytest.skip("GROQ_API_KEY no configurada")

    from src.pipeline import run_acta_pipeline

    result = run_acta_pipeline(REAL_STATE_DOCX, keep_docx=False, output_dir="/tmp/acta-real-state-pytest")
    acta = result["acta"]
    assert acta["fecha"] == "22 de mayo de 2026"
    assert len(acta["compromisos_gorila"]) == 2
    assert len(acta["compromisos_cliente"]) == 5
    objetivo = (acta.get("objetivo") or "").strip()
    cierre = (acta.get("cierre") or "").strip()
    assert objetivo and objetivo != "Stub."
    assert objetivo.split()[0].endswith("r") or objetivo[0].isupper()
    assert cierre and cierre != "Stub."
    asuntos = acta.get("asuntos_tratados") or []
    assert 9 <= len(asuntos) <= 13
    titulos = {str(a.get("titulo") or "").casefold() for a in asuntos}
    assert "revisión del contenido de mayo" in titulos
    assert "diseño y contenido de los reels" in titulos
