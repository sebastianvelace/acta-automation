"""Prueba determinística Barrera Estrada (sin Groq)."""

from __future__ import annotations

from src.aliases import (
    build_compromisos_from_proximos_pasos,
    build_invitados_from_attendee_emails,
    finalize_acta_after_llm,
)
from src.google_workflow import apply_metadata_times_to_acta
from src.parser import extract_proximos_pasos_items, extract_text, extract_gorila_person_names

BARRERA_DOCX = (
    "/home/sebasvelace/Downloads/Seguimiento Barrera Estrada_ "
    "2026_05_21 16_01 GMT-05_00 - Notas de Gemini.docx"
)

BARRERA_PROXIMOS = """
Próximos pasos
[Mariana] Remitir parrilla: Enviar el calendario de contenidos antes de las 5 de la tarde del día de mañana.
[El grupo] Espacio fotos: Generar un espacio compartido para organizar las fotografías de los empleados.
[Mariana] Cargar imágenes: Depositar las fotografías correspondientes a cada persona dentro del directorio recién creado.
[El grupo] Tarjeta aniversario: Modificar la fecha en la tarjeta de aniversario tras la confirmación de los nuevos tiempos.
[Mariana] Recordar tarea: Insistir al abogado sobre el envío pendiente del material de trabajo programado para mañana.
"""


def test_barrera_estrada_docx_parse_or_skip() -> None:
    try:
        parsed = extract_text(BARRERA_DOCX)
    except FileNotFoundError:
        import pytest

        pytest.skip("DOCX Barrera Estrada no disponible")
    meta = parsed["metadata"]
    assert meta["hora_inicio"] == "4:01 PM"
    assert "barreraestradaabogados@gmail.com" in meta["attendee_emails"]
    assert meta["gorila_person_names"] == []


def test_barrera_invitados_humanized_with_cliente_account() -> None:
    emails = [
        "barreraestradaabogados@gmail.com",
        "enythelvira@gmail.com",
        "abogado2@barreraestrada.com",
        "asistenteadministrativo1@barreraestrada.com",
        "asistenteadministrativo@barreraestrada.com",
        "gorilahosting@gmail.com",
    ]
    rows = build_invitados_from_attendee_emails(emails, cliente_account="Barrera Estrada")
    by_email = {r["correo"].casefold(): r for r in rows}
    assert by_email["enythelvira@gmail.com"]["nombre"] == "Enythelvira"
    assert by_email["barreraestradaabogados@gmail.com"]["nombre"] == "Barrera Estrada Abogados"
    assert by_email["barreraestradaabogados@gmail.com"]["puesto"] == "Cuenta corporativa"
    assert by_email["enythelvira@gmail.com"]["puesto"] == "Barrera Estrada Abogados"
    assert by_email["abogado2@barreraestrada.com"]["nombre"] == "Abogado 2"
    assert by_email["abogado2@barreraestrada.com"]["puesto"] == "Abogado"
    assert by_email["asistenteadministrativo@barreraestrada.com"]["nombre"] == "Asistente administrativo"
    assert by_email["asistenteadministrativo1@barreraestrada.com"]["nombre"] == "Asistente administrativo 1"
    assert by_email["asistenteadministrativo@barreraestrada.com"]["puesto"] == "Asistente administrativo"
    assert by_email["gorilahosting@gmail.com"]["nombre"] == "Martina Belén Tonelli"


def test_barrera_mariana_compromisos_go_to_cliente_account() -> None:
    items = extract_proximos_pasos_items(BARRERA_PROXIMOS)
    g, c = build_compromisos_from_proximos_pasos(
        items,
        ["Marketing Gorila Hosting", "Administración Gorila Hosting"],
        cliente_responsable="Barrera Estrada",
        meeting_date_str="21 de mayo de 2026",
    )
    assert len(g) == 2
    assert len(c) == 3
    assert all(r["responsable"] == "Barrera Estrada" for r in c)
    parrilla = next(r for r in c if "calendario de contenidos" in r["tarea"])
    assert parrilla["fecha_entrega"] == "22 de mayo de 2026, 5:00 PM"


def test_gorila_person_names_no_false_positives_from_details() -> None:
    snippet = """
Detalles
Estado de la parrilla de contenidos: Marketing Gorila Hosting manifiesta su preocupación.
Gestión de activos para cumpleaños: Social Media Gorila Hosting revisa el calendario.
"""
    assert extract_gorila_person_names(snippet) == []


def test_metadata_times_override_llm_placeholder() -> None:
    out = apply_metadata_times_to_acta(
        {"hora_inicio": "No especificada", "hora_fin": "No especificada"},
        {"hora_inicio": "4:01 PM", "hora_fin": ""},
    )
    assert out["hora_inicio"] == "4:01 PM"
    assert out["hora_fin"] == "5:01 PM"


def test_barrera_finalize_end_to_end_without_llm() -> None:
    items = extract_proximos_pasos_items(BARRERA_PROXIMOS)
    out = finalize_acta_after_llm(
        {
            "titulo": "Seguimiento Barrera Estrada",
            "fecha": "21 de mayo de 2026",
            "hora_inicio": "4:01 PM",
            "hora_fin": "No especificada",
            "lugar": "Google meet",
            "cliente": "Barrera Estrada",
            "objetivo": "Revisar contenidos.",
            "cierre": "Cierre.",
            "invitados": [],
            "asuntos_tratados": [],
            "compromisos_gorila": [],
            "compromisos_cliente": [],
        },
        BARRERA_PROXIMOS,
        proximos_items=items,
        metadata={
            "attendee_emails": ["enythelvira@gmail.com", "gorilahosting@gmail.com"],
            "gorila_teams": ["Marketing Gorila Hosting"],
            "gorila_emails": ["gorilahosting@gmail.com"],
            "gorila_person_names": [],
        },
    )
    assert out["cliente"] == "Seguimiento Barrera Estrada"
    assert len(out["compromisos_gorila"]) == 2
    assert len(out["compromisos_cliente"]) == 3
    by_nombre = {i["nombre"]: i for i in out["invitados"]}
    assert "Marketing" in by_nombre
    assert by_nombre["Enythelvira"]["correo"] == "enythelvira@gmail.com"
    patched = apply_metadata_times_to_acta(out, {"hora_inicio": "4:01 PM"})
    assert patched["hora_inicio"] == "4:01 PM"
