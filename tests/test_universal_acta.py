"""Tests del acta Universal (post-proceso determinístico, sin Groq)."""

from __future__ import annotations

import os

from src.aliases import build_compromisos_from_proximos_pasos, finalize_acta_after_llm
from src.google_workflow import apply_metadata_times_to_acta
from src.parser import _extract_times_from_filename, extract_proximos_pasos_items, extract_text

REPORTE_VENTAS_PATH = (
    "/home/sebasvelace/Downloads/Reunión Reporte de Ventas - Universal _ "
    "2026_05_25 15_59 GMT-05_00 - Notas de Gemini.docx"
)

REPORTE_VENTAS_PROXIMOS = """
Próximos pasos
[PEDRO ANTONIO RODRIGUEZ HERNANDEZ] Compartir informe: Enviar el reporte de corte de abril al equipo.
[PEDRO ANTONIO RODRIGUEZ HERNANDEZ] Consultar con Tatiana: Contactar a Tatiana para validar la metodología.
"""

UNIVERSAL_PROXIMOS = """
Próximos pasos
[Omar Escobedo] Validar metodología Tatiana: Coordinar una reunión con Tatiana para validar la metodología.
[Omar Escobedo] Programar nota 1 y 2: Incorporar la lógica de negocio para los campos nota 1 y nota 2.
[Omar Escobedo] Agregar filtro periodo: Implementar una funcionalidad de selección de fechas en el tablero.
[Marketing Gorila Hosting] Llamar a Pedro: Realizar una llamada telefónica a Pedro para gestionar un tema.
[Marketing Gorila Hosting] Programar reunión: Convocar a una sesión de seguimiento con Pedro para mañana a las 2PM.
"""

UNIVERSAL_FILENAME = (
    "Actualización Dashboard - Universal _ 2026_05_21 11_02 GMT-05_00 - Notas de Gemini.docx"
)


def test_filename_hora_universal_format() -> None:
    hora, _ = _extract_times_from_filename(UNIVERSAL_FILENAME)
    assert hora == "11:02 AM"


def test_omar_compromisos_route_to_gorila_not_cliente() -> None:
    items = extract_proximos_pasos_items(UNIVERSAL_PROXIMOS)
    g, c = build_compromisos_from_proximos_pasos(
        items,
        ["Marketing Gorila Hosting"],
        cliente_responsable="Universal",
        meeting_date_str="21 de mayo de 2026",
    )
    omar_rows = [r for r in g if r["responsable"] == "Omar Escobedo"]
    assert len(omar_rows) == 3
    assert all("; " not in r["tarea"] for r in g + c)
    assert "Validar metodología" in omar_rows[0]["tarea"] or "Coordinar una reunión" in omar_rows[0]["tarea"]
    assert all(r["responsable"] != "Universal" for r in g)
    assert not any("Omar" in r["responsable"] for r in c)


def test_manana_fecha_entrega_from_proximos() -> None:
    items = extract_proximos_pasos_items(UNIVERSAL_PROXIMOS)
    g, _ = build_compromisos_from_proximos_pasos(
        items,
        ["Marketing Gorila Hosting"],
        meeting_date_str="21 de mayo de 2026",
    )
    reunion = next(r for r in g if "mañana" in r["tarea"].casefold() or "2PM" in r["tarea"])
    assert reunion["fecha_entrega"] == "22 de mayo de 2026, 2:00 PM"


def test_finalize_adds_omar_to_invitados_from_proximos_tags() -> None:
    items = extract_proximos_pasos_items(UNIVERSAL_PROXIMOS)
    out = finalize_acta_after_llm(
        {
            "titulo": "Actualización Dashboard",
            "fecha": "21 de mayo de 2026",
            "hora_inicio": "11:02 AM",
            "hora_fin": "No especificada",
            "lugar": "Google meet",
            "cliente": "Universal",
            "objetivo": "Revisar tablero.",
            "cierre": "Cierre.",
            "invitados": [],
            "asuntos_tratados": [],
            "compromisos_gorila": [],
            "compromisos_cliente": [],
        },
        UNIVERSAL_PROXIMOS,
        proximos_items=items,
        metadata={
            "attendee_emails": [
                "davidgutierrez@growfik.com",
                "samuel.villalobos@universal.edu.co",
            ],
            "gorila_teams": ["Marketing Gorila Hosting"],
            "gorila_emails": ["davidgutierrez@growfik.com"],
        },
    )
    nombres = {i["nombre"] for i in out["invitados"]}
    assert "Omar Escobedo" in nombres
    assert "David Gutiérrez" in nombres
    assert "Samuel Villalobos" in nombres
    david = next(i for i in out["invitados"] if i["correo"] == "davidgutierrez@growfik.com")
    assert "Growfik" in david["puesto"]


def test_reporte_ventas_pedro_name_from_contacts_yaml() -> None:
    items = extract_proximos_pasos_items(REPORTE_VENTAS_PROXIMOS)
    out = finalize_acta_after_llm(
        {
            "titulo": "Reunión Reporte de Ventas - Universal",
            "fecha": "25 de mayo de 2026",
            "hora_inicio": "No especificada",
            "hora_fin": "No especificada",
            "lugar": "No especificada",
            "cliente": "Universal",
            "objetivo": "Revisar informes.",
            "cierre": "Cierre.",
            "invitados": [],
            "asuntos_tratados": [],
            "compromisos_gorila": [],
            "compromisos_cliente": [],
        },
        REPORTE_VENTAS_PROXIMOS,
        proximos_items=items,
        metadata={
            "attendee_emails": ["pedro.rodriguezh@universal.edu.co"],
            "gorila_teams": ["Marketing Gorila Hosting"],
            "gorila_emails": [],
        },
    )
    pedro = next(i for i in out["invitados"] if "pedro" in i["correo"].casefold())
    assert pedro["nombre"] == "Pedro Antonio Rodríguez Hernández"
    assert len(out["compromisos_cliente"]) == 2
    assert all(
        r["responsable"] == "Pedro Antonio Rodríguez Hernández"
        for r in out["compromisos_cliente"]
    )


def test_reporte_ventas_real_doc_metadata() -> None:
    if not os.path.isfile(REPORTE_VENTAS_PATH):
        return
    parsed = extract_text(REPORTE_VENTAS_PATH)
    meta = parsed["metadata"]
    assert meta["is_virtual"] is True
    assert meta["hora_inicio"] == ""
    out = apply_metadata_times_to_acta({"lugar": "No especificada"}, meta)
    assert out["lugar"] == "Google Meet"
