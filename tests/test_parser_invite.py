from __future__ import annotations

from pathlib import Path

from docx import Document

from src.parser import _extract_times_from_filename, extract_text


def test_extract_times_from_filename_space_format() -> None:
    hora, fin = _extract_times_from_filename(
        "Actualización Dashboard - Universal _ 2026_05_21 11_02 GMT-05_00 - Notas de Gemini.docx"
    )
    assert hora == "11:02 AM"
    assert fin == ""


def test_extract_text_populates_gorila_teams_and_emails(tmp_path: Path) -> None:
    doc = Document()
    doc.add_paragraph(
        "Invitado camilolinaresj@gmail.com Marketing Gorila Hosting "
        "Administración Gorila Hosting ads@gorilahosting@gmail.com Social Media Gorila Hosting"
    )
    doc.add_paragraph("Archivos adjuntos x")
    p = tmp_path / "invite.docx"
    doc.save(str(p))
    out = extract_text(str(p))
    meta = out["metadata"]
    assert "camilolinaresj@gmail.com" in meta["attendee_emails"]
    assert "camilolinaresj@gmail.com" in meta["client_emails"]
    assert "gorilahosting@gmail.com" in meta["attendee_emails"]
    assert "gorilahosting@gmail.com" in meta["gorila_emails"]
    assert "Marketing Gorila Hosting" in meta["gorila_teams"]
    assert "Administración Gorila Hosting" in meta["gorila_teams"]
