"""
Shared acta generation pipeline (file watcher CLI and HTTP API).
"""

from __future__ import annotations

import os
from typing import Any, TypedDict

from src.generator import generate_acta
from src.llm import structure_meeting
from src.parser import extract_text


def slugify(text: str) -> str:
    return text.lower().replace(" ", "_")


class ActaPipelineResult(TypedDict):
    metadata: dict[str, Any]
    acta: dict[str, Any]
    output_name: str
    pdf_path: str
    docx_path: str | None


def run_acta_pipeline(
    input_docx_path: str,
    *,
    source_filename: str | None = None,
    output_dir: str | None = None,
    keep_docx: bool = True,
) -> ActaPipelineResult:
    """
    Parse Gemini docx → LLM JSON → render PDF (optional DOCX).

    Does not move or delete ``input_docx_path``.
    """
    name = source_filename or os.path.basename(input_docx_path)

    parsed = extract_text(input_docx_path)
    data = structure_meeting(
        parsed["raw_text"],
        parsed["metadata"],
        source_filename=name,
    )
    output_name = slugify(data["titulo"])
    pdf_path = generate_acta(
        data,
        output_name,
        keep_docx=keep_docx,
        output_dir=output_dir,
    )

    docx_candidate = os.path.splitext(pdf_path)[0] + ".docx"
    if keep_docx and os.path.isfile(docx_candidate):
        docx_path: str | None = docx_candidate
    else:
        docx_path = None

    return ActaPipelineResult(
        metadata=parsed["metadata"],
        acta=data,
        output_name=output_name,
        pdf_path=pdf_path,
        docx_path=docx_path,
    )
