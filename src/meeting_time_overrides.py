"""Horas de reunión por patrón de título/archivo (p. ej. export Gemini _59 GMT)."""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OVERRIDES_PATH = _REPO_ROOT / "data" / "meeting_time_overrides.yaml"


def _row_dates(row: dict[str, Any]) -> tuple[str, ...]:
    """`date` (string) o `dates` (lista) → fechas YYYY_MM_DD casefolded."""
    raw = row.get("dates") if row.get("dates") is not None else row.get("date")
    if raw is None:
        return ()
    values = raw if isinstance(raw, list) else [raw]
    return tuple(str(v).strip().casefold() for v in values if str(v).strip())


@lru_cache(maxsize=1)
def _load_overrides() -> tuple[tuple[str, str, str, tuple[str, ...]], ...]:
    if not _OVERRIDES_PATH.is_file():
        return ()
    data = yaml.safe_load(_OVERRIDES_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return ()
    rows = data.get("overrides")
    if not isinstance(rows, list):
        return ()
    out: list[tuple[str, str, str, tuple[str, ...]]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        match = str(row.get("match") or "").strip()
        hi = str(row.get("hora_inicio") or "").strip()
        hf = str(row.get("hora_fin") or "").strip()
        if match and hi:
            out.append((match.casefold(), hi, hf, _row_dates(row)))
    return tuple(out)


def apply_meeting_time_overrides(
    metadata: dict[str, Any],
    *,
    source_filename: str = "",
    notes_text: str = "",
) -> dict[str, Any]:
    """Aplica horas conocidas por título/archivo (p. ej. sello de exportación Gemini).

    `notes_text` permite además casar el `match` contra el texto de las notas/adjunto
    (raw_text) cuando el archivo fue renombrado y el título de la serie solo aparece allí.
    """
    base = dict(metadata or {})
    blob = " ".join(
        (
            str(source_filename or ""),
            str(base.get("meeting_title") or ""),
            str(notes_text or ""),
        )
    ).casefold()
    if not blob.strip():
        return base
    for match, hi, hf, dates in _load_overrides():
        if match not in blob:
            continue
        # Un override con fecha(s) solo aplica a las reuniones de esas fechas
        # (evita pisar reuniones recurrentes con el mismo título).
        if dates:
            if not any(date in blob for date in dates):
                continue
        elif base.get("hora_inicio"):
            # Override sin fecha pero el parser ya extrajo hora real (no sello):
            # gana la hora del parser para no pisar reuniones recurrentes.
            logger.warning(
                "Override de hora sin fecha para %r ignorado: el parser extrajo %r (%s)",
                match,
                base.get("hora_inicio"),
                source_filename,
            )
            break
        base["hora_inicio"] = hi
        if hf:
            base["hora_fin"] = hf
        break
    return base
