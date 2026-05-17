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

_GROUP_RESPONSABLE_RE = re.compile(
    r"(?i)^\[?\s*(el\s+grupo|todos|ambos\s+equipos)\s*\]?$"
)

_ROLE_ORDER = (
    "Marketing",
    "Administración",
    "Redes",
    "Social Media",
    "Executive",
    "Soporte",
    "Ventas",
    "Diseño",
    "Producto",
)

_GORILA_RESPONSABLE_MARKERS = (
    "gorila hosting",
    "growfik",
)


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


def _strip_bracket_tag(s: str) -> str:
    t = (s or "").strip()
    m = re.match(r"^\[(.+)\]$", t)
    return m.group(1).strip() if m else t


def is_shared_responsable(responsable: str) -> bool:
    raw = _strip_bracket_tag((responsable or "").strip())
    return bool(_GROUP_RESPONSABLE_RE.match(raw))


def is_gorila_group_commitment_tag(tag: str) -> bool:
    raw = _strip_bracket_tag((tag or "").strip()).casefold()
    return bool(_GROUP_RESPONSABLE_RE.match(raw))


def infer_gorila_responsable(
    gorila_teams: list[str],
    *,
    for_grupo_task: bool = False,
) -> str:
    """
    Build responsable string like "Marketing & Administración Gorila Hosting"
    from calendar invite team labels, else "Gorila Hosting".

    When ``for_grupo_task`` is True, only **Marketing** and **Administración**
    (when present among detected roles) are kept for ``[El grupo]`` rows,
    excluding other invitees such as Social Media (matches manual actas).
    """
    roles: list[str] = []
    seen: set[str] = set()
    for t in gorila_teams:
        tt = " ".join((t or "").split())
        alias = lookup_team_alias(tt)
        if not alias:
            continue
        role = (alias.get("nombre") or "").strip()
        puesto = (alias.get("puesto") or "").strip()
        if role in seen:
            continue
        if puesto not in ("Gorila Hosting", "Equipo"):
            continue
        if role == "Gorila Hosting":
            continue
        seen.add(role)
        roles.append(role)

    def _sort_key(r: str) -> int:
        try:
            return _ROLE_ORDER.index(r)
        except ValueError:
            return 99

    roles = sorted(roles, key=_sort_key)

    if for_grupo_task:
        priority = ("Marketing", "Administración")
        picked = [r for r in priority if r in roles]
        if picked:
            roles = picked

    if not roles:
        return "Gorila Hosting"
    if len(roles) == 1:
        return f"{roles[0]} Gorila Hosting"
    return " & ".join(roles) + " Gorila Hosting"


def build_compromisos_from_proximos_pasos(
    items: list[dict[str, str]],
    gorila_teams: list[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """
    Deterministic routing from Gemini ``Próximos pasos``:
    [El grupo] / [Todos] → only ``compromisos_gorila`` with inferred Gorila responsable;
    person tags → only ``compromisos_cliente``; ``tarea`` = full description after colon.
    """
    out_g: list[dict[str, str]] = []
    out_c: list[dict[str, str]] = []
    inferred = infer_gorila_responsable(gorila_teams, for_grupo_task=True)
    for it in items:
        tag = (it.get("tag") or "").strip()
        desc = (it.get("descripcion") or "").strip()
        if not desc:
            continue
        row = {
            "tarea": desc,
            "responsable": "",
            "fecha_entrega": "No especificada",
        }
        if is_gorila_group_commitment_tag(tag):
            row["responsable"] = inferred
            out_g.append(dict(row))
        elif is_gorila_responsable(tag):
            row["responsable"] = _strip_bracket_tag(tag).strip()
            out_g.append(dict(row))
        else:
            row["responsable"] = _strip_bracket_tag(tag).strip() or "No especificado"
            out_c.append(dict(row))
    return out_g, out_c


def is_gorila_responsable(responsable: str) -> bool:
    """True when the assignee is a Gorila/Growfik team (not a client-side person)."""
    raw = _strip_bracket_tag((responsable or "").strip())
    if not raw:
        return False
    alias = lookup_team_alias(raw)
    if alias:
        p = (alias.get("puesto") or "").strip()
        if p in ("Gorila Hosting", "Equipo"):
            return True
        return False
    low = raw.casefold()
    return any(marker in low for marker in _GORILA_RESPONSABLE_MARKERS)


def compose_cliente_heading(titulo: str, cliente: str) -> str:
    """
    Build the acta heading shown in the Cliente field: meeting name + account.

    Manual actas use values like ``Revisión Pauta - Real State``. When the LLM
    already returns that full string in ``cliente``, it is preserved as-is.
    """
    t = (titulo or "").strip()
    c = (cliente or "").strip()
    if not c:
        return t or "No especificado"
    if not t:
        return c
    if " - " in c:
        return c
    if t.casefold() == c.casefold():
        return t
    if c.casefold() in t.casefold():
        return t
    if " - " in t:
        suffix = t.rsplit(" - ", 1)[-1].strip()
        if suffix.casefold() == c.casefold():
            return t
    return f"{t} - {c}"


def _normalize_compromiso_row(raw: dict[str, Any]) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    tarea = (raw.get("tarea") or "").strip()
    if not tarea:
        return None
    fecha = (raw.get("fecha_entrega") or "").strip() or "No especificada"
    return {
        "tarea": tarea,
        "responsable": (raw.get("responsable") or "").strip() or "No especificado",
        "fecha_entrega": fecha,
    }


def reclassify_compromisos(
    gorila: list[Any] | None,
    cliente: list[Any] | None,
    *,
    gorila_teams: list[str] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """
    Route commitments by responsable: Gorila Hosting teams → gorila;
    client-side people → cliente; [El grupo]/[Todos] → **solo** gorila (no duplicar en cliente).
    """
    teams = gorila_teams or []
    inferred = infer_gorila_responsable(teams, for_grupo_task=True)

    out_gorila: list[dict[str, str]] = []
    out_cliente: list[dict[str, str]] = []
    seen_g: set[tuple[str, str]] = set()
    seen_c: set[tuple[str, str]] = set()

    def _key(item: dict[str, str]) -> tuple[str, str]:
        return (item["tarea"].casefold(), item["fecha_entrega"].casefold())

    for raw in list(gorila or []) + list(cliente or []):
        item = _normalize_compromiso_row(raw)
        if not item:
            continue
        resp = item["responsable"]
        k = _key(item)
        if is_shared_responsable(resp):
            dup = dict(item)
            dup["responsable"] = inferred
            if k not in seen_g:
                seen_g.add(k)
                out_gorila.append(dup)
        elif is_gorila_responsable(resp):
            if k not in seen_g:
                seen_g.add(k)
                out_gorila.append(item)
        else:
            if k not in seen_c:
                seen_c.add(k)
                out_cliente.append(item)

    return out_gorila, out_cliente


def _is_person_attendee(nombre: str) -> bool:
    n = (nombre or "").strip()
    if not n or "@" in n:
        return False
    alias = lookup_team_alias(n)
    if alias:
        p = alias.get("puesto") or ""
        if p in ("Gorila Hosting", "Equipo"):
            return False
    if lookup_team_alias(f"{n} Gorila Hosting"):
        return False
    return _looks_like_person_name(n)


def filter_calendar_only_attendees(rows: list[Any], raw_text: str) -> list[dict[str, str]]:
    """
    Drop calendar-only team rows when the acta already lists real people from notes.
    ``raw_text`` is reserved for future heuristics; attendee rows are already alias-normalized.
    """
    _ = raw_text
    normalized = [
        apply_alias_to_asistente_row(a.get("nombre", ""), a.get("puesto", ""))
        if isinstance(a, dict)
        else apply_alias_to_asistente_row("", "")
        for a in rows
    ]
    people = [r for r in normalized if _is_person_attendee(r["nombre"])]
    if people:
        return people
    return normalized


def finalize_acta_after_llm(
    data: dict[str, Any],
    raw_text: str,
    *,
    proximos_items: list[dict[str, str]] | None,
    gorila_teams: list[str],
) -> dict[str, Any]:
    """Deterministic compromisos + attendee cleanup (runs after LLM post_process)."""
    out = dict(data)
    if proximos_items:
        g, c = build_compromisos_from_proximos_pasos(proximos_items, gorila_teams)
        out["compromisos_gorila"] = g
        out["compromisos_cliente"] = c
    out["asistentes"] = filter_calendar_only_attendees(out.get("asistentes") or [], raw_text)
    return out


def post_process_acta(
    data: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize asistentes, cliente heading, and compromiso routing."""
    out = dict(data)
    rows = data.get("asistentes") or []
    out["asistentes"] = [
        apply_alias_to_asistente_row(a.get("nombre", ""), a.get("puesto", ""))
        if isinstance(a, dict)
        else apply_alias_to_asistente_row("", "")
        for a in rows
    ]
    titulo = (data.get("titulo") or "").strip()
    cliente_raw = (data.get("cliente") or "").strip()
    out["cliente"] = compose_cliente_heading(titulo, cliente_raw)
    teams = (metadata or {}).get("gorila_teams") or []
    out["compromisos_gorila"], out["compromisos_cliente"] = reclassify_compromisos(
        data.get("compromisos_gorila"),
        data.get("compromisos_cliente"),
        gorila_teams=teams,
    )
    return out
