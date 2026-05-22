"""
Local REST API for the acta pipeline.
Run from repo root: python -m uvicorn api.app:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.exceptions import ActaError, FileTooLargeError, InvalidFileTypeError
from src.pipeline import run_acta_pipeline

load_dotenv()

_MAX_UPLOAD_MB = 25
_DEBUG = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")

logger = logging.getLogger("acta.api")

app = FastAPI(title="Acta automation", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    return await call_next(request)


@app.exception_handler(ActaError)
async def acta_error_handler(request: Request, exc: ActaError):
    rid = getattr(request.state, "request_id", None) or "unknown"
    payload: dict = {
        "error_code": exc.error_code,
        "user_message": exc.user_message,
        "request_id": rid,
    }
    if _DEBUG and exc.technical_details:
        payload["technical_details"] = exc.technical_details

    timings = getattr(request.state, "acta_timings", None) or {}
    t0 = getattr(request.state, "acta_t0", None)
    total_s = (time.perf_counter() - t0) if t0 is not None else None
    filename = getattr(request.state, "acta_filename", None)
    file_size = getattr(request.state, "acta_file_size", None)
    logger.warning(
        "[request_id=%s] acta_error error_code=%s http_status=%s filename=%r size=%s "
        "user_message=%r latency_total_s=%s latency_parse_s=%s latency_llm_s=%s latency_render_s=%s",
        rid,
        exc.error_code,
        exc.http_status,
        filename,
        file_size,
        exc.user_message,
        f"{total_s:.3f}" if total_s is not None else None,
        round(timings.get("parse", 0.0), 3) if timings else None,
        round(timings.get("llm", 0.0), 3) if timings else None,
        round(timings.get("render", 0.0), 3) if timings else None,
        extra={
            "request_id": rid,
            "event": "acta_error",
            "error_code": exc.error_code,
            "http_status": exc.http_status,
            "upload_filename": filename,
            "upload_bytes": file_size,
            "user_message": exc.user_message,
            "technical_details": exc.technical_details if _DEBUG else None,
            "latency_total_s": round(total_s, 3) if total_s is not None else None,
            "latency_parse_s": round(timings.get("parse", 0.0), 3) if timings else None,
            "latency_llm_s": round(timings.get("llm", 0.0), 3) if timings else None,
            "latency_render_s": round(timings.get("render", 0.0), 3) if timings else None,
        },
    )
    return JSONResponse(status_code=exc.http_status, content=payload)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/process")
async def process_meeting_notes(request: Request, file: UploadFile = File(...)):
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    request.state.acta_t0 = time.perf_counter()
    timings: dict[str, float] = {}
    request.state.acta_timings = timings
    t_wall0 = request.state.acta_t0
    request.state.acta_filename = file.filename

    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise InvalidFileTypeError(
            technical_details=f"filename={file.filename!r}",
        )

    raw = await file.read()
    file_size = len(raw)
    request.state.acta_file_size = file_size

    if file_size > _MAX_UPLOAD_MB * 1024 * 1024:
        raise FileTooLargeError(max_mb=_MAX_UPLOAD_MB)

    logger.info(
        "[request_id=%s] process_start filename=%r size=%s",
        request_id,
        file.filename,
        file_size,
        extra={
            "request_id": request_id,
            "upload_filename": file.filename,
            "upload_bytes": file_size,
            "event": "process_start",
        },
    )

    tmpdir = tempfile.mkdtemp(prefix="acta-upload-")
    outdir = tempfile.mkdtemp(prefix="acta-out-")

    upload_path = os.path.join(tmpdir, Path(file.filename).name)

    try:
        with open(upload_path, "wb") as f:
            f.write(raw)

        result = run_acta_pipeline(
            upload_path,
            source_filename=file.filename,
            output_dir=outdir,
            keep_docx=True,
            timings=timings,
        )
        with open(result["pdf_path"], "rb") as f:
            pdf_b64 = base64.standard_b64encode(f.read()).decode("ascii")

        docx_b64: str | None = None
        if result["docx_path"]:
            with open(result["docx_path"], "rb") as f:
                docx_b64 = base64.standard_b64encode(f.read()).decode("ascii")

        total_s = time.perf_counter() - t_wall0
        logger.info(
            "[request_id=%s] process_success filename=%r size=%s latency_total_s=%.3f "
            "latency_parse_s=%.3f latency_llm_s=%.3f latency_render_s=%.3f",
            request_id,
            file.filename,
            file_size,
            total_s,
            timings.get("parse", 0.0),
            timings.get("llm", 0.0),
            timings.get("render", 0.0),
            extra={
                "request_id": request_id,
                "upload_filename": file.filename,
                "upload_bytes": file_size,
                "event": "process_success",
                "latency_total_s": round(total_s, 3),
                "latency_parse_s": round(timings.get("parse", 0.0), 3),
                "latency_llm_s": round(timings.get("llm", 0.0), 3),
                "latency_render_s": round(timings.get("render", 0.0), 3),
            },
        )

        out: dict = {
            "metadata": result["metadata"],
            "acta": result["acta"],
            "output_base_name": result["output_name"],
            "pdf_base64": pdf_b64,
            "docx_base64": docx_b64,
        }
        drive_link = result.get("drive_web_link")
        if drive_link:
            out["drive_web_link"] = drive_link
        return out
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        shutil.rmtree(outdir, ignore_errors=True)
