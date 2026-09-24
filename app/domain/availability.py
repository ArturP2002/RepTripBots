"""Расчёт доступных слотов встреч."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time
from typing import Sequence
from zoneinfo import ZoneInfo

from app.adapters.calendar import BusyPeriod, CalendarPort
from app.db.models import Trip

logger = logging.getLogger(__name__)

DEFAULT_DURATION_MINUTES = 60
SLOT_STEP_MINUTES = 30


@dataclass
class TimedSlot:
    """Один кандидат начала встречи с флагом занятости."""

    start: datetime
    is_free: bool


@dataclass
class DaySchedule:
    """Расписание одного дня поездки."""

    day: date
    slots: list[TimedSlot]

    @property
    def has_free(self) -> bool:
        return any(s.is_free for s in self.slots)

    @property
    def is_past(self) -> bool:
        if not self.slots:
            return True
        return all(not s.is_free and s.start < datetime.now(s.start.tzinfo) for s in self.slots)


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _overlaps(start: datetime, end: datetime, busy: Sequence[BusyPeriod]) -> bool:
    for b in busy:
        if start < b.end and end > b.start:
            return True
    return False


async def build_trip_schedule(
    trip: Trip,
    calendar: CalendarPort,
    *,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
    step_minutes: int = SLOT_STEP_MINUTES,
) -> list[DaySchedule]:
    """
    Полное расписание по дням Trip (только даты владельца).

    Для каждого дня — все шаги 30 мин в часах поездки с is_free.
    """
    tz = ZoneInfo(trip.timezone)
    hours = trip.availability_hours or {}
    day_start = _parse_hhmm(hours.get("start", "10:00"))
    day_end = _parse_hhmm(hours.get("end", "18:00"))

    range_start = datetime.combine(trip.start_date, day_start, tzinfo=tz)
    range_end = datetime.combine(trip.end_date, day_end, tzinfo=tz)
    busy = await calendar.list_busy(range_start, range_end, trip.timezone)
    now = datetime.now(tz)

    days: list[DaySchedule] = []
    current_day: date = trip.start_date
    while current_day <= trip.end_date:
        slots: list[TimedSlot] = []
        cursor = datetime.combine(current_day, day_start, tzinfo=tz)
        day_limit = datetime.combine(current_day, day_end, tzinfo=tz)
        while cursor + timedelta(minutes=duration_minutes) <= day_limit:
            end = cursor + timedelta(minutes=duration_minutes)
            is_free = cursor >= now and not _overlaps(cursor, end, busy)
            slots.append(TimedSlot(start=cursor, is_free=is_free))
            cursor += timedelta(minutes=step_minutes)
        days.append(DaySchedule(day=current_day, slots=slots))
        current_day += timedelta(days=1)

    logger.info(
        "Расписание Trip id=%s: дней=%s, busy-интервалов=%s",
        trip.id,
        len(days),
        len(busy),
    )
    return days


async def list_candidate_slots(
    trip: Trip,
    calendar: CalendarPort,
    *,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
    step_minutes: int = SLOT_STEP_MINUTES,
    limit: int = 40,
) -> list[datetime]:
    """Список только свободных начал встреч (для Suggest и тестов)."""
    schedule = await build_trip_schedule(
        trip,
        calendar,
        duration_minutes=duration_minutes,
        step_minutes=step_minutes,
    )
    free: list[datetime] = []
    for day in schedule:
        for slot in day.slots:
            if slot.is_free:
                free.append(slot.start)
                if len(free) >= limit:
                    return free
    return free


def intervals_overlap(
    start_a: datetime,
    end_a: datetime,
    start_b: datetime,
    end_b: datetime,
) -> bool:
    """Проверка пересечения двух интервалов."""
    return start_a < end_b and end_a > start_b
