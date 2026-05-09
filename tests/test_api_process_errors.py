from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.app import app
from src.exceptions import LLMExtractionError


@pytest.fixture
def client():
    return TestClient(app)


def test_llm_failure_returns_safe_user_message_no_raw_leak(client: TestClient):
    raw_secret = "no soy json completo con basura del modelo"
    with patch(
        "api.app.run_acta_pipeline",
        side_effect=LLMExtractionError(technical_details=raw_secret),
    ), patch("api.app._DEBUG", False):
        res = client.post(
            "/api/process",
            files={"file": ("notas.docx", b"PK\x03\x04fake", "application/octet-stream")},
        )
    assert res.status_code == 502
    data = res.json()
    assert data["error_code"] == "LLM_EXTRACTION_FAILED"
    assert raw_secret not in data["user_message"]
    assert "technical_details" not in data
    full = res.text
    assert raw_secret not in full
    assert "reintentando" in data["user_message"].lower()
    assert data.get("request_id")


def test_llm_failure_includes_technical_details_when_debug(client: TestClient):
    raw_secret = "no soy json"
    with patch(
        "api.app.run_acta_pipeline",
        side_effect=LLMExtractionError(technical_details=raw_secret),
    ), patch("api.app._DEBUG", True):
        res = client.post(
            "/api/process",
            files={"file": ("notas.docx", b"x", "application/octet-stream")},
        )
    assert res.status_code == 502
    data = res.json()
    assert data.get("technical_details") == raw_secret


def test_invalid_extension_returns_422_structured(client: TestClient):
    with patch("api.app._DEBUG", False):
        res = client.post(
            "/api/process",
            files={"file": ("x.pdf", b"%PDF", "application/pdf")},
        )
    assert res.status_code == 422
    data = res.json()
    assert data["error_code"] == "INVALID_FILE_TYPE"
    assert "request_id" in data
