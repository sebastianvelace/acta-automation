"""
Shared acta generation pipeline (file watcher CLI and HTTP API).
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from typing import Any, NotRequired, TypedDict

from groq import APIConnectionError, BadRequestError, RateLimitError
from pydantic import ValidationError

from src.exceptions import (
    DocxParseError,
    LLMExtractionError,
    RenderError,
    SchemaValidationError,
)
from src.aliases import compose_cliente_heading, finalize_acta_after_llm
from src.generator import generate_acta
from src.llm import structure_meeting
from src.parser import extract_proximos_pasos_items, extract_text


def slugify(text: str) -> str:
    return text.lower().replace(" ", "_")


def _short_date(fecha: str) -> str:
    """Return '14 de mayo' from '14 de mayo de 2026'."""
    return re.sub(r"\s+de\s+\d{4}\s*$", "", fecha, flags=re.IGNORECASE).strip()


def build_output_name(titulo: str, fecha: str, cliente: str = "") -> str:
    """Build a human-readable filename without underscores.

    Example: 'Acta revisión pauta real state 15 de mayo'
    """
    heading = compose_cliente_heading(titulo, cliente)
    clean = re.sub(r"[-–—]", " ", heading)
    clean = re.sub(r'[<>:"/\\|?*&]', "", clean)
    clean = re.sub(r"\s+", " ", clean).strip().lower()
    short = _short_date(fecha)
    return f"Acta {clean} {short}"


class ActaPipelineResult(TypedDict):
    metadata: dict[str, Any]
    acta: dict[str, Any]
    output_name: str
    pdf_path: str
    docx_path: str | None
    timings: NotRequired[dict[str, float]]


def run_acta_pipeline(
    input_docx_path: str,
    *,
    source_filename: str | None = None,
    output_dir: str | None = None,
    keep_docx: bool = True,
    timings: dict[str, float] | None = None,
) -> ActaPipelineResult:
    """
    Parse Gemini docx → LLM JSON → render PDF (optional DOCX).

    Does not move or delete ``input_docx_path``.
    """
    name = source_filename or os.path.basename(input_docx_path)

    try:
        t0 = time.perf_counter()
        parsed = extract_text(input_docx_path)
        if timings is not None:
            timings["parse"] = time.perf_counter() - t0
    except Exception as e:
        raise DocxParseError(technical_details=str(e)) from e

    try:
        t0 = time.perf_counter()
        data = structure_meeting(
            parsed["raw_text"],
            parsed["metadata"],
            source_filename=name,
        )
        if timings is not None:
            timings["llm"] = time.perf_counter() - t0
    except ValidationError as e:
        raise SchemaValidationError(
            technical_details=_schema_details(e),
        ) from e
    except ValueError as e:
        raise LLMExtractionError(technical_details=str(e)) from e
    except (RateLimitError, APIConnectionError, BadRequestError) as e:
        raise LLMExtractionError(technical_details=str(e)) from e

    proximos = extract_proximos_pasos_items(parsed["raw_text"])
    data = finalize_acta_after_llm(
        data,
        parsed["raw_text"],
        proximos_items=proximos if proximos else None,
        gorila_teams=parsed["metadata"].get("gorila_teams") or [],
    )

    output_name = build_output_name(data["titulo"], data["fecha"], data.get("cliente", ""))

    try:
        t0 = time.perf_counter()
        pdf_path = generate_acta(
            data,
            output_name,
            keep_docx=keep_docx,
            output_dir=output_dir,
        )
        if timings is not None:
            timings["render"] = time.perf_counter() - t0
    except FileNotFoundError as e:
        raise RenderError(technical_details=str(e)) from e
    except subprocess.CalledProcessError as e:
        raise RenderError(
            technical_details=f"libreoffice failed (code {e.returncode}): {e!s}",
        ) from e
    except Exception as e:
        raise RenderError(technical_details=str(e)) from e

    docx_candidate = os.path.splitext(pdf_path)[0] + ".docx"
    if keep_docx and os.path.isfile(docx_candidate):
        docx_path: str | None = docx_candidate
    else:
        docx_path = None

    result: ActaPipelineResult = {
        "metadata": parsed["metadata"],
        "acta": data,
        "output_name": output_name,
        "pdf_path": pdf_path,
        "docx_path": docx_path,
    }
    if timings is not None:
        result["timings"] = dict(timings)
    return result


def _schema_details(exc: ValidationError) -> str:
    import json

    return json.dumps(exc.errors(), ensure_ascii=False)
