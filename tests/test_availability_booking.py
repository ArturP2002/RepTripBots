"""Тесты availability и conflict на Confirm."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.calendar import BusyPeriod, InMemoryCalendar
from app.db.base import Base
from app.db.models import MeetingFormat, MeetingRequestStatus
from app.domain.availability import list_candidate_slots
from app.domain.bookings import BookingService
from app.domain.trips import TripService


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


@pytest.mark.asyncio
async def test_slots_skip_busy(session: AsyncSession):
    calendar = InMemoryCalendar()
    service = TripService(session)
    # подменим timezone_for_country через settings — TripService использует get_settings
    trip = await service.create_trip(
        provider_name="P",
        rep_name="R",
        rep_email="r@e.com",
        city="Almaty",
        country="KZ",
        start_date=date(2030, 6, 1),
        end_date=date(2030, 6, 1),
        hours_start="10:00",
        hours_end="12:00",
        meeting_format=MeetingFormat.ONLINE,
        online_meeting_link="https://meet.example.com/x",
    )
    tz = ZoneInfo(trip.timezone)
    busy_start = datetime(2030, 6, 1, 10, 0, tzinfo=tz)
    calendar.busy.append(
        BusyPeriod(busy_start, busy_start + timedelta(hours=1))
    )
    slots = await list_candidate_slots(trip, calendar)
    assert all(s != busy_start for s in slots)
    assert any(s.hour == 11 for s in slots)


@pytest.mark.asyncio
async def test_confirm_conflict(session: AsyncSession):
    calendar = InMemoryCalendar()
    trips = TripService(session)
    trip = await trips.create_trip(
        provider_name="P",
        rep_name="R",
        rep_email="r@e.com",
        city="Tashkent",
        country="UZ",
        start_date=date(2030, 7, 1),
        end_date=date(2030, 7, 1),
        hours_start="10:00",
        hours_end="14:00",
        meeting_format=MeetingFormat.ONLINE,
        online_meeting_link="https://meet.example.com/x",
    )
    from app.domain.agents import AgentService

    agents = AgentService(session)
    a1 = await agents.register(
        name="A1", agency="Ag1", email="a1@e.com", phone="+1", telegram_id=1
    )
    a2 = await agents.register(
        name="A2", agency="Ag2", email="a2@e.com", phone="+2", telegram_id=2
    )
    bookings = BookingService(session, calendar)
    tz = ZoneInfo(trip.timezone)
    start = datetime(2030, 7, 1, 10, 0, tzinfo=tz)
    mr1 = await bookings.create_request(
        trip=trip,
        agent=a1,
        requested_start=start,
        meeting_format=MeetingFormat.ONLINE,
        source_channel="telegram",
    )
    mr2 = await bookings.create_request(
        trip=trip,
        agent=a2,
        requested_start=start,
        meeting_format=MeetingFormat.ONLINE,
        source_channel="telegram",
    )
    r1 = await bookings.confirm(mr1.id)
    assert r1.ok
    r2 = await bookings.confirm(mr2.id)
    assert not r2.ok
    assert r2.reason in {"conflict_booking", "calendar_busy"}
    mr2_reload = await bookings.get_request(mr2.id)
    assert mr2_reload is not None
    assert mr2_reload.status == MeetingRequestStatus.PENDING
