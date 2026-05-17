import json
from types import SimpleNamespace

import pytest

from src.llm import structure_meeting


def _minimal_acta_payload() -> dict:
    return {
        "titulo": "Reunión de prueba",
        "fecha": "1 de enero de 2026",
        "hora_inicio": "10:00 AM",
        "hora_fin": "11:00 AM",
        "lugar": "Virtual",
        "cliente": "Cliente demo",
        "objetivo": "Alinear próximos pasos.",
        "cierre": "Los equipos siguen reuniones próximas con entregables validados.",
        "asistentes": [{"nombre": "Ana", "puesto": "PM"}],
        "asuntos_tratados": [
            {"titulo": "1. Estado", "descripcion": "Se revisó el estado del proyecto."}
        ],
        "compromisos_gorila": [
            {
                "tarea": "Enviar informe",
                "responsable": "Marketing Gorila Hosting",
                "fecha_entrega": "No especificada",
            }
        ],
        "compromisos_cliente": [
            {
                "tarea": "Revisar propuesta",
                "responsable": "Cliente",
                "fecha_entrega": "No especificada",
            }
        ],
    }


def _patch_groq(monkeypatch: pytest.MonkeyPatch, response_text: str) -> None:
    class FakeGroq:
        def __init__(self, **kwargs: object) -> None:
            pass

        @property
        def chat(self) -> "FakeGroq":
            return self

        @property
        def completions(self) -> "FakeGroq":
            return self

        def create(self, **kwargs: object) -> SimpleNamespace:
            assert kwargs.get("response_format") == {"type": "json_object"}
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=response_text))
                ]
            )

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr("src.llm.Groq", FakeGroq)


def test_extract_json_from_markdown_fences(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _minimal_acta_payload()
    raw = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    _patch_groq(monkeypatch, raw)

    out = structure_meeting("notas mínimas", metadata={}, source_filename=None)

    assert out["titulo"] == payload["titulo"]
    assert out["asistentes"][0]["nombre"] == "Ana"


def test_extract_json_after_preamble(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _minimal_acta_payload()
    inner = json.dumps(payload, ensure_ascii=False)
    raw = f"Aquí está el JSON solicitado:\n\n{inner}\n\n(fin)"
    _patch_groq(monkeypatch, raw)

    out = structure_meeting("cuerpo", metadata=None, source_filename="x.docx")

    assert out["cliente"] == "Reunión de prueba - Cliente demo"
    assert len(out["compromisos_gorila"]) == 1


def test_extract_json_plain_json(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _minimal_acta_payload()
    raw = json.dumps(payload, ensure_ascii=False)
    _patch_groq(monkeypatch, raw)

    out = structure_meeting("", metadata={})

    assert out["fecha"] == payload["fecha"]
    assert out["asuntos_tratados"][0]["titulo"] == "1. Estado"
