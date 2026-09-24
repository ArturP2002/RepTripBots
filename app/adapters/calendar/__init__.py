"""Интерфейс и реализация Google Calendar для RepTrip."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Sequence

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class BusyPeriod:
    """Занятый интервал в календаре."""

    start: datetime
    end: datetime


@dataclass
class CalendarEventPayload:
    """Данные для создания события встречи."""

    title: str
    start: datetime
    end: datetime
    description: str
    location: Optional[str] = None
    timezone_name: str = "UTC"
    # Цвет события Google Calendar (строка "1"…"11"), см. event colors API
    color_id: Optional[str] = None
    # Целый день (метка даты); не блокирует free/busy
    all_day: bool = False
    transparency: str = "opaque"  # opaque | transparent


class CalendarPort(ABC):
    """Порт календаря (реализация — Google)."""

    @abstractmethod
    async def list_busy(
        self,
        time_min: datetime,
        time_max: datetime,
        timezone_name: str,
    ) -> Sequence[BusyPeriod]:
        """Возвращает занятые интервалы."""

    @abstractmethod
    async def is_free(
        self,
        start: datetime,
        end: datetime,
        timezone_name: str,
    ) -> bool:
        """Проверяет, свободен ли интервал."""

    @abstractmethod
    async def create_event(self, payload: CalendarEventPayload) -> str:
        """Создаёт событие, возвращает event_id."""

    @abstractmethod
    async def delete_event(self, event_id: str) -> None:
        """Удаляет событие по id."""


class InMemoryCalendar(CalendarPort):
    """
    Простая in-memory реализация для unit-тестов.
    Не заменяет Google в проде — только тесты.
    """

    def __init__(self) -> None:
        self.busy: list[BusyPeriod] = []
        self.events: dict[str, CalendarEventPayload] = {}
        self._counter = 0

    async def list_busy(
        self,
        time_min: datetime,
        time_max: datetime,
        timezone_name: str,
    ) -> Sequence[BusyPeriod]:
        return [
            b
            for b in self.busy
            if b.start < time_max and b.end > time_min
        ]

    async def is_free(
        self,
        start: datetime,
        end: datetime,
        timezone_name: str,
    ) -> bool:
        for b in self.busy:
            if start < b.end and end > b.start:
                return False
        return True

    async def create_event(self, payload: CalendarEventPayload) -> str:
        self._counter += 1
        event_id = f"mem-{self._counter}"
        self.events[event_id] = payload
        self.busy.append(BusyPeriod(payload.start, payload.end))
        return event_id

    async def delete_event(self, event_id: str) -> None:
        payload = self.events.pop(event_id, None)
        if payload:
            self.busy = [
                b
                for b in self.busy
                if not (b.start == payload.start and b.end == payload.end)
            ]


class GoogleCalendarAdapter(CalendarPort):
    """Адаптер Google Calendar API (OAuth desktop + refresh token)."""

    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._service = None

    def _build_service(self):
        """Создаёт google calendar service (синхронный клиент)."""
        if self._service is not None:
            return self._service

        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        token_path = Path(self.settings.google_token_file)
        creds_path = Path(self.settings.google_credentials_file)

        if token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(token_path), self.SCOPES
            )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Обновляю Google OAuth token…")
                creds.refresh(Request())
            else:
                if not creds_path.exists():
                    raise FileNotFoundError(
                        f"Не найден файл credentials: {creds_path}. "
                        "Сначала выполните scripts/google_oauth_setup.py"
                    )
                logger.info("Запускаю OAuth-поток Google Calendar…")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(creds_path), self.SCOPES
                )
                creds = flow.run_local_server(port=0)
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json(), encoding="utf-8")
            logger.info("Google token сохранён в %s", token_path)

        self._service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        logger.info(
            "Google Calendar подключен (calendar_id=%s)",
            self.settings.google_calendar_id,
        )
        return self._service

    def _ensure_aware(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    async def list_busy(
        self,
        time_min: datetime,
        time_max: datetime,
        timezone_name: str,
    ) -> Sequence[BusyPeriod]:
        import asyncio

        service = self._build_service()
        time_min = self._ensure_aware(time_min)
        time_max = self._ensure_aware(time_max)

        def _call():
            body = {
                "timeMin": time_min.isoformat(),
                "timeMax": time_max.isoformat(),
                "timeZone": timezone_name,
                "items": [{"id": self.settings.google_calendar_id}],
            }
            return (
                service.freebusy()
                .query(body=body)
                .execute()
            )

        result = await asyncio.to_thread(_call)
        cal = result.get("calendars", {}).get(self.settings.google_calendar_id, {})
        periods: list[BusyPeriod] = []
        for item in cal.get("busy", []):
            periods.append(
                BusyPeriod(
                    start=datetime.fromisoformat(item["start"].replace("Z", "+00:00")),
                    end=datetime.fromisoformat(item["end"].replace("Z", "+00:00")),
                )
            )
        logger.debug(
            "Google free/busy: найдено %s занятых интервалов",
            len(periods),
        )
        return periods

    async def is_free(
        self,
        start: datetime,
        end: datetime,
        timezone_name: str,
    ) -> bool:
        busy = await self.list_busy(start, end, timezone_name)
        start = self._ensure_aware(start)
        end = self._ensure_aware(end)
        for b in busy:
            if start < b.end and end > b.start:
                return False
        return True

    async def create_event(self, payload: CalendarEventPayload) -> str:
        import asyncio

        service = self._build_service()

        def _call():
            if payload.all_day:
                # Google: end.date — следующий день (exclusive)
                start_day = payload.start.date().isoformat()
                end_day = payload.end.date().isoformat()
                body = {
                    "summary": payload.title,
                    "description": payload.description,
                    "start": {"date": start_day},
                    "end": {"date": end_day},
                    "transparency": payload.transparency,
                }
            else:
                body = {
                    "summary": payload.title,
                    "description": payload.description,
                    "start": {
                        "dateTime": payload.start.isoformat(),
                        "timeZone": payload.timezone_name,
                    },
                    "end": {
                        "dateTime": payload.end.isoformat(),
                        "timeZone": payload.timezone_name,
                    },
                    "transparency": payload.transparency,
                }
            if payload.location:
                body["location"] = payload.location
            if payload.color_id:
                body["colorId"] = str(payload.color_id)
            return (
                service.events()
                .insert(calendarId=self.settings.google_calendar_id, body=body)
                .execute()
            )

        created = await asyncio.to_thread(_call)
        event_id = created["id"]
        logger.info("Создано событие Google Calendar id=%s", event_id)
        return event_id

    async def delete_event(self, event_id: str) -> None:
        import asyncio

        service = self._build_service()

        def _call():
            service.events().delete(
                calendarId=self.settings.google_calendar_id,
                eventId=event_id,
            ).execute()

        await asyncio.to_thread(_call)
        logger.info("Удалено событие Google Calendar id=%s", event_id)


def build_calendar(settings: Settings | None = None) -> CalendarPort:
    """Фабрика календаря: Google. Для тестов подменяйте вручную."""
    return GoogleCalendarAdapter(settings or get_settings())
