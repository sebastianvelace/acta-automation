"""
Canonical labels for calendar / Gemini team display names (not real people).
"""

from __future__ import annotations

import re
from typing import Any

from src.dates import fecha_entrega_for_compromiso
from src.client_contacts import (
    fold_person_name,
    invitado_fields_from_client_email,
    is_known_client_person,
    lookup_client_contact,
    lookup_client_contact_by_alias,
    lookup_client_contact_by_name,
)
from src.gorila_roster import (
    invitado_fields_from_email,
    invitado_fields_from_name,
    is_gorila_branded_email,
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
        "ADS Gorila Hosting": {"nombre": "ADS", "puesto": "Gorila Hosting"},
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
        "Web Gorila Hosting": {"nombre": "Web", "puesto": "Gorila Hosting"},
        "SEO Gorila Hosting": {"nombre": "SEO", "puesto": "Gorila Hosting"},
        "SEO - Gorila Hosting": {"nombre": "SEO", "puesto": "Gorila Hosting"},
        "Códigos Creativos": {"nombre": "Códigos Creativos", "puesto": "Gorila Hosting"},
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
    # Variantes mal escritas que aparecen en notas fuente (Grofit/Grofik).
    "grofit",
    "grofik",
)

# Cubre "Growfik" y sus erratas frecuentes "Grofit"/"Grofik" (case-insensitive).
_GROWFIK_DISPLAY = re.compile(r"(?i)\bgro(?:wfik|fit|fik)\b")


def normalize_gorila_compromiso_responsable_display(
    responsable: str,
    *,
    universal: bool = False,
) -> str:
    """
    Texto visible en acta: usar siempre nomenclatura **Gorila Hosting**, nunca marcas legacy.
    En actas Universal (``universal=True``) se conserva la marca Growfik.
    """
    s = _strip_bracket_tag((responsable or "").strip())
    if not s:
        return s
    # Colapsa espacios repetidos: equipos concatenados llegan con doble espacio
    # (ej. "Marketing  Administración Gorila Hosting").
    s = " ".join(s.split())
    if universal:
        return s
    s = _GROWFIK_DISPLAY.sub("Gorila Hosting", s)
    # Evita sufijo "Gorila Hosting" duplicado tras concatenar equipos.
    s = re.sub(r"(?i)(?:\bGorila Hosting\b\s*)+(?=\bGorila Hosting\b)", "", s)
    return s


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


def _lookup_proximos_person_alias(raw: str) -> str | None:
    """Display name / typo de Gemini → nombre canónico vía aliases en client_contacts.yaml."""
    contact = lookup_client_contact_by_alias(raw)
    return contact.name if contact else None


def _normalize_proximos_person_name(tag: str) -> str:
    """Title-case ALL CAPS person tags; strip stray dots (e.g. Samuel. Villalobos)."""
    raw = re.sub(r"(?<=\w)\.(?=\s+\w)", "", (tag or "").strip())
    alias = _lookup_proximos_person_alias(raw)
    if alias:
        raw = alias
    raw = re.sub(r"\s+", " ", raw).strip()
    if not raw or not _looks_like_person_name(raw):
        return raw
    if raw.isupper() or raw.islower():
        return " ".join(part.capitalize() for part in raw.split())
    return raw


def client_compromiso_responsable_from_tag(tag: str, *, client_label: str) -> str:
    """
    Responsable visible en compromisos_cliente: persona del tag Próximos pasos si aplica;
    si no, nombre de cuenta (client_label).
    """
    raw = _strip_bracket_tag((tag or "").strip())
    if not raw or raw.casefold() == client_label.casefold():
        return client_label
    if is_gorila_responsable(raw) or is_gorila_group_commitment_tag(raw):
        return client_label
    alias = lookup_team_alias(raw)
    if alias and (alias.get("puesto") or "").strip() == "Portal cliente":
        return client_label
    parts = raw.split()
    if len(parts) == 1:
        token = parts[0]
        alias = _lookup_proximos_person_alias(token)
        if alias:
            token = alias
        if token.isalpha() and len(token) >= 3:
            single = token.capitalize() if token.isupper() else token
            contact = lookup_client_contact_by_name(single)
            return contact.name if contact else single
        return client_label
    normalized = _normalize_proximos_person_name(raw)
    if _looks_like_person_name(normalized) and normalized.casefold() != client_label.casefold():
        contact = lookup_client_contact_by_name(normalized)
        return contact.name if contact else normalized
    return client_label


_ASUNTO_STOPWORDS = frozenset(
    {"de", "el", "la", "los", "las", "en", "y", "a", "del", "al", "un", "una", "por", "con"}
)


def _normalize_asunto_titulo(titulo: str) -> str:
    s = re.sub(r"^\s*\d+[.)]\s*", "", (titulo or "").strip())
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    tokens = [t for t in s.casefold().split() if t and t not in _ASUNTO_STOPWORDS]
    return " ".join(tokens)


def _asunto_titulos_overlap(a: str, b: str) -> bool:
    na, nb = _normalize_asunto_titulo(a), _normalize_asunto_titulo(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.65


def dedupe_asuntos_tratados(asuntos: list[Any]) -> list[dict[str, str]]:
    """Elimina asuntos duplicados (p. ej. eco Resumen vs Detalles); conserva la descripción más larga."""
    rows: list[dict[str, str]] = []
    for raw in asuntos or []:
        if not isinstance(raw, dict):
            continue
        titulo = (raw.get("titulo") or "").strip()
        desc = (raw.get("descripcion") or "").strip()
        if not titulo and not desc:
            continue
        rows.append({"titulo": titulo or "Sin título", "descripcion": desc})
    kept: list[dict[str, str]] = []
    for row in rows:
        merged = False
        for idx, existing in enumerate(kept):
            if _asunto_titulos_overlap(row["titulo"], existing["titulo"]):
                if len(row.get("descripcion") or "") > len(existing.get("descripcion") or ""):
                    kept[idx] = row
                merged = True
                break
        if not merged:
            kept.append(row)
    return kept


def is_universal_acta(
    *,
    cliente: str = "",
    titulo: str = "",
    attendee_emails: list[str] | None = None,
    source_filename: str = "",
) -> bool:
    blob = " ".join(filter(None, [cliente, titulo, source_filename]))
    if "universal" in blob.casefold():
        return True
    return any("@universal.edu.co" in (e or "").casefold() for e in (attendee_emails or []))


def _scrub_growfik_text(value: str) -> str:
    return _GROWFIK_DISPLAY.sub("Gorila Hosting", value or "")


def apply_growfik_visibility_policy(
    data: dict[str, Any],
    *,
    universal: bool,
) -> dict[str, Any]:
    """En actas no Universal, reemplaza menciones visibles de Growfik por Gorila Hosting.

    Growfik es una empresa independiente que solo figura en actas de Universal; el
    encabezado de compromisos refleja esa política (con o sin « & GROWFIK»).
    """
    out = dict(data)
    out["encabezado_compromisos_gorila"] = "GORILA & GROWFIK" if universal else "GORILA"
    if universal:
        return out
    for key in ("objetivo", "cierre", "cliente", "titulo", "lugar"):
        if isinstance(out.get(key), str):
            out[key] = _scrub_growfik_text(out[key])
    invitados: list[dict[str, str]] = []
    for inv in out.get("invitados") or []:
        if not isinstance(inv, dict):
            continue
        row = dict(inv)
        for field in ("nombre", "puesto"):
            if isinstance(row.get(field), str):
                row[field] = _scrub_growfik_text(row[field])
        invitados.append(row)
    if invitados:
        out["invitados"] = invitados
    for key in ("compromisos_gorila", "compromisos_cliente"):
        rows: list[dict[str, str]] = []
        for item in out.get(key) or []:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            for field in ("tarea", "responsable"):
                if isinstance(row.get(field), str):
                    row[field] = _scrub_growfik_text(row[field])
            rows.append(row)
        out[key] = rows
    asuntos: list[dict[str, str]] = []
    for item in out.get("asuntos_tratados") or []:
        if not isinstance(item, dict):
            continue
        asuntos.append(
            {
                "titulo": _scrub_growfik_text(str(item.get("titulo") or "")),
                "descripcion": _scrub_growfik_text(str(item.get("descripcion") or "")),
            }
        )
    if asuntos:
        out["asuntos_tratados"] = asuntos
    return out


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
    Build responsable string like "Marketing y Administración Gorila Hosting"
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
    if len(roles) == 2:
        equipos = " y ".join(roles)
    else:
        equipos = ", ".join(roles[:-1]) + " y " + roles[-1]
    return f"{equipos} Gorila Hosting"


def _merged_gorila_emails(dynamic: list[str] | None) -> list[str]:
    base = {e.casefold() for e in (dynamic or []) if e}
    base |= set(roster_emails())
    return list(base)


def _display_gorila_assignee(tag_or_responsable: str, *, universal: bool = False) -> str:
    raw = _strip_bracket_tag((tag_or_responsable or "").strip())
    if "," in raw:
        # Normaliza display names Gemini por parte (ej. «Sophia7 Marketing» → persona real).
        parts = [_normalize_proximos_person_name(p.strip()) for p in raw.split(",") if p.strip()]
        raw = ", ".join(parts)
    if universal and _GROWFIK_DISPLAY.search(raw):
        return raw
    return normalize_gorila_compromiso_responsable_display(
        responsable_for_tag(raw),
        universal=universal,
    )


def build_invitados_from_attendee_emails(
    emails: list[str],
    *,
    cliente_account: str = "",
    universal: bool = False,
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
        rows.append(
            invitado_fields_from_email(
                email, cliente_account=cliente_account, universal=universal
            )
        )
    return rows


def _gorila_team_sort_key(team_label: str) -> tuple[int, str]:
    label_cf = team_label.casefold()
    if "administraci" in label_cf:
        return (-1, label_cf)
    alias = lookup_team_alias(team_label)
    role = (alias or {}).get("nombre") or team_label
    role_cf = role.casefold()
    for idx, r in enumerate(_ROLE_ORDER):
        if r.casefold() == role_cf:
            return (idx, label_cf)
    return (len(_ROLE_ORDER), label_cf)


def _invitado_row_from_gorila_team(team_label: str) -> dict[str, str] | None:
    label = (team_label or "").strip()
    if not label:
        return None
    alias = lookup_team_alias(label)
    if not alias:
        return None
    nombre = alias["nombre"]
    if "administraci" in label.casefold():
        puesto = "Organizador"
    else:
        puesto = alias.get("puesto") or "Gorila Hosting"
    return {
        "correo": "",
        "nombre": nombre,
        "puesto": puesto,
        "asistencia": "Confirmado",
    }


def merge_invitados_from_gorila_teams(
    invitados: list[dict[str, str]],
    gorila_teams: list[str],
) -> list[dict[str, str]]:
    """Añade filas de equipos Gorila del bloque Invitado (antes de invitados por correo)."""
    teams = sorted({t.strip() for t in (gorila_teams or []) if t and t.strip()}, key=_gorila_team_sort_key)
    if not teams:
        return invitados
    team_rows: list[dict[str, str]] = []
    seen_names: set[str] = set()
    for team in teams:
        row = _invitado_row_from_gorila_team(team)
        if not row:
            continue
        key = row["nombre"].casefold()
        if key in seen_names:
            continue
        seen_names.add(key)
        team_rows.append(row)
    if not team_rows:
        return invitados
    email_rows = list(invitados)
    filtered_email_rows: list[dict[str, str]] = []
    for row in email_rows:
        nombre_cf = (row.get("nombre") or "").strip().casefold()
        if nombre_cf in seen_names:
            continue
        filtered_email_rows.append(row)
    return team_rows + filtered_email_rows


def _invitado_dedupe_key(row: dict[str, str]) -> str:
    correo = (row.get("correo") or "").strip().casefold()
    if correo:
        return f"email:{correo}"
    return f"name:{(row.get('nombre') or '').strip().casefold()}"


def _invitado_person_fold_key(row: dict[str, str]) -> str:
    email = (row.get("correo") or "").strip()
    contact = lookup_client_contact(email) if email else None
    name = contact.name if contact else (row.get("nombre") or "")
    folded = fold_person_name(name)
    if folded:
        return f"person:{folded}"
    if email:
        return f"email:{email.casefold()}"
    return f"name:{(row.get('nombre') or '').strip().casefold()}"


_ROLE_EMAIL_LOCALS = frozenset({"presidencia", "info", "contacto", "admin", "ventas"})


def _invitado_row_quality(row: dict[str, str]) -> tuple[int, int, int]:
    email = (row.get("correo") or "").strip()
    has_catalog = 1 if email and lookup_client_contact(email) else 0
    local = email.split("@")[0].casefold() if "@" in email else ""
    personal_email = 0 if local in _ROLE_EMAIL_LOCALS else 1
    return (has_catalog, personal_email, len((row.get("nombre") or "")))


def dedupe_invitados_by_person(invitados: list[dict[str, str]]) -> list[dict[str, str]]:
    """Una fila por persona: p. ej. presidencia@ y pedro.rodriguezh@ → mismo Pedro."""
    groups: dict[str, list[dict[str, str]]] = {}
    order: list[str] = []
    for row in invitados:
        key = _invitado_person_fold_key(row)
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(row)
    out: list[dict[str, str]] = []
    for key in order:
        rows = groups[key]
        if len(rows) == 1:
            out.append(rows[0])
        else:
            out.append(max(rows, key=_invitado_row_quality))
    return out


def _compromiso_dedupe_key(row: dict[str, str]) -> tuple[str, str]:
    resp = (row.get("responsable") or "").strip()
    if _looks_like_person_name(resp):
        resp_key = fold_person_name(resp)
    else:
        resp_key = resp.casefold()
    return (resp_key, (row.get("tarea") or "").strip().casefold())


def _dedupe_compromiso_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for row in rows:
        k = _compromiso_dedupe_key(row)
        if k in seen:
            continue
        seen.add(k)
        out.append(row)
    return out


def merge_invitados_from_proximos_tags(
    invitados: list[dict[str, str]],
    proximos_items: list[dict[str, str]] | None,
    *,
    gorila_person_names: list[str] | None = None,
    gorila_emails: list[str] | None = None,
    universal: bool = False,
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
        extra = invitado_fields_from_name(tag, universal=universal)
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
        if lookup_client_contact(email):
            continue
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


def _split_assignee_tag_parts(raw: str) -> list[str]:
    if "," not in raw:
        return [raw] if raw else []
    return [p.strip() for p in raw.split(",") if p.strip()]


def _comma_tag_assignee_kind(
    parts: list[str],
    *,
    gorila_person_names: list[str] | None = None,
    gorila_emails: list[str] | None = None,
) -> str | None:
    """Clasifica tags multi-persona: ``internal``, ``client`` o ``None`` (ambiguo)."""
    if len(parts) <= 1:
        return None
    kinds: list[str] = []
    for part in parts:
        if (
            is_roster_member(part)
            or is_gorila_responsable(part)
            or _is_growfik_domain_assignee(part)
            or is_internal_gorila_assignee(
                part,
                gorila_person_names=gorila_person_names,
                gorila_emails=gorila_emails,
            )
        ):
            kinds.append("internal")
        elif is_known_client_person(part):
            kinds.append("client")
        else:
            return None
    if kinds and all(k == "internal" for k in kinds):
        return "internal"
    if kinds and all(k == "client" for k in kinds):
        return "client"
    return None


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
    parts = _split_assignee_tag_parts(raw)
    if len(parts) > 1:
        kind = _comma_tag_assignee_kind(
            parts,
            gorila_person_names=gorila_person_names,
            gorila_emails=gorila_emails,
        )
        if kind == "internal":
            return True
        if kind == "client":
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
    normalized = _normalize_proximos_person_name(raw)
    if is_known_client_person(normalized) or is_known_client_person(raw):
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
    r"(?:doctora|dr\.?|ingrid|pedro|tatiana)\b"
)

_CLIENT_SUBMISSION_RE = re.compile(
    r"(?i)\bremitir\b.{0,120}\b(?:contenido|video(?:s)?)\b.{0,120}\bcorreo personal\b"
)


def _is_client_deliverable_despite_gorila_tag(tag: str, descripcion: str) -> bool:
    """Marketing/Social tag but entrega explícita al cliente → compromiso_cliente."""
    if not is_gorila_responsable(tag):
        return False
    return bool(_CLIENT_DELIVERY_RE.search(descripcion or ""))


def _is_client_submission_despite_gorila_tag(tag: str, descripcion: str) -> bool:
    """Gorila tag but cliente remite material grabado → compromiso_cliente."""
    if not is_gorila_responsable(tag):
        return False
    return bool(_CLIENT_SUBMISSION_RE.search(descripcion or ""))


def build_compromisos_from_proximos_pasos(
    items: list[dict[str, str]],
    gorila_teams: list[str],
    *,
    gorila_person_names: list[str] | None = None,
    gorila_emails: list[str] | None = None,
    cliente_responsable: str | None = None,
    meeting_date_str: str = "",
    universal: bool = False,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """
    Deterministic routing from Gemini ``Próximos pasos``:
    [El grupo] / [Todos] → only ``compromisos_gorila`` with inferred Gorila responsable;
    client-side tags → ``compromisos_cliente`` with ``responsable`` = persona del tag o cuenta.
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
        client_resp = client_compromiso_responsable_from_tag(tag, client_label=client_label)
        row = {
            "tarea": desc,
            "responsable": "",
            "fecha_entrega": fecha_entrega_for_compromiso(desc, meeting_date_str),
        }
        if _is_client_deliverable_despite_gorila_tag(tag, desc) or _is_client_submission_despite_gorila_tag(
            tag, desc
        ):
            row["responsable"] = client_resp
            out_c.append(dict(row))
        elif is_gorila_group_commitment_tag(tag):
            row["responsable"] = normalize_gorila_compromiso_responsable_display(
                inferred,
                universal=universal,
            )
            out_g.append(dict(row))
        elif is_gorila_responsable(tag) or is_internal_gorila_assignee(
            tag,
            gorila_person_names=gorila_person_names,
            gorila_emails=gorila_emails,
        ):
            row["responsable"] = _display_gorila_assignee(tag, universal=universal)
            out_g.append(dict(row))
        else:
            row["responsable"] = client_resp
            out_c.append(dict(row))
    return _dedupe_compromiso_rows(out_g), _dedupe_compromiso_rows(out_c)


def _strip_trailing_punctuation(value: str) -> str:
    return (value or "").strip().rstrip(".,;:")


def _compact_brand_key(value: str) -> str:
    base = re.sub(r"[^a-z0-9]", "", (value or "").casefold())
    # Gemini suele escribir «Revela» en notas de la cuenta Rebella.
    if base in ("revela", "rebella", "rebela"):
        return "rebella"
    # Variantes de cuenta Universal (Idiomas, Academia de Idiomas, Redes, …).
    if base.startswith("universal"):
        return "universal"
    return re.sub(r"(.)\1+", r"\1", base)


def _same_client_account(a: str, b: str) -> bool:
    """True when two labels refer to the same account (e.g. Lattir / La TIR)."""
    ka, kb = _compact_brand_key(a), _compact_brand_key(b)
    if not ka or not kb:
        return False
    return ka == kb or ka in kb or kb in ka


def compose_cliente_heading(titulo: str, cliente: str) -> str:
    """
    Build the acta heading shown in the Cliente field: meeting name + account.

    Manual actas use values like ``Revisión Pauta - Real State``. When the LLM
    already returns that full string in ``cliente``, it is preserved as-is.
    """
    t = _strip_trailing_punctuation(titulo)
    c = _strip_trailing_punctuation(cliente)
    if not c:
        return t or "No especificado"
    if not t:
        return c
    if t and c.startswith(f"{t} - "):
        extra = c[len(t) + 3 :].strip()
        suffix = t.rsplit(" - ", 1)[-1].strip() if " - " in t else t
        if extra and _same_client_account(suffix, extra):
            return t
    if " - " in c:
        parts = [p.strip() for p in c.split(" - ") if p.strip()]
        if len(parts) >= 2 and parts[-1].casefold() == parts[-2].casefold():
            return " - ".join(parts[:-1])
        return c
    if t.casefold() == c.casefold():
        return t
    if c.casefold() in t.casefold():
        return t
    t_account = _account_from_meeting_title(t)
    if t_account and _same_client_account(t_account, c):
        return t
    if " - " in t:
        suffix = t.rsplit(" - ", 1)[-1].strip()
        if suffix.casefold() == c.casefold() or _same_client_account(suffix, c):
            return t
    return f"{t} - {c}"


_MEETING_TITLE_PREFIXES = (
    "Seguimiento",
    "Revisión",
    "Actualización",
    "Estrategia",
    "Propuesta",
    "Reunión",
    "Redes",
)


def _account_from_meeting_title(label: str) -> str | None:
    """«Estrategia Rebella» / «Seguimiento Barrera Estrada» → cuenta tras el prefijo de reunión."""
    text = _strip_trailing_punctuation(label)
    if not text or " - " in text:
        return None
    for prefix in _MEETING_TITLE_PREFIXES:
        lead = f"{prefix} "
        if text.startswith(lead):
            suffix = text[len(lead) :].strip()
            if suffix and suffix.casefold() != prefix.casefold():
                return suffix
    return None


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
    for label in (c, t):
        account = _account_from_meeting_title(label)
        if account:
            return account
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
    universal: bool = False,
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
            dup["responsable"] = normalize_gorila_compromiso_responsable_display(
                inferred,
                universal=universal,
            )
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
                normed["responsable"] = _display_gorila_assignee(
                    normed["responsable"],
                    universal=universal,
                )
                out_gorila.append(normed)
        else:
            if k not in seen_c:
                seen_c.add(k)
                dup = dict(item)
                dup["responsable"] = client_compromiso_responsable_from_tag(
                    resp, client_label=client_label
                )
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
    source_filename: str = "",
) -> dict[str, Any]:
    """Compromisos determinísticos + participantes por correo (post LLM)."""
    _ = raw_text
    meta = metadata or {}
    teams = meta.get("gorila_teams") or []
    gorila_person_names = meta.get("gorila_person_names") or []
    gorila_emails = _merged_gorila_emails(meta.get("gorila_emails"))
    attendee_emails = meta.get("attendee_emails") or meta.get("client_emails") or []

    out = dict(data)
    titulo = str(out.get("titulo") or "")
    cliente_label = client_account_responsable(
        str(out.get("cliente") or ""),
        titulo,
    )
    universal = is_universal_acta(
        cliente=str(out.get("cliente") or ""),
        titulo=titulo,
        attendee_emails=attendee_emails,
        source_filename=source_filename,
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
            universal=universal,
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
            universal=universal,
        )
        out["compromisos_gorila"] = g
        out["compromisos_cliente"] = c

    invitados = build_invitados_from_attendee_emails(
        attendee_emails,
        cliente_account=cliente_label,
        universal=universal,
    )
    invitados = merge_invitados_from_gorila_teams(invitados, teams)
    invitados = merge_invitados_from_proximos_tags(
        invitados,
        proximos_items,
        gorila_person_names=gorila_person_names,
        gorila_emails=gorila_emails,
        universal=universal,
    )
    _enrich_invitados_from_proximos_names(
        invitados,
        proximos_items,
        gorila_person_names=gorila_person_names,
        gorila_emails=gorila_emails,
    )
    out["invitados"] = dedupe_invitados_by_person(invitados)
    cliente_raw = str(out.get("cliente") or "").strip()
    titulo_account = _account_from_meeting_title(titulo)
    if titulo_account and cliente_raw and _same_client_account(titulo_account, cliente_raw):
        cliente_raw = titulo_account
    elif not cliente_raw or cliente_raw.casefold() == titulo.casefold():
        for email in attendee_emails:
            contact = lookup_client_contact(email)
            if contact and (contact.role or "").strip():
                cliente_raw = contact.role.strip()
                break
    out["cliente"] = compose_cliente_heading(titulo, cliente_raw)
    out["asuntos_tratados"] = dedupe_asuntos_tratados(out.get("asuntos_tratados"))
    return apply_growfik_visibility_policy(out, universal=universal)


def _is_fallback_invitado(row: dict[str, str]) -> bool:
    """True when the invitado's nombre was derived from the email local-part (not catalog-enriched)."""
    email = (row.get("correo") or "").strip()
    if not email:
        return False
    if is_gorila_branded_email(email):
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
        normalized = _normalize_proximos_person_name(tag)
        if _looks_like_person_name(normalized):
            key = normalized.casefold()
            if key not in seen:
                seen.add(key)
                client_names.append(normalized)
    if not client_names:
        return
    covered = {_invitado_person_fold_key(r) for r in invitados}
    remaining: list[str] = []
    for name in client_names:
        contact = lookup_client_contact_by_name(name)
        if contact:
            row = invitado_fields_from_client_email(contact.email)
            if row and _invitado_person_fold_key(row) not in covered:
                invitados.append(row)
                covered.add(_invitado_person_fold_key(row))
            continue
        remaining.append(name)
    if not remaining:
        return
    fallback_idxs = [i for i, row in enumerate(invitados) if _is_fallback_invitado(row)]
    if not fallback_idxs:
        return
    if len(fallback_idxs) == 1:
        invitados[fallback_idxs[0]]["nombre"] = remaining[0]
    elif len(fallback_idxs) == len(remaining):
        for idx, name in zip(fallback_idxs, remaining):
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
    attendee_emails = (metadata or {}).get("attendee_emails") or []
    universal = is_universal_acta(
        cliente=out["cliente"],
        titulo=titulo,
        attendee_emails=attendee_emails,
    )
    out["compromisos_gorila"], out["compromisos_cliente"] = reclassify_compromisos(
        data.get("compromisos_gorila"),
        data.get("compromisos_cliente"),
        gorila_teams=teams,
        gorila_person_names=(metadata or {}).get("gorila_person_names") or [],
        gorila_emails=_merged_gorila_emails((metadata or {}).get("gorila_emails")),
        cliente_responsable=cliente_label,
        universal=universal,
    )
    out["asuntos_tratados"] = dedupe_asuntos_tratados(out.get("asuntos_tratados"))
    return apply_growfik_visibility_policy(out, universal=universal)
