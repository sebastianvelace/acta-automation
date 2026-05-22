"""
Canonical labels for calendar / Gemini team display names (not real people).
"""

from __future__ import annotations

import re
from typing import Any

from src.dates import fecha_entrega_for_compromiso
from src.client_contacts import invitado_fields_from_client_email
from src.gorila_roster import (
    invitado_fields_from_email,
    invitado_fields_from_name,
    is_roster_member,
    lookup_staff_by_email,
    match_roster_member,
    responsable_for_tag,
    roster_emails,
)

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
    r"(?i)^\[?\s*(el\s+grupo|the\s+group|todos|ambos\s+equipos)\s*\]?$"
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
    # Marca legacy en etiquetas históricas; no debe mostrarse en PDF — ver normalize_* abajo.
    "growfik",
)

_GROWFIK_DISPLAY = re.compile(r"(?i)\bgrowfik\b")


def normalize_gorila_compromiso_responsable_display(responsable: str) -> str:
    """
    Texto visible en acta: usar siempre nomenclatura **Gorila Hosting**, nunca marcas legacy.
    """
    s = _strip_bracket_tag((responsable or "").strip())
    if not s:
        return s
    return _GROWFIK_DISPLAY.sub("Gorila Hosting", s)


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


def looks_like_person_name(s: str) -> bool:
    """Heuristic: several tokens, mostly letters, no @ — típico 'Apellido Nombre'."""
    return _looks_like_person_name(s)


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


def _merged_gorila_emails(dynamic: list[str] | None) -> list[str]:
    base = {e.casefold() for e in (dynamic or []) if e}
    base |= set(roster_emails())
    return list(base)


def _display_gorila_assignee(tag_or_responsable: str) -> str:
    raw = _strip_bracket_tag((tag_or_responsable or "").strip())
    return normalize_gorila_compromiso_responsable_display(responsable_for_tag(raw))


def build_invitados_from_attendee_emails(
    emails: list[str],
    *,
    cliente_account: str = "",
) -> list[dict[str, str]]:
    """
    Invitados del acta: correos del bloque Invitado, enriquecidos con roster Gorila (O(1) por email).
    """
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in emails:
        email = (raw or "").strip()
        if not email:
            continue
        key = email.casefold()
        if key in seen:
            continue
        seen.add(key)
        rows.append(invitado_fields_from_email(email, cliente_account=cliente_account))
    return rows


def _invitado_dedupe_key(row: dict[str, str]) -> str:
    correo = (row.get("correo") or "").strip().casefold()
    if correo:
        return f"email:{correo}"
    return f"name:{(row.get('nombre') or '').strip().casefold()}"


def merge_invitados_from_proximos_tags(
    invitados: list[dict[str, str]],
    proximos_items: list[dict[str, str]] | None,
    *,
    gorila_person_names: list[str] | None = None,
    gorila_emails: list[str] | None = None,
) -> list[dict[str, str]]:
    """Añade invitados internos que aparecen en tags de Próximos pasos pero no en correos."""
    if not proximos_items:
        return invitados
    rows = list(invitados)
    seen = {_invitado_dedupe_key(r) for r in rows}
    for it in proximos_items:
        tag = (it.get("tag") or "").strip()
        if not tag or not is_internal_gorila_assignee(
            tag,
            gorila_person_names=gorila_person_names,
            gorila_emails=gorila_emails,
        ):
            continue
        extra = invitado_fields_from_name(tag)
        if not extra:
            continue
        key = _invitado_dedupe_key(extra)
        if key in seen:
            continue
        seen.add(key)
        rows.append(extra)
    return rows


def _name_matches_gorila_person(tag: str, gorila_person_names: list[str]) -> bool:
    raw = _strip_bracket_tag((tag or "").strip())
    if not raw:
        return False
    raw_cf = raw.casefold()
    for full in gorila_person_names:
        nf = full.casefold()
        if raw_cf == nf or raw_cf in nf or nf in raw_cf:
            return True
        raw_parts = raw_cf.split()
        name_parts = nf.split()
        if raw_parts and name_parts and raw_parts[0][:4] == name_parts[0][:4]:
            return True
    return False


def _tag_matches_gorila_email_person(tag: str, gorila_emails: list[str]) -> bool:
    raw = _strip_bracket_tag((tag or "").strip()).casefold()
    if not raw or "@" in raw:
        return False
    tokens = [t for t in re.findall(r"[a-záéíóúñ]+", raw) if len(t) > 2]
    if not tokens:
        return False
    first = tokens[0][:4]
    for email in gorila_emails:
        local = re.sub(r"[^a-z]", "", email.split("@")[0].casefold())
        if first and local.startswith(first):
            return True
    return False


def _is_growfik_domain_assignee(tag_or_responsable: str) -> bool:
    """Correo @growfik.com o mención explícita Growfik en tag/responsable."""
    raw = _strip_bracket_tag((tag_or_responsable or "").strip())
    if not raw:
        return False
    if "@" in raw and raw.casefold().endswith("@growfik.com"):
        return True
    return "growfik" in raw.casefold()


def is_internal_gorila_assignee(
    tag_or_responsable: str,
    *,
    gorila_person_names: list[str] | None = None,
    gorila_emails: list[str] | None = None,
) -> bool:
    """Persona o etiqueta que corresponde a personal interno Gorila (no cuenta/cliente)."""
    raw = _strip_bracket_tag((tag_or_responsable or "").strip())
    if not raw:
        return False
    if _is_growfik_domain_assignee(raw):
        return True
    alias = lookup_team_alias(raw)
    if alias and (alias.get("puesto") or "").strip() == "Portal cliente":
        return False
    if is_roster_member(raw):
        return True
    if is_gorila_responsable(raw):
        return True
    if is_gorila_group_commitment_tag(raw):
        return False
    names = gorila_person_names or []
    emails = gorila_emails or []
    if _name_matches_gorila_person(raw, names):
        return True
    if _tag_matches_gorila_email_person(raw, emails):
        return True
    return False


def is_gorila_responsable(responsable: str) -> bool:
    """True when the assignee is an internal Gorila Hosting team (not a client-side person).

    Labels that contain legacy ``growfik`` still classify as internal; texto en PDF se normaliza vía
    ``normalize_gorila_compromiso_responsable_display``.
    """
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


_CLIENT_DELIVERY_RE = re.compile(
    r"(?i)\bentregar\b.{0,120}\b(?:a\s+la|al)\s+"
    r"(?:doctora|dr\.?|cliente|ingrid|pedro|tatiana)\b"
)


def _is_client_deliverable_despite_gorila_tag(tag: str, descripcion: str) -> bool:
    """Marketing/Social tag but entrega explícita al cliente → compromiso_cliente."""
    if not is_gorila_responsable(tag):
        return False
    return bool(_CLIENT_DELIVERY_RE.search(descripcion or ""))


def _proximos_desc_index(items: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {((it.get("descripcion") or "").strip().casefold()): it for it in items if it.get("descripcion")}


def _merge_compromiso_rows(rows: list[dict[str, str]]) -> dict[str, str]:
    if not rows:
        return {"tarea": "", "responsable": "", "fecha_entrega": "No especificada"}
    if len(rows) == 1:
        return dict(rows[0])
    tareas = [r["tarea"] for r in rows if r.get("tarea")]
    fechas = [r["fecha_entrega"] for r in rows if r.get("fecha_entrega") and r["fecha_entrega"] != "No especificada"]
    return {
        "tarea": "; ".join(tareas),
        "responsable": rows[0]["responsable"],
        "fecha_entrega": fechas[0] if fechas else rows[0].get("fecha_entrega", "No especificada"),
    }


def _merge_cliente_parrilla_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Une tareas cliente sobre la misma parrilla/seguimiento (p. ej. Barrera)."""
    if len(rows) < 2:
        return rows
    parrilla_keys = ("parrilla", "calendario de contenidos", "material de trabajo", "abogado")
    parrilla_rows: list[dict[str, str]] = []
    rest: list[dict[str, str]] = []
    for row in rows:
        blob = row["tarea"].casefold()
        if any(k in blob for k in parrilla_keys):
            parrilla_rows.append(row)
        else:
            rest.append(row)
    if len(parrilla_rows) >= 2:
        rest.insert(0, _merge_compromiso_rows(parrilla_rows))
        return rest
    return rows


def consolidate_compromisos_from_proximos(
    gorila: list[dict[str, str]],
    cliente: list[dict[str, str]],
    proximos_items: list[dict[str, str]] | None,
    gorila_teams: list[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """
    Compacta filas duplicadas para alinear densidad con actas manuales:
    - [El grupo]/[The group] → una fila
    - 3+ tareas con el mismo tag persona → una fila
    - 2+ tareas de equipo Gorila cuando también hay 3+ de una persona interna
    """
    if not proximos_items:
        return gorila, _merge_cliente_parrilla_rows(cliente)

    desc_index = _proximos_desc_index(proximos_items)
    group_rows: list[dict[str, str]] = []
    other_g: list[dict[str, str]] = []
    tag_counts: dict[str, int] = {}
    for it in proximos_items:
        tag_cf = (it.get("tag") or "").strip().casefold()
        if tag_cf:
            tag_counts[tag_cf] = tag_counts.get(tag_cf, 0) + 1

    for row in gorila:
        prox = desc_index.get(row["tarea"].casefold(), {})
        tag = (prox.get("tag") or "").strip()
        if is_gorila_group_commitment_tag(tag):
            group_rows.append(row)
        else:
            other_g.append(row)

    merged_g: list[dict[str, str]] = []
    if group_rows:
        merged_g.append(_merge_compromiso_rows(group_rows))

    person_tags_3plus = {
        t
        for t, n in tag_counts.items()
        if n >= 3 and not is_gorila_group_commitment_tag(t) and not is_gorila_responsable(t)
    }
    roster_person_tags_2plus = {
        t
        for t, n in tag_counts.items()
        if n >= 2
        and not is_gorila_group_commitment_tag(t)
        and not is_gorila_responsable(t)
        and match_roster_member(t)
    }

    by_tag: dict[str, list[dict[str, str]]] = {}
    tag_order: list[str] = []
    for row in other_g:
        prox = desc_index.get(row["tarea"].casefold(), {})
        tag_cf = (prox.get("tag") or "").strip().casefold() or f"__row__:{row['tarea'].casefold()}"
        if tag_cf not in by_tag:
            by_tag[tag_cf] = []
            tag_order.append(tag_cf)
        by_tag[tag_cf].append(row)

    for tag_cf in tag_order:
        bucket = by_tag[tag_cf]
        if (
            tag_cf in person_tags_3plus
            or tag_cf in roster_person_tags_2plus
        ):
            merged_g.append(_merge_compromiso_rows(bucket))
        else:
            merged_g.extend(bucket)

    if len(merged_g) > 4:
        team_buckets: dict[str, list[dict[str, str]]] = {}
        team_order: list[str] = []
        final_g: list[dict[str, str]] = []
        for row in merged_g:
            prox = desc_index.get(row["tarea"].casefold(), {})
            tag = (prox.get("tag") or "").strip()
            tag_cf = tag.casefold()
            if is_gorila_responsable(tag) and tag_counts.get(tag_cf, 0) >= 2:
                if tag_cf not in team_buckets:
                    team_buckets[tag_cf] = []
                    team_order.append(tag_cf)
                team_buckets[tag_cf].append(row)
            else:
                final_g.append(row)
        for tag_cf in team_order:
            final_g.append(_merge_compromiso_rows(team_buckets[tag_cf]))
        merged_g = final_g

    return merged_g, _merge_cliente_parrilla_rows(cliente)


def build_compromisos_from_proximos_pasos(
    items: list[dict[str, str]],
    gorila_teams: list[str],
    *,
    gorila_person_names: list[str] | None = None,
    gorila_emails: list[str] | None = None,
    cliente_responsable: str | None = None,
    meeting_date_str: str = "",
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """
    Deterministic routing from Gemini ``Próximos pasos``:
    [El grupo] / [Todos] → only ``compromisos_gorila`` with inferred Gorila responsable;
    client-side tags → ``compromisos_cliente`` with ``responsable`` = empresa/cuenta.
    """
    out_g: list[dict[str, str]] = []
    out_c: list[dict[str, str]] = []
    inferred = infer_gorila_responsable(gorila_teams, for_grupo_task=True)
    client_label = (cliente_responsable or "").strip() or "No especificado"
    for it in items:
        tag = (it.get("tag") or "").strip()
        desc = (it.get("descripcion") or "").strip()
        if not desc:
            continue
        row = {
            "tarea": desc,
            "responsable": "",
            "fecha_entrega": fecha_entrega_for_compromiso(desc, meeting_date_str),
        }
        if _is_client_deliverable_despite_gorila_tag(tag, desc):
            row["responsable"] = client_label
            out_c.append(dict(row))
        elif is_gorila_group_commitment_tag(tag):
            row["responsable"] = normalize_gorila_compromiso_responsable_display(inferred)
            out_g.append(dict(row))
        elif is_gorila_responsable(tag) or is_internal_gorila_assignee(
            tag,
            gorila_person_names=gorila_person_names,
            gorila_emails=gorila_emails,
        ):
            row["responsable"] = _display_gorila_assignee(tag)
            out_g.append(dict(row))
        else:
            row["responsable"] = client_label
            out_c.append(dict(row))
    return consolidate_compromisos_from_proximos(out_g, out_c, items, gorila_teams)


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


def client_account_responsable(cliente: str, titulo: str = "") -> str:
    """
    Nombre de empresa/cuenta para la columna ``responsable`` en ``compromisos_cliente``.
    Preferimos el sufijo tras `` - `` (p. ej. «Real State» en «Revisión Pauta - Real State»).
    """
    c = (cliente or "").strip()
    t = (titulo or "").strip()
    if not c and not t:
        return "No especificado"
    if " - " in c:
        return c.rsplit(" - ", 1)[-1].strip() or c
    if t and " - " in t:
        suffix = t.rsplit(" - ", 1)[-1].strip()
        if suffix and suffix.casefold() != t.casefold():
            if not c or c.casefold() == suffix.casefold() or suffix.casefold() in c.casefold():
                return suffix
    return c or t or "No especificado"


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
    gorila_person_names: list[str] | None = None,
    gorila_emails: list[str] | None = None,
    cliente_responsable: str | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """
    Route commitments by responsable: Gorila Hosting teams → gorila;
    client-side people → cliente; [El grupo]/[Todos] → **solo** gorila (no duplicar en cliente).
    """
    teams = gorila_teams or []
    inferred = infer_gorila_responsable(teams, for_grupo_task=True)
    client_label = (cliente_responsable or "").strip() or "No especificado"

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
            dup["responsable"] = normalize_gorila_compromiso_responsable_display(inferred)
            if k not in seen_g:
                seen_g.add(k)
                out_gorila.append(dup)
        elif is_gorila_responsable(resp) or is_internal_gorila_assignee(
            resp,
            gorila_person_names=gorila_person_names,
            gorila_emails=gorila_emails,
        ):
            if k not in seen_g:
                seen_g.add(k)
                normed = dict(item)
                normed["responsable"] = _display_gorila_assignee(normed["responsable"])
                out_gorila.append(normed)
        else:
            if k not in seen_c:
                seen_c.add(k)
                dup = dict(item)
                dup["responsable"] = client_label
                out_cliente.append(dup)

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
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compromisos determinísticos + participantes por correo (post LLM)."""
    _ = raw_text
    meta = metadata or {}
    teams = meta.get("gorila_teams") or []
    gorila_person_names = meta.get("gorila_person_names") or []
    gorila_emails = _merged_gorila_emails(meta.get("gorila_emails"))
    attendee_emails = meta.get("attendee_emails") or meta.get("client_emails") or []

    out = dict(data)
    cliente_label = client_account_responsable(
        str(out.get("cliente") or ""),
        str(out.get("titulo") or ""),
    )
    meeting_date_str = str(out.get("fecha") or meta.get("date") or "")
    if proximos_items:
        g, c = build_compromisos_from_proximos_pasos(
            proximos_items,
            teams,
            gorila_person_names=gorila_person_names,
            gorila_emails=gorila_emails,
            cliente_responsable=cliente_label,
            meeting_date_str=meeting_date_str,
        )
        out["compromisos_gorila"] = g
        out["compromisos_cliente"] = c
    else:
        g, c = reclassify_compromisos(
            out.get("compromisos_gorila"),
            out.get("compromisos_cliente"),
            gorila_teams=teams,
            gorila_person_names=gorila_person_names,
            gorila_emails=gorila_emails,
            cliente_responsable=cliente_label,
        )
        out["compromisos_gorila"] = g
        out["compromisos_cliente"] = c

    invitados = build_invitados_from_attendee_emails(attendee_emails, cliente_account=cliente_label)
    invitados = merge_invitados_from_proximos_tags(
        invitados,
        proximos_items,
        gorila_person_names=gorila_person_names,
        gorila_emails=gorila_emails,
    )
    _enrich_invitados_from_proximos_names(
        invitados,
        proximos_items,
        gorila_person_names=gorila_person_names,
        gorila_emails=gorila_emails,
    )
    out["invitados"] = invitados
    titulo = str(out.get("titulo") or "")
    out["cliente"] = compose_cliente_heading(titulo, str(out.get("cliente") or ""))
    return out


def _is_fallback_invitado(row: dict[str, str]) -> bool:
    """True when the invitado's nombre was derived from the email local-part (not catalog-enriched)."""
    email = (row.get("correo") or "").strip()
    if not email:
        return False
    return lookup_staff_by_email(email) is None and invitado_fields_from_client_email(email) is None


def _enrich_invitados_from_proximos_names(
    invitados: list[dict[str, str]],
    proximos_items: list[dict[str, str]] | None,
    *,
    gorila_person_names: list[str],
    gorila_emails: list[str],
) -> None:
    """Assign person names found in Próximos pasos client tags to fallback invitado rows.

    Applies only when there is a clear 1-to-1 (or N-to-N) mapping between
    un-catalogued client emails and unique client person names in tags.
    """
    if not proximos_items or not invitados:
        return
    client_names: list[str] = []
    seen: set[str] = set()
    for it in proximos_items:
        tag = (it.get("tag") or "").strip()
        if not tag:
            continue
        if is_gorila_group_commitment_tag(tag):
            continue
        if is_internal_gorila_assignee(
            tag, gorila_person_names=gorila_person_names, gorila_emails=gorila_emails
        ):
            continue
        if _looks_like_person_name(tag) and not tag.isupper():
            key = tag.casefold()
            if key not in seen:
                seen.add(key)
                client_names.append(tag)
    if not client_names:
        return
    fallback_idxs = [i for i, row in enumerate(invitados) if _is_fallback_invitado(row)]
    if not fallback_idxs:
        return
    if len(fallback_idxs) == 1:
        invitados[fallback_idxs[0]]["nombre"] = client_names[0]
    elif len(fallback_idxs) == len(client_names):
        for idx, name in zip(fallback_idxs, client_names):
            invitados[idx]["nombre"] = name


def post_process_acta(
    data: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize invitados, cliente heading, and compromiso routing."""
    out = dict(data)
    out.setdefault("invitados", [])
    titulo = (data.get("titulo") or "").strip()
    cliente_raw = (data.get("cliente") or "").strip()
    out["cliente"] = compose_cliente_heading(titulo, cliente_raw)
    cliente_label = client_account_responsable(out["cliente"], titulo)
    teams = (metadata or {}).get("gorila_teams") or []
    out["compromisos_gorila"], out["compromisos_cliente"] = reclassify_compromisos(
        data.get("compromisos_gorila"),
        data.get("compromisos_cliente"),
        gorila_teams=teams,
        gorila_person_names=(metadata or {}).get("gorila_person_names") or [],
        gorila_emails=_merged_gorila_emails((metadata or {}).get("gorila_emails")),
        cliente_responsable=cliente_label,
    )
    return out
