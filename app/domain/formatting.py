"""Утилиты форматирования дат/карточек для сообщений бота."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.db.models import MeetingFormat, MeetingRequest, Trip


def format_trip_dates(trip: Trip) -> str:
    """Человекочитаемые даты поездки."""
    if trip.start_date == trip.end_date:
        return trip.start_date.strftime("%d %B %Y")
    return (
        f"{trip.start_date.strftime('%d %B')} – "
        f"{trip.end_date.strftime('%d %B %Y')}"
    )


def format_when(dt: datetime, tz_name: str, *, with_tz_label: bool = False) -> str:
    """Форматирует момент времени в TZ поездки."""
    local = dt.astimezone(ZoneInfo(tz_name))
    text = local.strftime("%d %B %Y · %H:%M")
    if with_tz_label:
        # Понятная подпись, чтобы не путать с временем в МСК в Google Calendar
        city_hint = {
            "Asia/Almaty": "Almaty",
            "Asia/Tashkent": "Tashkent",
            "Europe/Moscow": "Moscow",
        }.get(tz_name, tz_name)
        text = f"{text} ({city_hint})"
    return text


def format_line_for_request(mr: MeetingRequest, *, lang: str = "en") -> str:
    """English meeting format label for request cards."""
    return {
        MeetingFormat.IN_PERSON: "In person",
        MeetingFormat.ONLINE: "Online",
        MeetingFormat.BOTH: "Both",
    }.get(mr.meeting_format, mr.meeting_format.value)


def location_line_for_request(mr: MeetingRequest, *, lang: str = "en") -> str:
    """Локация/ссылка для карточки заявки."""
    trip = mr.trip
    if mr.meeting_format == MeetingFormat.ONLINE:
        link = mr.online_meeting_link or trip.online_meeting_link or "—"
        prefix = "Online"
        return f"{prefix} · {link}"
    from app.db.models import LocationMode

    if trip.location_mode == LocationMode.AGENTS_COME:
        return trip.common_location or "—"
    return mr.office_address or (mr.agent.office_address if mr.agent else None) or "—"
