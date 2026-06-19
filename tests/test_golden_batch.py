"""Regresión sobre los DOCX golden de scripts/batch_grade.py (determinístico, sin Groq)."""
from __future__ import annotations

import os

import pytest

from scripts.batch_grade import DOCS, EXPECTED_COUNTS, grade_doc

MIN_SCORE = 9.0


@pytest.mark.parametrize("label", list(DOCS), ids=list(DOCS))
def test_golden_doc_scores(label: str) -> None:
    path = DOCS[label]
    if not os.path.isfile(path):
        pytest.skip(f"docx no encontrado: {path}")
    result = grade_doc(label, path)
    assert not result.get("skipped"), result.get("reason")
    scores = result["scores"]
    assert scores["encabezado"] >= MIN_SCORE, result
    assert scores["invitados"] >= MIN_SCORE, result
    assert scores["compromisos"] >= MIN_SCORE, result
    counts = result["compromisos"]
    got = (counts["got_gorila"], counts["got_cliente"])
    assert got == EXPECTED_COUNTS[label], result
