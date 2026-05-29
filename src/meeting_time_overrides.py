"""Horas de reunión por patrón de título/archivo (p. ej. export Gemini _59 GMT)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OVERRIDES_PATH = _REPO_ROOT / "data" / "meeting_time_overrides.yaml"


@lru_cache(maxsize=1)
def _load_overrides() -> tuple[tuple[str, str, str], ...]:
    if not _OVERRIDES_PATH.is_file():
        return ()
    data = yaml.safe_load(_OVERRIDES_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return ()
    rows = data.get("overrides")
    if not isinstance(rows, list):
        return ()
    out: list[tuple[str, str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        match = str(row.get("match") or "").strip()
        hi = str(row.get("hora_inicio") or "").strip()
        hf = str(row.get("hora_fin") or "").strip()
        if match and hi:
            out.append((match.casefold(), hi, hf))
    return tuple(out)


def apply_meeting_time_overrides(
    metadata: dict[str, Any],
    *,
    source_filename: str = "",
) -> dict[str, Any]:
    """Rellena hora_inicio/hora_fin si el parser no obtuvo hora (p. ej. sello _59 GMT)."""
    base = dict(metadata or {})
    if base.get("hora_inicio") and str(base["hora_inicio"]).strip():
        return base
    blob = " ".join(
        (
            str(source_filename or ""),
            str(base.get("meeting_title") or ""),
        )
    ).casefold()
    if not blob.strip():
        return base
    for match, hi, hf in _load_overrides():
        if match in blob:
            base["hora_inicio"] = hi
            if hf:
                base["hora_fin"] = hf
            break
    return base
