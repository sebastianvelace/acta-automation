"""
Local REST API for the acta pipeline.
Run from repo root: python -m uvicorn api.app:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import base64
import os
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from src.pipeline import run_acta_pipeline

load_dotenv()

_MAX_UPLOAD_MB = 25

app = FastAPI(title="Acta automation", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/process")
async def process_meeting_notes(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=400,
            detail="Sube un archivo .docx (notas Gemini).",
        )

    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Archivo demasiado grande (máx. {_MAX_UPLOAD_MB} MB).",
        )

    tmpdir = tempfile.mkdtemp(prefix="acta-upload-")
    outdir = tempfile.mkdtemp(prefix="acta-out-")

    upload_path = os.path.join(tmpdir, Path(file.filename).name)

    try:
        with open(upload_path, "wb") as f:
            f.write(raw)

        try:
            result = run_acta_pipeline(
                upload_path,
                source_filename=file.filename,
                output_dir=outdir,
                keep_docx=True,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error al generar el acta: {e!s}",
            ) from e

        with open(result["pdf_path"], "rb") as f:
            pdf_b64 = base64.standard_b64encode(f.read()).decode("ascii")

        docx_b64: str | None = None
        if result["docx_path"]:
            with open(result["docx_path"], "rb") as f:
                docx_b64 = base64.standard_b64encode(f.read()).decode("ascii")

        return {
            "metadata": result["metadata"],
            "acta": result["acta"],
            "output_base_name": result["output_name"],
            "pdf_base64": pdf_b64,
            "docx_base64": docx_b64,
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        shutil.rmtree(outdir, ignore_errors=True)
