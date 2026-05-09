#!/usr/bin/env python3
"""
Juez LLM (Groq mismo modelo) sobre notas + JSON extraído; promedia scores.
Actualiza eval_history.jsonl y muestra comparación con la corrida anterior.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from groq import Groq

from src.llm import parse_json_blob
from src.parser import extract_text

load_dotenv(ROOT / ".env")

GEMINI = ROOT / "tests/fixtures/gemini"
OUT_DIR = ROOT / "tests/fixtures/llm_outputs"
HISTORY_PATH = ROOT / "eval_history.jsonl"

MODEL = os.environ.get("EVAL_JUDGE_MODEL", "llama-3.3-70b-versatile")

JUDGE_SYSTEM = """\
Eres un evaluador imparcial de extracción de actas de reunión.
Dado el texto bruto de notas (Gemini/calendario) y el JSON estructurado extraído,
califica cada dimensión con un entero de 0 a 5:
- completitud_compromisos: ¿se reflejan los compromisos relevantes del texto?
- calidad_titulos: ¿los títulos de asuntos_tratados son claros y acordes al contenido?
- precision_asistentes: ¿los asistentes son coherentes con el texto?
- claridad_objetivo: ¿el objetivo resume bien el propósito de la reunión?

Responde SOLO con un objeto JSON válido, sin markdown:
{"completitud_compromisos": <int>, "calidad_titulos": <int>, "precision_asistentes": <int>, "claridad_objetivo": <int>, "razon": "<una frase breve en español>"}
"""


def _judge_one(client: Groq, notes: str, acta: dict[str, Any]) -> dict[str, Any]:
    user = (
        "NOTAS (texto completo):\n\n"
        f"{notes[:120000]}\n\n"
        "---\nJSON EXTRAÍDO:\n"
        f"{json.dumps(acta, ensure_ascii=False, indent=2)[:80000]}"
    )
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0.1,
        max_tokens=600,
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        data = parse_json_blob(raw)
    except ValueError:
        return {
            "completitud_compromisos": 0,
            "calidad_titulos": 0,
            "precision_asistentes": 0,
            "claridad_objetivo": 0,
            "razon": "respuesta del juez no fue JSON válido",
        }
    for k in (
        "completitud_compromisos",
        "calidad_titulos",
        "precision_asistentes",
        "claridad_objetivo",
    ):
        try:
            v = int(float(data.get(k, 0)))
            data[k] = max(0, min(5, v))
        except (TypeError, ValueError):
            data[k] = 0
    return data


def _avg(scores_list: list[dict[str, Any]]) -> dict[str, float]:
    keys = (
        "completitud_compromisos",
        "calidad_titulos",
        "precision_asistentes",
        "claridad_objetivo",
    )
    out: dict[str, float] = {}
    for k in keys:
        vals: list[float] = []
        for s in scores_list:
            v = s.get(k)
            if isinstance(v, bool) or v is None:
                continue
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                continue
        out[k] = round(sum(vals) / len(vals), 2) if vals else 0.0
    return out


def _load_previous_record() -> dict[str, Any] | None:
    if not HISTORY_PATH.is_file():
        return None
    lines = HISTORY_PATH.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return None


def main() -> None:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("Falta GROQ_API_KEY", file=sys.stderr)
        sys.exit(1)

    summary_path = OUT_DIR / "_eval_summary.json"
    if not summary_path.is_file():
        print(f"Ejecuta primero eval_acta.py (falta {summary_path})", file=sys.stderr)
        sys.exit(1)

    eval_summary = json.loads(summary_path.read_text(encoding="utf-8"))

    docx_files = sorted(GEMINI.glob("*.docx"))
    client = Groq(api_key=api_key)
    scores: list[dict[str, Any]] = []
    reasons: list[str] = []
    judged_paths: list[Path] = []

    print(f"judge_acta — modelo {MODEL}\n")
    t0 = time.perf_counter()

    for path in docx_files:
        acta_path = OUT_DIR / f"{path.name}.json"
        if not acta_path.is_file():
            print(f"  (saltar {path.name}: no hay {acta_path.name})", file=sys.stderr)
            continue
        acta = json.loads(acta_path.read_text(encoding="utf-8"))
        notes = extract_text(str(path))["raw_text"]
        print(f"  · {path.name} …", flush=True)
        s = _judge_one(client, notes, acta)
        scores.append(s)
        reasons.append(str(s.get("razon", "")))
        judged_paths.append(path)

    elapsed = time.perf_counter() - t0
    averages = _avg(scores)

    print(f"\nTiempo juez: {elapsed:.1f}s\n")
    print(f"{'Dimensión':<28} {'Media':>8}")
    print("-" * 38)
    for k, v in averages.items():
        print(f"{k:<28} {v:>8.2f}")
    print("-" * 38)
    overall = round(sum(averages.values()) / len(averages), 2) if averages else 0.0
    print(f"{'PROMEDIO GLOBAL':<28} {overall:>8.2f}\n")

    print("Razones (por acta):")
    for path, r in zip(judged_paths, reasons):
        print(f"  — {path.name}: {r[:160]}{'…' if len(r) > 160 else ''}")

    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "eval": {
            "mean_coverage_scalar_pct": eval_summary.get("mean_coverage_scalar_pct"),
            "total_commitment_delta": eval_summary.get("total_commitment_delta"),
            "asistentes_puesto_inferido_sum": eval_summary.get("asistentes_puesto_inferido_sum"),
            "elapsed_s": eval_summary.get("elapsed_s"),
        },
        "judge": {"averages": averages, "overall": overall, "judge_elapsed_s": round(elapsed, 2)},
    }

    prev = _load_previous_record()
    if prev:
        print("\n--- Comparación vs corrida anterior ---\n")
        print(f"{'Métrica':<40} {'Antes':>12} {'Ahora':>12} {'Δ':>10}")
        print("-" * 76)

        def row(label: str, a: Any, b: Any) -> None:
            try:
                da = float(a) if a is not None else None
                db = float(b) if b is not None else None
                if da is None or db is None:
                    print(f"{label:<40} {str(a):>12} {str(b):>12} {'—':>10}")
                    return
                print(f"{label:<40} {da:>12.2f} {db:>12.2f} {db - da:>+10.2f}")
            except (TypeError, ValueError):
                print(f"{label:<40} {str(a):>12} {str(b):>12} {'—':>10}")

        pe = prev.get("eval") or {}
        je = prev.get("judge") or {}
        pa = averages

        row("Cobertura escalar (media %)", pe.get("mean_coverage_scalar_pct"), eval_summary.get("mean_coverage_scalar_pct"))
        row("Δ compromisos vs esperado (suma)", pe.get("total_commitment_delta"), eval_summary.get("total_commitment_delta"))
        row("Asistentes c/puesto inferido (suma)", pe.get("asistentes_puesto_inferido_sum"), eval_summary.get("asistentes_puesto_inferido_sum"))
        row("Juez: completitud compromisos", je.get("averages", {}).get("completitud_compromisos"), pa.get("completitud_compromisos"))
        row("Juez: calidad títulos", je.get("averages", {}).get("calidad_titulos"), pa.get("calidad_titulos"))
        row("Juez: precisión asistentes", je.get("averages", {}).get("precision_asistentes"), pa.get("precision_asistentes"))
        row("Juez: claridad objetivo", je.get("averages", {}).get("claridad_objetivo"), pa.get("claridad_objetivo"))
        row("Juez: promedio global", je.get("overall"), overall)
        print()

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Historial actualizado: {HISTORY_PATH}")


if __name__ == "__main__":
    main()
