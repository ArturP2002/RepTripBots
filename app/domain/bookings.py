"""MeetingRequest и Booking: Confirm / Decline / Suggest / Cancel."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.calendar import CalendarEventPayload, CalendarPort
from app.config import get_settings
from app.db.models import (
    Agent,
    Booking,
    BookingStatus,
    MeetingFormat,
    MeetingRequest,
    MeetingRequestStatus,
    Representative,
    Trip,
)
from app.domain.availability import DEFAULT_DURATION_MINUTES, intervals_overlap

logger = logging.getLogger(__name__)


@dataclass
class ConfirmResult:
    """Результат подтверждения заявки владельцем."""

    ok: bool
    booking: Optional[Booking] = None
    reason: str = ""


class BookingService:
    """Заявки и бронирования."""

    def __init__(self, session: AsyncSession, calendar: CalendarPort) -> None:
        self.session = session
        self.calendar = calendar

    async def create_request(
        self,
        *,
        trip: Trip,
        agent: Agent,
        requested_start: datetime,
        meeting_format: MeetingFormat,
        source_channel: str,
        office_address: Optional[str] = None,
        online_meeting_link: Optional[str] = None,
    ) -> MeetingRequest:
        """Создаёт pending MeetingRequest (слот ещё не блокируется)."""
        mr = MeetingRequest(
            trip_id=trip.id,
            agent_id=agent.id,
            requested_start=requested_start,
            meeting_format=meeting_format,
            office_address=office_address or agent.office_address,
            online_meeting_link=online_meeting_link or trip.online_meeting_link,
            status=MeetingRequestStatus.PENDING,
            source_channel=source_channel,
        )
        self.session.add(mr)
        await self.session.commit()
        await self.session.refresh(mr)
        logger.info(
            "Создана заявка MeetingRequest id=%s trip=%s agent=%s start=%s",
            mr.id,
            trip.id,
            agent.id,
            requested_start.isoformat(),
        )
        return await self.get_request(mr.id)  # type: ignore[return-value]

    async def get_request(self, request_id: int) -> Optional[MeetingRequest]:
        result = await self.session.execute(
            select(MeetingRequest)
            .where(MeetingRequest.id == request_id)
            .options(
                selectinload(MeetingRequest.agent),
                selectinload(MeetingRequest.trip)
                .selectinload(Trip.representative)
                .selectinload(Representative.provider),
                selectinload(MeetingRequest.booking),
            )
        )
        return result.scalar_one_or_none()

    async def list_active_bookings_for_trip(self, trip_id: int) -> list[Booking]:
        result = await self.session.execute(
            select(Booking)
            .join(MeetingRequest)
            .where(
                MeetingRequest.trip_id == trip_id,
                Booking.status == BookingStatus.ACTIVE,
            )
            .options(selectinload(Booking.meeting_request))
        )
        return list(result.scalars().all())

    def _location_lines(self, mr: MeetingRequest, trip: Trip) -> tuple[str, Optional[str]]:
        """Возвращает (строка для описания, location для календаря)."""
        if mr.meeting_format == MeetingFormat.ONLINE:
            link = mr.online_meeting_link or trip.online_meeting_link or ""
            return f"Online: {link}", None
        # in person
        from app.db.models import LocationMode

        if trip.location_mode == LocationMode.AGENTS_COME:
            loc = trip.common_location or ""
            return loc, loc
        loc = mr.office_address or mr.agent.office_address or ""
        return loc, loc

    async def confirm(self, request_id: int) -> ConfirmResult:
        """
        Владелец подтверждает запись агента.

        Повторно проверяет Google Calendar и активные Booking на пересечение.
        """
        mr = await self.get_request(request_id)
        if mr is None:
            return ConfirmResult(ok=False, reason="not_found")
        if mr.status != MeetingRequestStatus.PENDING:
            return ConfirmResult(ok=False, reason="not_pending")

        trip = mr.trip
        start = mr.requested_start
        end = start + timedelta(minutes=DEFAULT_DURATION_MINUTES)

        # Конфликт с уже подтверждёнными Booking
        active = await self.list_active_bookings_for_trip(trip.id)
        for booking in active:
            b_end = booking.confirmed_start + timedelta(
                minutes=booking.duration_minutes
            )
            if intervals_overlap(start, end, booking.confirmed_start, b_end):
                logger.warning(
                    "Конфликт с Booking id=%s при Confirm заявки id=%s",
                    booking.id,
                    mr.id,
                )
                return ConfirmResult(ok=False, reason="conflict_booking")

        free = await self.calendar.is_free(start, end, trip.timezone)
        if not free:
            logger.warning(
                "Слот занят в Google Calendar при Confirm заявки id=%s", mr.id
            )
            return ConfirmResult(ok=False, reason="calendar_busy")

        agent = mr.agent
        rep = trip.representative
        provider_name = rep.provider.name
        location_text, location_field = self._location_lines(mr, trip)

        description_parts = [
            f"Agent: {agent.name}",
            f"Agency: {agent.agency}",
            f"Email: {agent.email}",
            f"Phone: {agent.phone}",
            f"Format: {mr.meeting_format.value}",
        ]
        if agent.website:
            description_parts.append(f"Website: {agent.website}")
        if mr.meeting_format == MeetingFormat.ONLINE:
            description_parts.append(location_text)
        elif location_text:
            description_parts.append(f"Location: {location_text}")

        event_id = await self.calendar.create_event(
            CalendarEventPayload(
                title=f"{agent.agency} · {agent.name}",
                start=start,
                end=end,
                description="\n".join(description_parts),
                location=location_field,
                timezone_name=trip.timezone,
                color_id=get_settings().google_event_color_id or None,
            )
        )

        mr.status = MeetingRequestStatus.CONFIRMED
        booking = Booking(
            meeting_request_id=mr.id,
            confirmed_start=start,
            duration_minutes=DEFAULT_DURATION_MINUTES,
            calendar_event_id=event_id,
            status=BookingStatus.ACTIVE,
        )
        self.session.add(booking)
        await self.session.flush()
        await self._ensure_day_highlight(trip, start)
        await self.session.commit()
        await self.session.refresh(booking)
        logger.info(
            "Подтверждена заявка id=%s → Booking id=%s event=%s",
            mr.id,
            booking.id,
            event_id,
        )
        return ConfirmResult(ok=True, booking=booking)

    async def _ensure_day_highlight(self, trip: Trip, start: datetime) -> None:
        """
        Создаёт цветную метку на весь день в Google Calendar.

        Google не умеет красить фон ячейки дня — используем all-day событие
        с transparency=transparent (не занимает слоты).
        """
        from zoneinfo import ZoneInfo

        settings = get_settings()
        local_day = start.astimezone(ZoneInfo(trip.timezone)).date()
        day_key = local_day.isoformat()
        highlights = dict(trip.day_highlights or {})
        if day_key in highlights:
            return

        day_start = datetime.combine(local_day, datetime.min.time())
        day_end = datetime.combine(local_day + timedelta(days=1), datetime.min.time())
        marker_id = await self.calendar.create_event(
            CalendarEventPayload(
                title=f"RepTrip · {trip.city} · meeting day",
                start=day_start,
                end=day_end,
                description=(
                    f"Day with confirmed RepTrip meetings "
                    f"(trip #{trip.id}, {trip.city}).\n"
                    "This marker does not block available time."
                ),
                timezone_name=trip.timezone,
                color_id=settings.google_day_highlight_color_id or "5",
                all_day=True,
                transparency="transparent",
            )
        )
        highlights[day_key] = marker_id
        trip.day_highlights = highlights
        logger.info(
            "Создана метка дня %s в календаре (event=%s) для Trip id=%s",
            day_key,
            marker_id,
            trip.id,
        )

    async def _maybe_clear_day_highlight(self, trip: Trip, start: datetime) -> None:
        """Удаляет метку дня, если на этот день больше нет активных Booking."""
        from zoneinfo import ZoneInfo

        local_day = start.astimezone(ZoneInfo(trip.timezone)).date()
        day_key = local_day.isoformat()
        highlights = dict(trip.day_highlights or {})
        event_id = highlights.get(day_key)
        if not event_id:
            return

        active = await self.list_active_bookings_for_trip(trip.id)
        still_has = False
        for booking in active:
            b_day = booking.confirmed_start.astimezone(
                ZoneInfo(trip.timezone)
            ).date()
            if b_day == local_day:
                still_has = True
                break
        if still_has:
            return

        try:
            await self.calendar.delete_event(event_id)
        except Exception:
            logger.exception("Не удалось удалить метку дня %s (%s)", day_key, event_id)
        highlights.pop(day_key, None)
        trip.day_highlights = highlights
        logger.info("Удалена метка дня %s для Trip id=%s", day_key, trip.id)

    async def decline(self, request_id: int) -> Optional[MeetingRequest]:
        mr = await self.get_request(request_id)
        if mr is None or mr.status != MeetingRequestStatus.PENDING:
            return None
        mr.status = MeetingRequestStatus.DECLINED
        await self.session.commit()
        logger.info("Заявка id=%s отклонена", mr.id)
        return mr

    async def reschedule_request(
        self,
        request_id: int,
        new_start: datetime,
    ) -> Optional[MeetingRequest]:
        """Владелец предлагает другое время — обновляет requested_start, статус pending."""
        mr = await self.get_request(request_id)
        if mr is None:
            return None
        mr.requested_start = new_start
        mr.status = MeetingRequestStatus.PENDING
        await self.session.commit()
        logger.info(
            "Для заявки id=%s предложено новое время %s",
            mr.id,
            new_start.isoformat(),
        )
        return await self.get_request(request_id)

    async def cancel_by_agent(self, request_id: int) -> Optional[Booking]:
        """Агент отменяет подтверждённую встречу."""
        mr = await self.get_request(request_id)
        if mr is None or mr.booking is None:
            return None
        booking = mr.booking
        if booking.status != BookingStatus.ACTIVE:
            return None
        if booking.calendar_event_id:
            try:
                await self.calendar.delete_event(booking.calendar_event_id)
            except Exception:
                logger.exception(
                    "Не удалось удалить событие календаря %s",
                    booking.calendar_event_id,
                )
        booking.status = BookingStatus.CANCELLED
        await self._maybe_clear_day_highlight(mr.trip, booking.confirmed_start)
        await self.session.commit()
        logger.info("Booking id=%s отменён агентом", booking.id)
        return booking

    async def find_active_booking_for_agent(
        self,
        agent_id: int,
        trip_id: int,
    ) -> Optional[MeetingRequest]:
        result = await self.session.execute(
            select(MeetingRequest)
            .where(
                MeetingRequest.agent_id == agent_id,
                MeetingRequest.trip_id == trip_id,
                MeetingRequest.status == MeetingRequestStatus.CONFIRMED,
            )
            .options(
                selectinload(MeetingRequest.booking),
                selectinload(MeetingRequest.agent),
                selectinload(MeetingRequest.trip)
                .selectinload(Trip.representative)
                .selectinload(Representative.provider),
            )
        )
        for mr in result.scalars().all():
            if mr.booking and mr.booking.status == BookingStatus.ACTIVE:
                return mr
        return None
