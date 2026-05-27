"""
Catálogo fijo de integrantes Gorila Hosting (data/gorila_staff.yaml).

Usado para clasificar compromisos: nadie del roster debe ir a compromisos_cliente.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from src.client_contacts import invitado_fields_from_client_email

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ROSTER_PATH = _REPO_ROOT / "data" / "gorila_staff.yaml"

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


@dataclass(frozen=True)
class GorilaStaff:
    canonical_name: str
    emails: tuple[str, ...]
    role: str
    aliases: tuple[str, ...]


def normalize_name(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    s = " ".join((text or "").split()).casefold()
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def _strip_bracket_tag(s: str) -> str:
    t = (s or "").strip()
    m = re.match(r"^\[(.+)\]$", t)
    return m.group(1).strip() if m else t


def _load_raw_roster() -> list[dict[str, Any]]:
    if not _ROSTER_PATH.is_file():
        raise FileNotFoundError(f"No se encontró el roster Gorila: {_ROSTER_PATH}")
    data = yaml.safe_load(_ROSTER_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Formato inválido en {_ROSTER_PATH}")
    staff = data.get("staff")
    if not isinstance(staff, list) or not staff:
        raise ValueError(f"Lista 'staff' vacía o ausente en {_ROSTER_PATH}")
    return staff


@lru_cache(maxsize=1)
def load_gorila_staff() -> tuple[GorilaStaff, ...]:
    out: list[GorilaStaff] = []
    for row in _load_raw_roster():
        if not isinstance(row, dict):
            continue
        name = str(row.get("canonical_name") or "").strip()
        if not name:
            continue
        emails_raw = row.get("emails") or []
        emails = tuple(str(e).strip().casefold() for e in emails_raw if str(e).strip())
        aliases_raw = row.get("aliases") or []
        aliases = tuple(str(a).strip() for a in aliases_raw if str(a).strip())
        role = str(row.get("role") or "").strip()
        out.append(
            GorilaStaff(
                canonical_name=name,
                emails=emails,
                role=role,
                aliases=aliases,
            )
        )
    if not out:
        raise ValueError(f"Ningún integrante válido en {_ROSTER_PATH}")
    return tuple(out)


@lru_cache(maxsize=1)
def roster_emails() -> frozenset[str]:
    emails: set[str] = set()
    for member in load_gorila_staff():
        emails.update(member.emails)
    return frozenset(emails)


@lru_cache(maxsize=1)
def _build_indexes() -> tuple[dict[str, GorilaStaff], dict[str, GorilaStaff], dict[str, GorilaStaff]]:
    """exact_names, email_map, unique_first_names."""
    exact: dict[str, GorilaStaff] = {}
    by_email: dict[str, GorilaStaff] = {}
    first_name_counts: dict[str, int] = {}

    for member in load_gorila_staff():
        keys = {member.canonical_name, *member.aliases}
        for k in keys:
            nk = normalize_name(k)
            if nk:
                exact[nk] = member
        for email in member.emails:
            by_email[email.casefold()] = member
        parts = normalize_name(member.canonical_name).split()
        if parts:
            first_name_counts[parts[0]] = first_name_counts.get(parts[0], 0) + 1

    unique_first: dict[str, GorilaStaff] = {}
    for member in load_gorila_staff():
        parts = normalize_name(member.canonical_name).split()
        if parts and first_name_counts.get(parts[0], 0) == 1:
            unique_first[parts[0]] = member

    return exact, by_email, unique_first


def _match_by_name_tokens(raw: str, staff: tuple[GorilaStaff, ...]) -> GorilaStaff | None:
    """Apellido + al menos un nombre en común (p. ej. Marco + Gonzalez)."""
    tokens = [t for t in normalize_name(raw).split() if len(t) > 1]
    if len(tokens) < 2:
        return None
    candidates: list[GorilaStaff] = []
    for member in staff:
        member_tokens = set(normalize_name(member.canonical_name).split())
        member_tokens.update(normalize_name(a) for a in member.aliases)
        member_tokens = {t for t in member_tokens if len(t) > 1}
        overlap = set(tokens) & member_tokens
        if len(overlap) >= 2:
            candidates.append(member)
        elif len(overlap) == 1 and len(tokens) >= 2:
            # one token match + surname match heuristic
            surnames = {t for t in member_tokens if t not in overlap}
            if surnames & set(tokens):
                candidates.append(member)
    if len(candidates) == 1:
        return candidates[0]
    return None


def match_roster_member(tag_or_responsable: str) -> GorilaStaff | None:
    raw = _strip_bracket_tag((tag_or_responsable or "").strip())
    if not raw:
        return None

    exact, by_email, unique_first = _build_indexes()
    staff = load_gorila_staff()

    if _EMAIL_RE.match(raw):
        return by_email.get(raw.casefold())

    nk = normalize_name(raw)
    if nk in exact:
        return exact[nk]

    if nk in unique_first:
        return unique_first[nk]

    token_match = _match_by_name_tokens(raw, staff)
    if token_match:
        return token_match

    return None


def is_roster_member(tag_or_responsable: str) -> bool:
    return match_roster_member(tag_or_responsable) is not None


def lookup_staff_by_email(email: str) -> GorilaStaff | None:
    """Match exacto case-insensitive contra el roster."""
    key = (email or "").strip().casefold()
    if not key:
        return None
    _, by_email, _ = _build_indexes()
    return by_email.get(key)


def format_staff_puesto(role: str) -> str:
    """Ej. «Senior Comunicaciones» → «Senior Comunicaciones Gorila»."""
    r = (role or "").strip()
    if not r:
        return ""
    if "gorila" in r.casefold():
        return r
    return f"{r} Gorila"


def _is_growfik_branded_email(email: str) -> bool:
    """True for @growfik.com or local-part containing growfik (e.g. community1.growfik@gmail.com)."""
    e = (email or "").casefold().strip()
    if not e:
        return False
    if e.endswith("@growfik.com"):
        return True
    local, _, _ = e.partition("@")
    return "growfik" in local


def format_staff_puesto_for_acta(role: str, *, universal: bool, email: str = "") -> str:
    """Universal actas show Growfik brand for growfik-branded staff emails; others use Gorila."""
    r = (role or "").strip()
    if not r:
        return ""
    if universal and _is_growfik_branded_email(email):
        if "growfik" in r.casefold():
            return r
        return f"{r} Growfik"
    return format_staff_puesto(r)


_GENERIC_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "hotmail.com",
        "yahoo.com",
        "outlook.com",
        "live.com",
        "icloud.com",
    }
)


_LOCAL_ROLE_NAMES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^asistenteadministrativo(\d+)?$", re.I), "Asistente administrativo"),
    (re.compile(r"^asistente[\W_]*administrativo(\d+)?$", re.I), "Asistente administrativo"),
    (re.compile(r"^abogado(\d+)?$", re.I), "Abogado"),
)


def _humanize_email_local(local: str) -> str:
    """Convierte local-part en nombre legible (enythelvira → Enythelvira, abogado2 → Abogado 2)."""
    s = (local or "").strip()
    if not s:
        return ""
    for pat, label in _LOCAL_ROLE_NAMES:
        m = pat.match(s)
        if m:
            num = m.group(1) if m.lastindex else None
            return f"{label}{f' {num}' if num else ''}".strip()
    s = re.sub(r"(\d+)", r" \1", s)
    s = s.replace(".", " ").replace("_", " ").replace("-", " ")
    parts = [p for p in s.split() if p]
    return " ".join(p[:1].upper() + p[1:].lower() if p else p for p in parts)


def _puesto_from_email_local(local: str, *, cliente_account: str, domain: str) -> str:
    """Rol inferido del local-part (asistenteadministrativo, abogado2, cuenta corporativa)."""
    lc = (local or "").strip().casefold()
    if not lc:
        return (cliente_account or "").strip() or _company_from_email_domain(domain)
    if re.match(r"^asistenteadministrativo\d*$", lc) or (
        "asistente" in lc and "administrativo" in lc
    ):
        return "Asistente administrativo"
    if re.match(r"^abogado\d*$", lc):
        return "Abogado"
    acct = (cliente_account or "").strip()
    acct_compact = re.sub(r"[^a-z0-9]", "", acct.casefold())
    local_compact = re.sub(r"[^a-z0-9]", "", lc)
    if acct_compact and acct_compact in local_compact:
        if local_compact.endswith("abogados") or local_compact == acct_compact + "abogados":
            return "Cuenta corporativa"
    if acct:
        return acct
    return _company_from_email_domain(domain)


def _company_from_email_domain(domain: str) -> str:
    """barreraestrada.com → Barrera Estrada; universal.edu.co → Universal Edu Co (best effort)."""
    d = (domain or "").strip().casefold()
    if not d or d in _GENERIC_EMAIL_DOMAINS:
        return ""
    base = d.split(".")[0]
    if not base:
        return ""
    # Separar palabras pegadas comunes: barreraestrada → barrera estrada (heurística simple)
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", base)
    if spaced == base and len(base) > 10:
        # intento: insertar espacio antes de sufijos conocidos
        for suffix in ("abogados", "estrada", "universal", "hosting"):
            if suffix in base and base != suffix:
                idx = base.find(suffix)
                if idx > 2:
                    spaced = f"{base[:idx]} {base[idx:]}"
                    break
    return " ".join(w[:1].upper() + w[1:] for w in spaced.replace("-", " ").split() if w)


def invitado_fallback_from_email(
    email: str,
    *,
    cliente_account: str = "",
) -> dict[str, str]:
    """Fallback genérico para cualquier cliente: nombre desde local-part, puesto desde cuenta o dominio."""
    raw = (email or "").strip()
    local, _, domain = raw.partition("@")
    nombre = _humanize_email_local(local) or raw
    if cliente_account:
        acct_compact = re.sub(r"[^a-z0-9]", "", cliente_account.casefold())
        local_compact = re.sub(r"[^a-z0-9]", "", local.casefold())
        if acct_compact and acct_compact in local_compact:
            suffix = local_compact.replace(acct_compact, "", 1)
            if suffix in ("abogados", "administrativo", "admin", "contacto"):
                nombre = f"{cliente_account} {suffix.capitalize()}"
            elif not suffix or local_compact == acct_compact:
                nombre = cliente_account
    puesto = _puesto_from_email_local(
        local, cliente_account=cliente_account, domain=domain
    )
    return {
        "correo": raw,
        "nombre": nombre,
        "puesto": puesto,
        "asistencia": "Confirmado",
    }


def invitado_fields_from_email(
    email: str,
    *,
    cliente_account: str = "",
    universal: bool = False,
) -> dict[str, str]:
    """
    Enriquece fila de invitados: roster Gorila → contacto cliente YAML → fallback legible por email.
    """
    raw = (email or "").strip()
    member = lookup_staff_by_email(raw)
    if member:
        return {
            "correo": raw,
            "nombre": member.canonical_name,
            "puesto": format_staff_puesto_for_acta(member.role, universal=universal, email=raw),
            "asistencia": "Confirmado",
        }
    client_row = invitado_fields_from_client_email(raw)
    if client_row:
        return client_row
    return invitado_fallback_from_email(raw, cliente_account=cliente_account)


def invitado_fields_from_name(
    tag_or_name: str,
    *,
    universal: bool = False,
) -> dict[str, str] | None:
    """Fila de invitado desde nombre/tag (p. ej. persona interna en Próximos pasos sin correo)."""
    raw = _strip_bracket_tag((tag_or_name or "").strip())
    if not raw:
        return None
    member = match_roster_member(raw)
    if not member:
        return None
    email = member.emails[0] if member.emails else ""
    return {
        "correo": email,
        "nombre": member.canonical_name,
        "puesto": format_staff_puesto_for_acta(member.role, universal=universal, email=email),
        "asistencia": "Confirmado",
    }


def canonical_responsable(member: GorilaStaff | None) -> str:
    if member is None:
        return ""
    return member.canonical_name


def responsable_for_tag(tag_or_responsable: str) -> str:
    """Nombre canónico del roster si hay match; si no, el texto original limpio."""
    raw = _strip_bracket_tag((tag_or_responsable or "").strip())
    member = match_roster_member(raw)
    if member:
        return member.canonical_name
    return raw
