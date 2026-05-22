"""
Integración opcional con Google Calendar y Drive (cuenta de servicio).

Sin variables de entorno / credenciales, el pipeline funciona igual que antes.
"""
from __future__ import annotations

import base64
import logging
import os
import re
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

logger = logging.getLogger(__name__)

_MONTHS_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def _fecha_prose(d: date) -> str:
    return f"{d.day} de {_MONTHS_ES[d.month - 1]} de {d.year}"


def _format_hora_ampm(dt: datetime) -> str:
    h12 = dt.hour % 12
    if h12 == 0:
        h12 = 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{h12}:{dt.minute:02d} {ampm}"


def parse_calendar_eid_from_url(url: str) -> tuple[str, str] | None:
    """
    Extrae (calendar_id, event_id) del parámetro ``eid`` en enlaces de Google Calendar.

    El valor suele ser base64url de ``eventId + ' ' + calendarId`` (calendarId = correo del calendario).
    """
    if not url or not re.search(r"calendar\.google\.com|google\.com/calendar", url, re.I):
        return None
    qs = parse_qs(urlparse(url).query)
    eid_list = qs.get("eid")
    if not eid_list:
        return None
    eid = unquote(eid_list[0])
    pad = "=" * (-len(eid) % 4)
    try:
        raw = base64.urlsafe_b64decode(eid + pad)
        decoded = raw.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if " " not in decoded:
        return None
    gap = decoded.rfind(" ")
    event_id = decoded[:gap].strip()
    calendar_id = decoded[gap + 1 :].strip()
    if not event_id or not calendar_id:
        return None
    return calendar_id, event_id


def _resolve_calendar_event_ids(metadata: dict[str, Any]) -> tuple[str, str] | None:
    cal = (os.environ.get("GCAL_CALENDAR_ID") or "").strip()
    ev = (os.environ.get("GCAL_EVENT_ID") or "").strip()
    if cal and ev:
        return cal, ev
    url = (metadata or {}).get("calendar_url") or ""
    if isinstance(url, str) and url.strip():
        parsed = parse_calendar_eid_from_url(url.strip())
        if parsed:
            return parsed
    return None


def _event_to_meta_patch(event: dict[str, Any]) -> dict[str, str]:
    """Campos compatibles con ``metadata`` del parser y el bloque METADATA del LLM."""
    patch: dict[str, str] = {}
    start = event.get("start") or {}
    end = event.get("end") or {}

    if "dateTime" in start:
        sdt = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
        patch["date"] = _fecha_prose(sdt.date())
        patch["hora_inicio"] = _format_hora_ampm(sdt)
    elif "date" in start:
        d = date.fromisoformat(start["date"])
        patch["date"] = _fecha_prose(d)
        patch["hora_inicio"] = "No especificada"

    if "dateTime" in end:
        edt = datetime.fromisoformat(end["dateTime"].replace("Z", "+00:00"))
        patch["hora_fin"] = _format_hora_ampm(edt)
    else:
        patch.setdefault("hora_fin", "No especificada")

    return patch


def _load_sa_credentials(scopes: list[str]):
    path = (os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()
    if not path or not os.path.isfile(path):
        return None
    try:
        from google.oauth2 import service_account

        return service_account.Credentials.from_service_account_file(path, scopes=scopes)
    except Exception as exc:
        logger.warning("No se pudieron cargar credenciales de Google: %s", exc)
        return None


def calendar_enrich_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """
    Si hay credenciales e identificadores de evento, rellena ``date`` / ``hora_inicio`` / ``hora_fin``.
    """
    base: dict[str, Any] = dict(metadata or {})
    ids = _resolve_calendar_event_ids(base)
    if not ids:
        return base

    calendar_id, event_id = ids
    creds = _load_sa_credentials(
        ["https://www.googleapis.com/auth/calendar.readonly"],
    )
    if not creds:
        return base

    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError

        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        event = (
            service.events()
            .get(calendarId=calendar_id, eventId=event_id)
            .execute()
        )
    except ImportError:
        logger.warning(
            "Instala google-api-python-client y google-auth para Calendar (pip install -r requirements.txt)",
        )
        return base
    except HttpError as exc:
        logger.warning("Calendar API error (%s): %s", exc.resp.status, exc)
        return base
    except Exception as exc:
        logger.warning("No se pudo leer el evento del calendario: %s", exc)
        return base

    patch = _event_to_meta_patch(event)
    for k, v in patch.items():
        base[k] = v
    base["calendar_event_id"] = event_id
    base["calendar_id_resolved"] = calendar_id
    return base


_TIME_PLACEHOLDERS = frozenset({"", "No especificada", "No especificado"})


def _is_time_placeholder(value: Any) -> bool:
    return str(value or "").strip() in _TIME_PLACEHOLDERS


def apply_metadata_times_to_acta(
    acta: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """
    Rellena fecha/horas del acta desde metadata del parser o Calendar API.

    - Con ``calendar_event_id``: prioridad total a metadata (Calendar).
    - Sin evento de calendario: solo sustituye horas del acta si el LLM dejó placeholder
      y el parser (p. ej. nombre de archivo ``16_01`` → ``4:01 PM``) detectó un valor.
    """
    out = dict(acta)
    meta = metadata or {}
    force = bool(meta.get("calendar_event_id"))

    d = meta.get("date")
    if force and d and str(d).strip():
        out["fecha"] = str(d).strip()

    for k in ("hora_inicio", "hora_fin"):
        v = meta.get(k)
        if not v or _is_time_placeholder(v):
            continue
        meta_v = str(v).strip()
        if force or _is_time_placeholder(out.get(k)):
            out[k] = meta_v

    if meta.get("is_virtual") and _is_time_placeholder(out.get("lugar")):
        out["lugar"] = "Google Meet"

    hf = out.get("hora_fin")
    if hf and not _is_time_placeholder(hf):
        out["hora_final"] = str(hf).strip()
    return out


def apply_calendar_times_to_acta(
    acta: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Alias retrocompatible: aplica horas desde metadata (parser o Calendar)."""
    return apply_metadata_times_to_acta(acta, metadata)


def drive_upload_pdf_if_configured(pdf_path: str, display_name: str) -> str | None:
    """
    Sube un PDF a ``DRIVE_UPLOAD_FOLDER_ID``. La carpeta debe compartirse con la cuenta de servicio (editor).

    Devuelve ``webViewLink`` o ``webContentLink`` si existe.
    """
    folder = (os.environ.get("DRIVE_UPLOAD_FOLDER_ID") or "").strip()
    if not folder:
        return None

    creds = _load_sa_credentials(
        ["https://www.googleapis.com/auth/drive"],
    )
    if not creds:
        return None

    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        logger.warning(
            "Instala google-api-python-client y google-auth para Drive (pip install -r requirements.txt)",
        )
        return None

    if not os.path.isfile(pdf_path):
        logger.warning("drive_upload_pdf_if_configured: no existe %s", pdf_path)
        return None

    try:
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        body = {"name": display_name, "parents": [folder]}
        media = MediaFileUpload(pdf_path, mimetype="application/pdf", resumable=False)
        created = (
            service.files()
            .create(body=body, media_body=media, fields="id, webViewLink, webContentLink")
            .execute()
        )
        link = created.get("webViewLink") or created.get("webContentLink")
        if link:
            logger.info("PDF subido a Drive: %s", link)
        return link if isinstance(link, str) else None
    except HttpError as exc:
        logger.warning("Drive API error (%s): %s", exc.resp.status, exc)
    except Exception as exc:
        logger.warning("No se pudo subir el PDF a Drive: %s", exc)
    return None
