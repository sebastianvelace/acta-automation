#!/usr/bin/env python3
"""
Calificación determinística (sin Groq) para las 6 actas Gemini reales.

Pipeline: parse → stub acta → finalize_acta_after_llm → apply_metadata_times.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.aliases import finalize_acta_after_llm, is_universal_acta, lookup_team_alias, post_process_acta
from src.google_workflow import apply_metadata_times_to_acta
from src.gorila_roster import _is_growfik_branded_email
from src.parser import extract_proximos_pasos_items, extract_text, is_gorila_email

DOCS: dict[str, str] = {
    "Ana Maria": (
        "/home/sebasvelace/Downloads/Seguimiento - Ana Maria Psicología_ "
        "2026_05_21 08_30 GMT-05_00 - Notas de Gemini.docx"
    ),
    "Universal Campañas": (
        "/home/sebasvelace/Downloads/Revisión Campañas - Universal Academia de Idiomas_ "
        "2026_05_20 14_58 GMT-05_00 - Notas de Gemini.docx"
    ),
    "Marlon": (
        "/home/sebasvelace/Downloads/Seguimiento Marlon Becerra a._ "
        "2026_05_20 14_01 GMT-05_00 - Notas de Gemini.docx"
    ),
    "Sambal": (
        "/home/sebasvelace/Downloads/Revisión Pauta - Sambal_ "
        "2026_05_21 08_00 GMT-05_00 - Notas de Gemini.docx"
    ),
    "Universal Dashboard": (
        "/home/sebasvelace/Downloads/Actualización Dashboard - Universal _ "
        "2026_05_21 11_02 GMT-05_00 - Notas de Gemini (1).docx"
    ),
    "Barrera": (
        "/home/sebasvelace/Downloads/Seguimiento Barrera Estrada_ "
        "2026_05_21 16_01 GMT-05_00 - Notas de Gemini.docx"
    ),
    "Real State Seguimiento": (
        "/home/sebasvelace/Downloads/Seguimiento - Real State _ "
        "2026_05_22 09_00 GMT-05_00 - Notas de Gemini.docx"
    ),
    "Universal Reporte Ventas": (
        "/home/sebasvelace/Downloads/Reunión Reporte de Ventas - Universal _ "
        "2026_05_25 15_59 GMT-05_00 - Notas de Gemini.docx"
    ),
    "Universal Redes": (
        "/home/sebasvelace/Downloads/Redes - Universal Idiomas._ "
        "2026_05_26 16_02 GMT-05_00 - Notas de Gemini.docx"
    ),
}

EXPECTED_COUNTS: dict[str, tuple[int, int]] = {
    "Ana Maria": (1, 4),
    "Universal Campañas": (8, 0),
    "Marlon": (2, 2),
    "Sambal": (3, 2),
    "Universal Dashboard": (8, 0),
    "Barrera": (2, 3),
    "Real State Seguimiento": (2, 5),
    "Universal Reporte Ventas": (0, 2),
    "Universal Redes": (5, 1),
}


def titulo_from_filename(path: str) -> str:
    base = os.path.basename(path).replace(" - Notas de Gemini.docx", "").replace(" (1)", "")
    m = re.match(r"^(.*?)\s*_\s*\d{4}_\d{2}_\d{2}", base)
    return (m.group(1).strip() if m else base).replace("_", " ")


def cliente_from_titulo(titulo: str) -> str:
    if " - " in titulo:
        return titulo.rsplit(" - ", 1)[-1].strip().rstrip(".,;:")
    parts = titulo.split()
    if len(parts) >= 2 and parts[0] in ("Seguimiento", "Revisión", "Actualización"):
        return " ".join(parts[1:]).strip(" -").rstrip(".,;:")
    return titulo.rstrip(".,;:")


def build_deterministic_acta(path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    parsed = extract_text(path)
    meta = parsed["metadata"]
    prox = extract_proximos_pasos_items(parsed["raw_text"])
    titulo = titulo_from_filename(path)
    stub: dict[str, Any] = {
        "titulo": titulo,
        "fecha": meta.get("date") or "No especificada",
        "hora_inicio": meta.get("hora_inicio") or "No especificada",
        "hora_fin": meta.get("hora_fin") or "No especificada",
        "lugar": "No especificada",
        "cliente": cliente_from_titulo(titulo),
        "objetivo": "Stub.",
        "cierre": "Stub.",
        "invitados": [],
        "asuntos_tratados": [],
        "compromisos_gorila": [],
        "compromisos_cliente": [],
    }
    out = finalize_acta_after_llm(
        stub,
        parsed["raw_text"],
        proximos_items=prox or None,
        metadata=meta,
        source_filename=path,
    )
    out = apply_metadata_times_to_acta(out, meta)
    out = post_process_acta(out, meta)
    return out, meta


def score_encabezado(acta: dict[str, Any], meta: dict[str, Any], titulo: str) -> float:
    pts = 0.0
    if acta.get("titulo") and acta["titulo"] != "No especificado":
        pts += 2.0
    if acta.get("fecha") and acta["fecha"] not in ("No especificada", ""):
        pts += 2.0
    if acta.get("hora_inicio") and acta["hora_inicio"] not in ("No especificada", ""):
        pts += 2.0
    elif meta.get("is_virtual") and str(acta.get("lugar") or "").casefold() == "google meet":
        pts += 2.0
    cliente = str(acta.get("cliente") or "")
    if cliente and cliente != "No especificado":
        pts += 2.0
        suffix = cliente_from_titulo(titulo)
        if suffix and cliente.lower().endswith(f"- {suffix.lower()} - {suffix.lower()}"):
            pts -= 1.0
    if meta.get("is_virtual"):
        if str(acta.get("lugar") or "").casefold() == "google meet":
            pts += 2.0
    else:
        pts += 2.0
    return min(10.0, max(0.0, pts))


def _needs_growfik_puesto(email: str, *, universal: bool) -> bool:
    return universal and _is_growfik_branded_email(email)


def score_invitados(acta: dict[str, Any], meta: dict[str, Any]) -> float:
    rows = acta.get("invitados") or []
    emails = meta.get("attendee_emails") or []
    teams = meta.get("gorila_teams") or []
    universal = is_universal_acta(
        cliente=str(acta.get("cliente") or ""),
        titulo=str(acta.get("titulo") or ""),
        attendee_emails=emails,
    )
    if not emails and not teams:
        return 10.0 if not rows else 7.0
    pts = 10.0
    by_email = {str(r.get("correo") or "").casefold(): r for r in rows if isinstance(r, dict)}
    by_nombre = {str(r.get("nombre") or "").casefold(): r for r in rows if isinstance(r, dict)}
    for email in emails:
        if email.casefold() not in by_email:
            pts -= 2.0
        else:
            row = by_email[email.casefold()]
            puesto = str(row.get("puesto") or "")
            nombre = str(row.get("nombre") or "")
            if is_gorila_email(email):
                if _needs_growfik_puesto(email, universal=universal):
                    if "growfik" not in puesto.casefold():
                        pts -= 1.5
                elif "gorila" not in puesto.casefold():
                    pts -= 1.5
            if nombre.lower() in ("el grupo", "the group"):
                pts -= 2.0
    for team in teams:
        alias = lookup_team_alias(team)
        if not alias:
            continue
        team_nombre = str(alias.get("nombre") or "").casefold()
        if team_nombre and team_nombre not in by_nombre:
            pts -= 2.0
    return max(0.0, min(10.0, pts))


def score_compromisos(acta: dict[str, Any], expected: tuple[int, int]) -> float:
    eg, ec = expected
    g = len(acta.get("compromisos_gorila") or [])
    c = len(acta.get("compromisos_cliente") or [])
    delta = abs(g - eg) + abs(c - ec)
    if delta == 0:
        return 10.0
    return max(0.0, 10.0 - delta * 2.5)


def grade_doc(label: str, path: str) -> dict[str, Any]:
    if not os.path.isfile(path):
        return {"label": label, "skipped": True, "reason": "docx not found"}
    acta, meta = build_deterministic_acta(path)
    exp = EXPECTED_COUNTS[label]
    enc = score_encabezado(acta, meta, titulo_from_filename(path))
    inv = score_invitados(acta, meta)
    com = score_compromisos(acta, exp)
    overall = round((enc + inv + com) / 3.0, 2)
    return {
        "label": label,
        "skipped": False,
        "scores": {
            "encabezado": round(enc, 2),
            "invitados": round(inv, 2),
            "compromisos": round(com, 2),
            "overall": overall,
        },
        "compromisos": {
            "got_gorila": len(acta.get("compromisos_gorila") or []),
            "got_cliente": len(acta.get("compromisos_cliente") or []),
            "exp_gorila": exp[0],
            "exp_cliente": exp[1],
        },
        "cliente": acta.get("cliente"),
        "lugar": acta.get("lugar"),
        "invitados_n": len(acta.get("invitados") or []),
    }


def main() -> None:
    results = [grade_doc(label, path) for label, path in DOCS.items()]
    out_path = ROOT / "tests/fixtures/llm_outputs/_batch_grade_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print("batch_grade — determinístico (sin Groq)\n")
    print(f"{'Doc':<22} {'Enc':>5} {'Inv':>5} {'Com':>5} {'Avg':>5}  G/C (exp)")
    print("-" * 62)
    for r in results:
        if r.get("skipped"):
            print(f"{r['label']:<22} SKIP")
            continue
        s = r["scores"]
        cd = r["compromisos"]
        exp = f"{cd['exp_gorila']}/{cd['exp_cliente']}"
        got = f"{cd['got_gorila']}/{cd['got_cliente']}"
        print(
            f"{r['label']:<22} {s['encabezado']:>5.1f} {s['invitados']:>5.1f} "
            f"{s['compromisos']:>5.1f} {s['overall']:>5.1f}  {got} ({exp})"
        )
    print(f"\nJSON: {out_path}")


if __name__ == "__main__":
    main()
