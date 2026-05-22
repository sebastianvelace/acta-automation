#!/usr/bin/env python3
"""
Evalúa extracción real (Groq + pipeline) sobre tests/fixtures/gemini/*.docx.
Escribe JSON por archivo y un resumen para judge/historial.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml
from dotenv import load_dotenv

from src.pipeline import run_acta_pipeline

load_dotenv(ROOT / ".env")

GEMINI = ROOT / "tests/fixtures/gemini"
OUT_DIR = ROOT / "tests/fixtures/llm_outputs"
COUNTS_PATH = ROOT / "tests/fixtures/expected_counts.yaml"

PLACEHOLDER = frozenset({"No especificada", "No especificado"})
SCALAR_KEYS = ("titulo", "fecha", "hora_inicio", "hora_fin", "lugar", "cliente", "objetivo")


def _scalar_coverage_pct(acta: dict[str, Any]) -> float:
    n = len(SCALAR_KEYS)
    ok = sum(
        1
        for k in SCALAR_KEYS
        if str(acta.get(k, "")).strip()
        and str(acta.get(k, "")).strip() not in PLACEHOLDER
    )
    return 100.0 * ok / n if n else 0.0


def _attendees_puesto_inferred(acta: dict[str, Any]) -> tuple[int, int]:
    rows = acta.get("invitados") or []
    inferred = 0
    for a in rows:
        if not isinstance(a, dict):
            continue
        p = str(a.get("puesto", "")).strip()
        if p and p not in PLACEHOLDER:
            inferred += 1
    return inferred, len(rows)


def _commitment_delta(acta: dict[str, Any], expected: dict[str, int] | None) -> dict[str, Any]:
    g = len(acta.get("compromisos_gorila") or [])
    c = len(acta.get("compromisos_cliente") or [])
    if not expected:
        return {
            "got_gorila": g,
            "got_cliente": c,
            "exp_gorila": None,
            "exp_cliente": None,
            "delta_total": None,
        }
    eg = int(expected.get("compromisos_gorila", -1))
    ec = int(expected.get("compromisos_cliente", -1))
    delta = abs(g - eg) + abs(c - ec)
    return {"got_gorila": g, "got_cliente": c, "exp_gorila": eg, "exp_cliente": ec, "delta_total": delta}


def main() -> None:
    if not GEMINI.is_dir():
        print(f"No existe {GEMINI}", file=sys.stderr)
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    counts_doc: dict[str, Any] = {}
    if COUNTS_PATH.is_file():
        counts_doc = yaml.safe_load(COUNTS_PATH.read_text(encoding="utf-8")) or {}

    docx_files = sorted(GEMINI.glob("*.docx"))
    if not docx_files:
        print(f"No hay .docx en {GEMINI}", file=sys.stderr)
        sys.exit(1)

    print("eval_acta — pipeline real (Groq + render)\n")
    rows_out: list[dict[str, Any]] = []
    t0 = time.perf_counter()

    for path in docx_files:
        stem = path.stem
        exp = counts_doc.get(stem)
        out_json = OUT_DIR / f"{path.name}.json"

        print(f"  · {path.name} …", flush=True)
        with tempfile.TemporaryDirectory(prefix="eval-acta-") as td:
            result = run_acta_pipeline(
                str(path),
                source_filename=path.name,
                output_dir=td,
                keep_docx=False,
            )
        acta = result["acta"]
        out_json.write_text(
            json.dumps(acta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        cov = _scalar_coverage_pct(acta)
        inf, n_att = _attendees_puesto_inferred(acta)
        cd = _commitment_delta(acta, exp if isinstance(exp, dict) else None)

        rows_out.append(
            {
                "docx": path.name,
                "stem": stem,
                "coverage_scalar_pct": round(cov, 1),
                "asistentes_puesto_inferido": inf,
                "asistentes_total": n_att,
                "commitments": cd,
            }
        )

    elapsed = time.perf_counter() - t0
    mean_cov = sum(r["coverage_scalar_pct"] for r in rows_out) / len(rows_out)
    total_delta = sum(
        r["commitments"]["delta_total"] or 0
        for r in rows_out
        if r["commitments"]["delta_total"] is not None
    )
    total_att_inf = sum(r["asistentes_puesto_inferido"] for r in rows_out)
    total_att = sum(r["asistentes_total"] for r in rows_out)

    summary = {
        "elapsed_s": round(elapsed, 2),
        "files": len(rows_out),
        "mean_coverage_scalar_pct": round(mean_cov, 2),
        "total_commitment_delta": int(total_delta),
        "asistentes_puesto_inferido_sum": total_att_inf,
        "asistentes_total_sum": total_att,
        "per_file": rows_out,
    }
    summary_path = OUT_DIR / "_eval_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Tabla legible
    print(f"\nTiempo total: {elapsed:.1f}s ({len(docx_files)} actas)\n")
    print(
        f"{'Acta':<28} {'Cobertura%':>10} {'Ast.inf':>8} {'Ast.tot':>8} "
        f"{'Gorila':>7} {'Cli':>5} {'Δ':>5}"
    )
    print("-" * 84)
    for r in rows_out:
        cd = r["commitments"]
        dg = cd.get("got_gorila", "-")
        dc = cd.get("got_cliente", "-")
        dlt = cd.get("delta_total")
        dstr = str(dlt) if dlt is not None else "—"
        print(
            f"{r['docx']:<28} {r['coverage_scalar_pct']:>10.1f} "
            f"{r['asistentes_puesto_inferido']:>8} {r['asistentes_total']:>8} "
            f"{dg!s:>7} {dc!s:>5} {dstr:>5}"
        )
    print("-" * 84)
    print(
        f"{'PROMEDIO / SUMA':<28} {mean_cov:>10.1f} "
        f"{total_att_inf:>8} {total_att:>8} {'':>7} {'':>5} {int(total_delta):>5}\n"
    )
    print(f"Resumen JSON: {summary_path}")


if __name__ == "__main__":
    main()
