"""Tests del roster fijo Gorila Hosting (data/gorila_staff.yaml)."""

from __future__ import annotations

import pytest

from src.aliases import build_compromisos_from_proximos_pasos, reclassify_compromisos
from src.gorila_roster import (
    invitado_fields_from_email,
    is_roster_member,
    load_gorila_staff,
    match_roster_member,
    roster_emails,
)
from src.parser import extract_proximos_pasos_items

REAL_STATE_NOTES = """
Próximos pasos
[Marco Gonzalez] Formalizar estrategia: Formalizar la estrategia de pauta inicial.
[Marco Gonzalez] Enviar referencias: Enviar referencias visuales al equipo.
[El grupo] Evaluar portales: Evaluar internamente el alcance en portales.
"""


@pytest.fixture
def staff_rows() -> list[dict]:
    return [
        {
            "canonical": m.canonical_name,
            "email": m.emails[0] if m.emails else "",
            "short": next((a for a in m.aliases if " " not in a), m.canonical_name.split()[0]),
        }
        for m in load_gorila_staff()
    ]


@pytest.mark.parametrize(
    "tag",
    [m.canonical_name for m in load_gorila_staff()],
    ids=[m.canonical_name for m in load_gorila_staff()],
)
def test_roster_canonical_names_match(tag: str) -> None:
    assert is_roster_member(tag)
    member = match_roster_member(tag)
    assert member is not None
    assert member.canonical_name == tag


@pytest.mark.parametrize("row", load_gorila_staff(), ids=lambda m: m.canonical_name)
def test_roster_email_matches(row) -> None:
    for email in row.emails:
        assert is_roster_member(email)
        assert match_roster_member(email).canonical_name == row.canonical_name


def test_roster_emails_include_gorila_hosting_domain() -> None:
    assert "ads@gorila.hosting" in roster_emails()
    assert "info@xenttia.com" in roster_emails()


def test_ambiguous_karen_alone_does_not_match() -> None:
    assert not is_roster_member("Karen")


def test_karen_patricia_matches() -> None:
    assert is_roster_member("Karen Patricia")
    assert match_roster_member("Karen Patricia Carvajal").canonical_name == (
        "Karen Patricia Carvajal Gómez"
    )


def test_karen_tatiana_matches() -> None:
    assert is_roster_member("Karen Tatiana Gonzalez")


def test_marco_gonzalez_always_gorila_in_proximos() -> None:
    items = extract_proximos_pasos_items(REAL_STATE_NOTES)
    g, c = build_compromisos_from_proximos_pasos(items, ["Marketing Gorila Hosting"])
    assert len(g) == 3
    assert len(c) == 0
    marco_rows = [r for r in g if "Marco" in r["responsable"]]
    assert len(marco_rows) == 2


def test_reclassify_moves_roster_member_from_cliente() -> None:
    g, c = reclassify_compromisos(
        [],
        [
            {
                "tarea": "Preparar pauta",
                "responsable": "Marco Gonzalez",
                "fecha_entrega": "No especificada",
            }
        ],
    )
    assert len(g) == 1
    assert g[0]["responsable"] == "Marco Gonzalez"
    assert c == []


def test_client_not_on_roster_stays_cliente() -> None:
    g, c = build_compromisos_from_proximos_pasos(
        [
            {
                "tag": "Pedro Cliente Externo",
                "titulo_corto": "x",
                "descripcion": "Entregar documentos al cliente.",
            }
        ],
        [],
        cliente_responsable="Real State",
    )
    assert g == []
    assert len(c) == 1
    assert c[0]["responsable"] == "Real State"


def test_omar_escobedo_routes_to_gorila() -> None:
    g, c = build_compromisos_from_proximos_pasos(
        [
            {
                "tag": "Omar Escobedo",
                "titulo_corto": "Validar",
                "descripcion": "Validar metodología Tatiana.",
            }
        ],
        [],
        cliente_responsable="Universal",
    )
    assert len(g) == 1
    assert g[0]["responsable"] == "Omar Escobedo"
    assert c == []


def test_growfik_email_enriches_invitado() -> None:
    row = invitado_fields_from_email("davidgutierrez@growfik.com")
    assert row["nombre"] == "David Gutiérrez"
    assert "Pauta" in row["puesto"] or "CRM" in row["puesto"]


@pytest.mark.parametrize("row", load_gorila_staff(), ids=lambda m: m.canonical_name)
def test_short_alias_when_unique(row) -> None:
    singles = [a for a in row.aliases if " " not in a.strip()]
    if not singles:
        return
    short = singles[0]
    others = [
        m
        for m in load_gorila_staff()
        if m.canonical_name != row.canonical_name
        and short.casefold() in {a.casefold() for a in m.aliases}
    ]
    if others:
        pytest.skip(f"alias {short!r} not unique across roster")
    assert is_roster_member(short)
