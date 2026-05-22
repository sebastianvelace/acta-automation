"""Golden batch determinístico para las 6 actas Gemini (sin Groq)."""

from __future__ import annotations

import pytest

from scripts.batch_grade import (
    DOCS,
    EXPECTED_COUNTS,
    build_deterministic_acta,
    grade_doc,
)


@pytest.mark.parametrize("label", list(DOCS))
def test_batch_doc_compromisos_counts(label: str) -> None:
    path = DOCS[label]
    try:
        acta, _ = build_deterministic_acta(path)
    except FileNotFoundError:
        pytest.skip(f"DOCX no disponible: {label}")
    eg, ec = EXPECTED_COUNTS[label]
    assert len(acta["compromisos_gorila"]) == eg, label
    assert len(acta["compromisos_cliente"]) == ec, label


@pytest.mark.parametrize("label", list(DOCS))
def test_batch_doc_minimum_score(label: str) -> None:
    path = DOCS[label]
    report = grade_doc(label, path)
    if report.get("skipped"):
        pytest.skip(report.get("reason", "docx missing"))
    scores = report["scores"]
    for dim in ("encabezado", "invitados", "compromisos"):
        assert scores[dim] >= 9.0, f"{label} {dim}={scores[dim]}"


def test_the_group_routes_to_gorila_only() -> None:
    from src.aliases import build_compromisos_from_proximos_pasos

    items = [
        {
            "tag": "The group",
            "titulo_corto": "Reagendar",
            "descripcion": "Gestionar la reprogramación de la reunión comercial.",
        }
    ]
    g, c = build_compromisos_from_proximos_pasos(items, ["Marketing Gorila Hosting"])
    assert len(g) == 1
    assert c == []


def test_ads_gorilahosting_invitado_has_gorila_puesto() -> None:
    from src.gorila_roster import invitado_fields_from_email

    row = invitado_fields_from_email("ads.gorilahosting@gmail.com")
    assert row["nombre"] == "Marco Gonzalez"
    assert "Gorila" in row["puesto"]
