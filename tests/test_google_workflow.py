"""Tests sin red para el flujo opcional de Google Calendar."""

from __future__ import annotations

import base64
from urllib.parse import urlencode

from src.google_workflow import parse_calendar_eid_from_url


def _calendar_url_with_eid(event_id: str, calendar_id: str) -> str:
    inner = f"{event_id} {calendar_id}"
    eid = base64.urlsafe_b64encode(inner.encode("utf-8")).decode("ascii").rstrip("=")
    q = urlencode({"eid": eid})
    return f"https://calendar.google.com/calendar/u/0/r/eventedit?{q}"


def test_parse_calendar_eid_roundtrip() -> None:
    url = _calendar_url_with_eid("evt_abc", "room@resource.calendar.google.com")
    assert parse_calendar_eid_from_url(url) == ("room@resource.calendar.google.com", "evt_abc")


def test_parse_calendar_eid_calendar_id_with_space_in_local_part() -> None:
    """rfind(" ") separa el último token como calendar_id (puede incluir espacios raros)."""
    url = _calendar_url_with_eid("single", "c@example.com")
    assert parse_calendar_eid_from_url(url) == ("c@example.com", "single")


def test_parse_calendar_rejects_non_calendar_host() -> None:
    assert parse_calendar_eid_from_url("https://example.com/?eid=abcd") is None


def test_parse_calendar_no_eid() -> None:
    assert parse_calendar_eid_from_url("https://calendar.google.com/calendar/embed?src=x") is None
