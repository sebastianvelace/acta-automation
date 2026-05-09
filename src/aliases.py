"""
Canonical labels for calendar / Gemini team display names (not real people).
"""

from __future__ import annotations

import re
from typing import Any

_TEAM_ALIASES_KEY_CF: dict[str, dict[str, str]] = {}


def _register_aliases(raw: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    for k, v in raw.items():
        _TEAM_ALIASES_KEY_CF[k.casefold().strip()] = dict(v)
    return raw


# Canonical display: invitado string from Gemini → {nombre, puesto}
TEAM_ALIASES: dict[str, dict[str, str]] = _register_aliases(
    {
        "Marketing Gorila Hosting": {"nombre": "Marketing", "puesto": "Gorila Hosting"},
        "Administración Gorila Hosting": {
            "nombre": "Administración",
            "puesto": "Gorila Hosting",
        },
        "Redes Gorila Hosting": {"nombre": "Redes", "puesto": "Gorila Hosting"},
        "Social Media Gorila Hosting": {"nombre": "Social Media", "puesto": "Gorila Hosting"},
        "Executive Gorila Hosting": {"nombre": "Executive", "puesto": "Gorila Hosting"},
        "Gorila Hosting": {"nombre": "Gorila Hosting", "puesto": "Equipo"},
        # Variaciones frecuentes en notas / compromisos
        "Eventos y Matrominios Portal": {
            "nombre": "Eventos y Matrominios",
            "puesto": "Portal cliente",
        },
        "Eventos y Matrimonios Portal": {
            "nombre": "Eventos y Matrimonios",
            "puesto": "Portal cliente",
        },
        "Eventos & Matrimonios Portal": {
            "nombre": "Eventos & Matrimonios",
            "puesto": "Portal cliente",
        },
        "Soporte Gorila Hosting": {"nombre": "Soporte", "puesto": "Gorila Hosting"},
        "Ventas Gorila Hosting": {"nombre": "Ventas", "puesto": "Gorila Hosting"},
        "Diseño Gorila Hosting": {"nombre": "Diseño", "puesto": "Gorila Hosting"},
        "Producto Gorila Hosting": {"nombre": "Producto", "puesto": "Gorila Hosting"},
    }
)


_NON_NAME_CHARS = re.compile(r"[^a-záéíóúñA-ZÁÉÍÓÚÑ0-9@\.\s\-]")


def lookup_team_alias(nombre: str) -> dict[str, str] | None:
    """Return canonical {nombre, puesto} if ``nombre`` matches a known team alias (exact, case-insensitive, normalized spaces)."""
    n = " ".join((nombre or "").split()).strip()
    if not n:
        return None
    if n in TEAM_ALIASES:
        return dict(TEAM_ALIASES[n])
    key = n.casefold()
    if key in _TEAM_ALIASES_KEY_CF:
        return dict(_TEAM_ALIASES_KEY_CF[key])
    return None


def normalize_attendee(raw: str) -> dict[str, str]:
    """
    Normalize a raw invitee string (metadata line, email, or human name).
    Used for deterministic parsing paths and tests; LLM JSON is post-processed via :func:`apply_alias_to_asistente_row`.
    """
    raw_clean = " ".join((raw or "").split()).strip()
    if not raw_clean:
        return {"nombre": "No especificado", "puesto": "No especificado"}

    alias = lookup_team_alias(raw_clean)
    if alias:
        return dict(alias)

    if "@" in raw_clean:
        local, _, domain = raw_clean.partition("@")
        dom = domain.strip() or "No especificado"
        name_part = local.strip().replace(".", " ").replace("_", " ")
        name = name_part.title() if name_part else "Correo"
        return {"nombre": name, "puesto": dom}

    if _looks_like_person_name(raw_clean):
        return {"nombre": raw_clean, "puesto": "No especificado"}

    return {"nombre": raw_clean, "puesto": "No especificado"}


def _looks_like_person_name(s: str) -> bool:
    """Heuristic: several tokens, mostly letters, no @ — típico 'Apellido Nombre'."""
    parts = s.split()
    if len(parts) < 2:
        return False
    if "@" in s:
        return False
    if _NON_NAME_CHARS.search(s):
        return False
    letterish = sum(1 for ch in s if ch.isalpha())
    return letterish >= len(s) * 0.6


def apply_alias_to_asistente_row(nombre: str, puesto: str) -> dict[str, str]:
    """
    Post-process a single attendee row from LLM JSON.
    If ``nombre`` matches a team alias, replace with canonical nombre/puesto; otherwise keep LLM output with defaults.
    """
    n = (nombre or "").strip()
    p = (puesto or "").strip()
    canon = lookup_team_alias(n)
    if canon:
        return {"nombre": canon["nombre"], "puesto": canon["puesto"]}
    return {
        "nombre": n or "No especificado",
        "puesto": p or "No especificado",
    }


def post_process_acta(data: dict[str, Any]) -> dict[str, Any]:
    """Apply deterministic team-alias normalization to ``asistentes``."""
    out = dict(data)
    rows = data.get("asistentes") or []
    out["asistentes"] = [
        apply_alias_to_asistente_row(a.get("nombre", ""), a.get("puesto", ""))
        if isinstance(a, dict)
        else apply_alias_to_asistente_row("", "")
        for a in rows
    ]
    return out
