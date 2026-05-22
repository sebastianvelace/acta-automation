#!/usr/bin/env python3
"""Métricas: placeholders 'No especificada/o' y filas de asistente beneficiadas por alias."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.aliases import TEAM_ALIASES, lookup_team_alias, post_process_acta
from src.schemas import ActaSchema

EXPECTED = ROOT / "tests/fixtures/expected"

_PLACE = frozenset({"No especificada", "No especificado"})


def _count_placeholders(acta: dict) -> tuple[int, int]:
    """(matches, total_cells) para hora_inicio, hora_fin, lugar + cada asistente nombre/puesto."""
    total = 0
    matches = 0
    for key in ("hora_inicio", "hora_fin", "lugar"):
        total += 1
        v = acta.get(key)
        if isinstance(v, str) and v in _PLACE:
            matches += 1
    for a in acta.get("invitados") or []:
        if not isinstance(a, dict):
            continue
        for key in ("correo", "puesto"):
            total += 1
            v = a.get(key)
            if isinstance(v, str) and v in _PLACE:
                matches += 1
    return matches, total


def _benefit_count_before_after(raw: dict) -> int:
    """Asistentes cuyo nombre coincide con un alias de equipo (cuenta beneficiarios)."""
    before = 0
    for a in raw.get("invitados") or []:
        if not isinstance(a, dict):
            continue
        n = (a.get("correo") or "").strip()
        if n and lookup_team_alias(n):
            before += 1
    return before


def _asistente_rows_changed(raw: dict, after: dict) -> int:
    c = 0
    br = raw.get("invitados") or []
    ar = after.get("invitados") or []
    for i, a0 in enumerate(br):
        if i >= len(ar) or not isinstance(a0, dict):
            continue
        a1 = ar[i]
        if a0.get("correo") != a1.get("correo") or a0.get("puesto") != a1.get("puesto"):
            c += 1
    return c


def main() -> None:
    stems = []
    for path in sorted(EXPECTED.glob("case_*.llm_raw.json")):
        stems.append(path.name.removesuffix(".llm_raw.json"))
    pct_before: list[float] = []
    pct_after: list[float] = []
    benefited_alias_rows = 0
    rows_changed = 0

    for stem in stems:
        path = EXPECTED / f"{stem}.llm_raw.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        validated = ActaSchema.model_validate(raw).model_dump()
        after_dict = post_process_acta(validated)

        b, t = _count_placeholders(validated)
        a_m, a_t = _count_placeholders(after_dict)
        pct_before.append(100.0 * b / t if t else 0.0)
        pct_after.append(100.0 * a_m / a_t if a_t else 0.0)
        benefited_alias_rows += _benefit_count_before_after(raw)
        rows_changed += _asistente_rows_changed(raw, after_dict)

    n = len(stems)
    print(f"Casos: {n}")
    if n:
        print(
            f"% medio celdas placeholder (hora_*, lugar, asistentes): "
            f"antes {sum(pct_before)/n:.1f}% → después {sum(pct_after)/n:.1f}%"
        )
    print(
        f"Asistentes cuyo nombre matchea TEAM_ALIASES en LLM crudo (suma en {n} actas): "
        f"{benefited_alias_rows}"
    )
    print(
        f"Filas de asistentes reescritas por post_process (nombre/puesto distinto): {rows_changed}"
    )
    print(f"Catálogo TEAM_ALIASES: {len(TEAM_ALIASES)} entradas")


if __name__ == "__main__":
    main()
