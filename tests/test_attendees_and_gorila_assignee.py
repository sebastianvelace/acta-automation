from __future__ import annotations

from src.aliases import (
    build_invitados_from_attendee_emails,
    build_compromisos_from_proximos_pasos,
    is_internal_gorila_assignee,
    reclassify_compromisos,
)
from src.parser import extract_gorila_person_names


def test_build_invitados_from_attendee_emails() -> None:
    rows = build_invitados_from_attendee_emails(
        ["a@cliente.com", "A@cliente.com", "b@gorilahosting.com"]
    )
    assert len(rows) == 2
    assert rows[0]["correo"] == "a@cliente.com"
    assert rows[0]["nombre"] == "A"
    assert rows[1]["nombre"] == "B"
    assert rows[0]["asistencia"] == "Confirmado"
    assert rows[0]["puesto"] == "Cliente"


def test_extract_gorila_person_names_from_detalles() -> None:
    text = """
Detalles
Camilo Linares Jiménez (Marketing Gorila Hosting) presentó el informe.
Marco Gonzalez comentó la estrategia del cliente.
"""
    names = extract_gorila_person_names(text)
    assert "Camilo Linares Jiménez" in names
    assert "Marco Gonzalez" not in names


def test_internal_gorila_assignee_by_name_and_email() -> None:
    meta_names = ["Camilo Linares Jiménez"]
    meta_emails = ["camilolinaresj@gmail.com"]
    assert is_internal_gorila_assignee(
        "Camilo Linares",
        gorila_person_names=meta_names,
        gorila_emails=meta_emails,
    )
    assert is_internal_gorila_assignee("Marco Gonzalez")
    assert not is_internal_gorila_assignee(
        "Pedro Cliente Externo",
        gorila_person_names=meta_names,
        gorila_emails=meta_emails,
    )


def test_build_compromisos_routes_gorila_person_to_gorila() -> None:
    items = [
        {
            "tag": "Camilo Linares",
            "titulo_corto": "Enviar informe",
            "descripcion": "Enviar informe mensual al cliente.",
        },
        {
            "tag": "Marco Gonzalez",
            "titulo_corto": "Aprobar",
            "descripcion": "Aprobar la propuesta comercial.",
        },
    ]
    g, c = build_compromisos_from_proximos_pasos(
        items,
        ["Marketing Gorila Hosting"],
        gorila_person_names=["Camilo Linares Jiménez"],
        gorila_emails=["camilolinaresj@gmail.com"],
    )
    assert len(g) == 2
    assert {r["responsable"] for r in g} == {"Camilo Linares", "Marco Gonzalez"}
    assert c == []


def test_reclassify_moves_gorila_person_from_cliente() -> None:
    gorila, cliente = reclassify_compromisos(
        [],
        [
            {
                "tarea": "Preparar creativos",
                "responsable": "Camilo Linares",
                "fecha_entrega": "No especificada",
            }
        ],
        gorila_person_names=["Camilo Linares Jiménez"],
        gorila_emails=["camilolinaresj@gmail.com"],
    )
    assert len(gorila) == 1
    assert gorila[0]["responsable"] == "Camilo Linares"
    assert cliente == []
