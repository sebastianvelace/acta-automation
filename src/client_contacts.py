"""Contactos cliente conocidos por email (data/client_contacts.yaml)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONTACTS_PATH = _REPO_ROOT / "data" / "client_contacts.yaml"


@dataclass(frozen=True)
class ClientContact:
    email: str
    name: str
    role: str


def _load_raw_contacts() -> list[dict[str, Any]]:
    if not _CONTACTS_PATH.is_file():
        return []
    data = yaml.safe_load(_CONTACTS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return []
    contacts = data.get("contacts")
    if not isinstance(contacts, list):
        return []
    return [c for c in contacts if isinstance(c, dict)]


@lru_cache(maxsize=1)
def load_client_contacts() -> tuple[ClientContact, ...]:
    out: list[ClientContact] = []
    for row in _load_raw_contacts():
        email = str(row.get("email") or "").strip()
        name = str(row.get("name") or "").strip()
        role = str(row.get("role") or "").strip()
        if email and name:
            out.append(ClientContact(email=email, name=name, role=role))
    return tuple(out)


@lru_cache(maxsize=1)
def _contacts_by_email() -> dict[str, ClientContact]:
    return {c.email.casefold(): c for c in load_client_contacts()}


def lookup_client_contact(email: str) -> ClientContact | None:
    key = (email or "").strip().casefold()
    if not key:
        return None
    return _contacts_by_email().get(key)


def _fold_person_name(name: str) -> str:
    nfd = unicodedata.normalize("NFD", (name or "").casefold())
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def fold_person_name(name: str) -> str:
    """Case- and accent-insensitive key for matching people."""
    return _fold_person_name(name)


def lookup_client_contact_by_name(name: str) -> ClientContact | None:
    """Match contacto YAML por nombre (ignora tildes y mayúsculas)."""
    target = _fold_person_name(name)
    if not target:
        return None
    for contact in load_client_contacts():
        if _fold_person_name(contact.name) == target:
            return contact
    return None


def is_known_client_person(name: str) -> bool:
    """True si el nombre coincide con un contacto cliente (completo o primer nombre)."""
    cleaned = re.sub(r"(?<=\w)\.(?=\s+\w)", "", (name or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if lookup_client_contact_by_name(cleaned):
        return True
    token = _fold_person_name(cleaned.split()[0].rstrip("."))
    if not token:
        return False
    for contact in load_client_contacts():
        parts = _fold_person_name(contact.name).split()
        if parts and parts[0] == token:
            return True
    return False


def invitado_fields_from_client_email(email: str) -> dict[str, str] | None:
    contact = lookup_client_contact(email)
    if not contact:
        return None
    return {
        "correo": email.strip(),
        "nombre": contact.name,
        "puesto": contact.role,
        "asistencia": "Confirmado",
    }
