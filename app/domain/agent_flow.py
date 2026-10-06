"""Общий оркестратор диалога агента (для Telegram и WhatsApp)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.calendar import CalendarPort
from app.db.models import Agent, MeetingFormat, MeetingRequest, Trip
from app.domain.agents import AgentService
from app.domain.availability import DaySchedule, TimedSlot, build_trip_schedule
from app.domain.bookings import BookingService
from app.domain.formatting import format_trip_dates, format_when
from app.domain.trips import TripService
from app.i18n import t

logger = logging.getLogger(__name__)


@dataclass
class AgentDialogState:
    """Состояние FSM агента в памяти процесса (пилот)."""

    trip_token: Optional[str] = None
    trip_id: Optional[int] = None
    step: str = "idle"
    meeting_format: Optional[MeetingFormat] = None
    name: Optional[str] = None
    agency: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    office_address: Optional[str] = None
    pending_request_id: Optional[int] = None
    selected_day: Optional[date] = None
    # Слоты выбранного дня: (start, is_free)
    day_slots: list[TimedSlot] = field(default_factory=list)
    # Страница списка часов для WhatsApp (лимит 10 пунктов)
    time_page: int = 0


# WhatsApp list: макс. 10 rows. На странице — до 8 свободных + More + Back.
_WA_TIMES_PER_PAGE = 8
_WA_TIMES_FIT_WITHOUT_MORE = 9


_STATES: dict[str, AgentDialogState] = {}


def state_key(channel: str, user_id: str | int) -> str:
    return f"{channel}:{user_id}"


def get_state(channel: str, user_id: str | int) -> AgentDialogState:
    key = state_key(channel, user_id)
    if key not in _STATES:
        _STATES[key] = AgentDialogState()
    return _STATES[key]


def clear_state(channel: str, user_id: str | int) -> None:
    _STATES.pop(state_key(channel, user_id), None)


@dataclass
class OutgoingMessage:
    """Сообщение наружу из оркестратора."""

    text: str
    # Плоский список (одна кнопка = ряд), если rows пуст
    buttons: list[tuple[str, str]] = field(default_factory=list)
    # Сетка кнопок: список рядов [(callback, label), ...]
    button_rows: list[list[tuple[str, str]]] = field(default_factory=list)


class AgentFlow:
    """Бизнес-шаги агента без привязки к мессенджеру."""

    def __init__(
        self,
        session: AsyncSession,
        calendar: CalendarPort,
    ) -> None:
        self.session = session
        self.calendar = calendar
        self.trips = TripService(session)
        self.agents = AgentService(session)
        self.bookings = BookingService(session, calendar)

    async def open_trip(
        self,
        *,
        channel: str,
        user_id: str | int,
        token: str,
        existing_agent: Optional[Agent],
    ) -> OutgoingMessage:
        trip = await self.trips.get_by_token(token)
        if trip is None:
            return OutgoingMessage(text=t("en", "trip_not_found"))

        st = get_state(channel, user_id)
        st.trip_token = token
        st.trip_id = trip.id
        st.step = "invite"

        name_part = f" {existing_agent.name}" if existing_agent else ""
        rep = trip.representative
        text = t(
            "en",
            "agent_welcome",
            name_part=name_part,
            rep_name=rep.name,
            provider=rep.provider.name,
            city=trip.city,
            dates=format_trip_dates(trip),
        )
        return OutgoingMessage(
            text=text,
            buttons=[
                ("yes", t("en", "btn_yes")),
                ("no", t("en", "btn_no")),
            ],
        )

    async def handle_invite_answer(
        self,
        *,
        channel: str,
        user_id: str | int,
        answer: str,
        existing_agent: Optional[Agent],
    ) -> OutgoingMessage:
        st = get_state(channel, user_id)
        if answer == "no":
            clear_state(channel, user_id)
            return OutgoingMessage(text=t("en", "agent_declined_invite"))

        trip = await self.trips.get_trip(st.trip_id) if st.trip_id else None
        if trip is None:
            return OutgoingMessage(text=t("en", "trip_not_found"))

        if existing_agent:
            st.step = "after_register"
            msg = OutgoingMessage(
                text=t("en", "known_agent", name=existing_agent.name)
            )
            follow = await self._after_register(trip, st, existing_agent)
            return OutgoingMessage(
                text=msg.text + "\n\n" + follow.text,
                buttons=follow.buttons,
                button_rows=follow.button_rows,
            )

        st.step = "reg_name"
        return OutgoingMessage(text=t("en", "register_ask_name"))

    async def handle_text(
        self,
        *,
        channel: str,
        user_id: str | int,
        text: str,
        telegram_id: Optional[int] = None,
        whatsapp_id: Optional[str] = None,
    ) -> OutgoingMessage:
        st = get_state(channel, user_id)
        trip = await self.trips.get_trip(st.trip_id) if st.trip_id else None
        if trip is None:
            return OutgoingMessage(text=t("en", "trip_not_found"))

        if st.step == "reg_name":
            st.name = text.strip()
            st.step = "reg_agency"
            return OutgoingMessage(text=t("en", "register_ask_agency"))
        if st.step == "reg_agency":
            st.agency = text.strip()
            st.step = "reg_email"
            return OutgoingMessage(text=t("en", "register_ask_email"))
        if st.step == "reg_email":
            st.email = text.strip()
            st.step = "reg_phone"
            return OutgoingMessage(text=t("en", "register_ask_phone"))
        if st.step == "reg_phone":
            st.phone = text.strip()
            agent = await self.agents.register(
                name=st.name or "",
                agency=st.agency or "",
                email=st.email or "",
                phone=st.phone or "",
                telegram_id=telegram_id,
                whatsapp_id=whatsapp_id,
                city=trip.city,
                country=trip.country,
            )
            st.step = "after_register"
            follow = await self._after_register(trip, st, agent)
            return OutgoingMessage(
                text=t("en", "register_done", name=agent.name) + "\n\n" + follow.text,
                buttons=follow.buttons,
                button_rows=follow.button_rows,
            )
        if st.step == "reg_office":
            st.office_address = text.strip()
            agent = await self._resolve_agent(channel, user_id, telegram_id, whatsapp_id)
            if agent:
                await self.agents.update_office(agent, st.office_address)
            return await self._offer_dates(trip, st)

        return OutgoingMessage(text=t("en", "error_generic"))

    async def handle_format(
        self,
        *,
        channel: str,
        user_id: str | int,
        fmt: str,
        telegram_id: Optional[int] = None,
        whatsapp_id: Optional[str] = None,
    ) -> OutgoingMessage:
        st = get_state(channel, user_id)
        trip = await self.trips.get_trip(st.trip_id) if st.trip_id else None
        if trip is None:
            return OutgoingMessage(text=t("en", "trip_not_found"))

        st.meeting_format = (
            MeetingFormat.IN_PERSON if fmt == "in_person" else MeetingFormat.ONLINE
        )

        from app.db.models import LocationMode

        needs_office = (
            st.meeting_format == MeetingFormat.IN_PERSON
            and trip.location_mode == LocationMode.VISIT_OFFICES
        )
        agent = await self._resolve_agent(channel, user_id, telegram_id, whatsapp_id)
        if needs_office and (not agent or not agent.office_address):
            st.step = "reg_office"
            return OutgoingMessage(text=t("en", "register_ask_office"))

        return await self._offer_dates(trip, st)

    async def handle_day_choice(
        self,
        *,
        channel: str,
        user_id: str | int,
        day_iso: str,
    ) -> OutgoingMessage:
        """Выбор даты → показ часов."""
        st = get_state(channel, user_id)
        trip = await self.trips.get_trip(st.trip_id) if st.trip_id else None
        if trip is None:
            return OutgoingMessage(text=t("en", "trip_not_found"))

        try:
            selected = date.fromisoformat(day_iso)
        except ValueError:
            return OutgoingMessage(text=t("en", "error_generic"))

        if selected < trip.start_date or selected > trip.end_date:
            return OutgoingMessage(text=t("en", "error_generic"))

        schedule = await build_trip_schedule(trip, self.calendar)
        day_sched = next((d for d in schedule if d.day == selected), None)
        if day_sched is None:
            return OutgoingMessage(text=t("en", "no_slots"))

        if not day_sched.has_free:
            # Занятый день — не переходим к часам
            return OutgoingMessage(text=t("en", "day_busy_alert"))

        st.selected_day = selected
        st.day_slots = list(day_sched.slots)
        st.time_page = 0
        st.step = "pick_time"
        return self._times_message(trip, day_sched, channel=channel)

    async def handle_more_times(
        self,
        *,
        channel: str,
        user_id: str | int,
    ) -> OutgoingMessage:
        """Следующая страница свободных часов (WhatsApp)."""
        st = get_state(channel, user_id)
        trip = await self.trips.get_trip(st.trip_id) if st.trip_id else None
        if trip is None or st.selected_day is None or not st.day_slots:
            return OutgoingMessage(text=t("en", "error_generic"))
        day_sched = DaySchedule(day=st.selected_day, slots=list(st.day_slots))
        free_count = sum(1 for s in day_sched.slots if s.is_free)
        max_page = max(0, (max(free_count, 1) - 1) // _WA_TIMES_PER_PAGE)
        st.time_page += 1
        if st.time_page > max_page:
            st.time_page = 0
        return self._times_message(
            trip, day_sched, channel=channel, page=st.time_page
        )

    async def handle_time_choice(
        self,
        *,
        channel: str,
        user_id: str | int,
        slot_index: int,
        telegram_id: Optional[int] = None,
        whatsapp_id: Optional[str] = None,
    ) -> tuple[OutgoingMessage, Optional[MeetingRequest]]:
        """Выбор часа из списка дня."""
        st = get_state(channel, user_id)
        trip = await self.trips.get_trip(st.trip_id) if st.trip_id else None
        if trip is None or slot_index < 0 or slot_index >= len(st.day_slots):
            return OutgoingMessage(text=t("en", "error_generic")), None

        timed = st.day_slots[slot_index]
        if not timed.is_free:
            return OutgoingMessage(text=t("en", "slot_busy_alert")), None

        agent = await self._resolve_agent(channel, user_id, telegram_id, whatsapp_id)
        if agent is None:
            return OutgoingMessage(text=t("en", "error_generic")), None

        fmt = st.meeting_format or trip.meeting_format
        if fmt == MeetingFormat.BOTH:
            fmt = MeetingFormat.IN_PERSON

        mr = await self.bookings.create_request(
            trip=trip,
            agent=agent,
            requested_start=timed.start,
            meeting_format=fmt,
            source_channel=channel,
            office_address=st.office_address or agent.office_address,
            online_meeting_link=trip.online_meeting_link,
        )
        st.pending_request_id = mr.id
        st.step = "await_owner"
        msg = OutgoingMessage(
            text=t("en", "request_sent", when=format_when(timed.start, trip.timezone))
        )
        return msg, mr

    async def handle_back_to_dates(
        self,
        *,
        channel: str,
        user_id: str | int,
    ) -> OutgoingMessage:
        st = get_state(channel, user_id)
        trip = await self.trips.get_trip(st.trip_id) if st.trip_id else None
        if trip is None:
            return OutgoingMessage(text=t("en", "trip_not_found"))
        return await self._offer_dates(trip, st)

    # Обратная совместимость имени для suggest/other
    async def _offer_slots(self, trip: Trip, st: AgentDialogState) -> OutgoingMessage:
        return await self._offer_dates(trip, st)

    async def handle_slot_choice(
        self,
        *,
        channel: str,
        user_id: str | int,
        slot_index: int,
        telegram_id: Optional[int] = None,
        whatsapp_id: Optional[str] = None,
    ) -> tuple[OutgoingMessage, Optional[MeetingRequest]]:
        """Алиас: выбор времени по индексу в day_slots."""
        return await self.handle_time_choice(
            channel=channel,
            user_id=user_id,
            slot_index=slot_index,
            telegram_id=telegram_id,
            whatsapp_id=whatsapp_id,
        )

    async def _after_register(
        self,
        trip: Trip,
        st: AgentDialogState,
        agent: Agent,
    ) -> OutgoingMessage:
        if trip.meeting_format == MeetingFormat.BOTH:
            st.step = "pick_format"
            return OutgoingMessage(
                text=t("en", "ask_format"),
                buttons=[
                    ("fmt:in_person", t("en", "btn_in_person")),
                    ("fmt:online", t("en", "btn_online")),
                ],
            )
        st.meeting_format = trip.meeting_format
        from app.db.models import LocationMode

        if (
            trip.meeting_format == MeetingFormat.IN_PERSON
            and trip.location_mode == LocationMode.VISIT_OFFICES
            and not agent.office_address
        ):
            st.step = "reg_office"
            return OutgoingMessage(text=t("en", "register_ask_office"))
        return await self._offer_dates(trip, st)

    async def _offer_dates(self, trip: Trip, st: AgentDialogState) -> OutgoingMessage:
        """Календарь дат поездки (только дни, заданные владельцем)."""
        schedule = await build_trip_schedule(trip, self.calendar)
        if not schedule:
            return OutgoingMessage(text=t("en", "no_slots"))

        st.step = "pick_date"
        st.selected_day = None
        st.day_slots = []
        st.time_page = 0

        rows: list[list[tuple[str, str]]] = []
        row: list[tuple[str, str]] = []
        for day_sched in schedule:
            label = _format_day_button(day_sched, trip.timezone)
            if day_sched.has_free:
                cb = f"day:{day_sched.day.isoformat()}"
            else:
                # Уникальный id: WhatsApp list запрещает дубли row id
                cb = f"busy:day:{day_sched.day.isoformat()}"
            row.append((cb, label))
            if len(row) == 3:
                rows.append(row)
                row = []
        if row:
            rows.append(row)

        if not any(d.has_free for d in schedule):
            return OutgoingMessage(text=t("en", "no_slots"), button_rows=rows)

        return OutgoingMessage(text=t("en", "pick_date"), button_rows=rows)

    def _times_message(
        self,
        trip: Trip,
        day_sched: DaySchedule,
        *,
        channel: str = "telegram",
        page: int = 0,
    ) -> OutgoingMessage:
        """Кнопки часов на выбранный день.

        Telegram: все слоты, занятые с ❌.
        WhatsApp: только свободные, страницами (лимит list = 10).
        """
        tz = ZoneInfo(trip.timezone)
        date_label = day_sched.day.strftime("%d %B %Y")

        if channel == "whatsapp":
            free_indexed = [
                (idx, timed)
                for idx, timed in enumerate(day_sched.slots)
                if timed.is_free
            ]
            rows: list[list[tuple[str, str]]] = []
            if len(free_indexed) <= _WA_TIMES_FIT_WITHOUT_MORE:
                page_items = free_indexed
                show_more = False
            else:
                start = page * _WA_TIMES_PER_PAGE
                if start >= len(free_indexed):
                    start = 0
                    page = 0
                page_items = free_indexed[start : start + _WA_TIMES_PER_PAGE]
                show_more = start + _WA_TIMES_PER_PAGE < len(free_indexed)

            for idx, timed in page_items:
                local = timed.start.astimezone(tz)
                rows.append([(f"time:{idx}", local.strftime("%H:%M"))])

            footer: list[tuple[str, str]] = []
            if show_more:
                footer.append(("times:more", t("en", "btn_more_times")))
            footer.append(("dates:back", t("en", "btn_back_dates")))
            rows.append(footer)
            return OutgoingMessage(
                text=t("en", "pick_time", date=date_label),
                button_rows=rows,
            )

        rows = []
        row: list[tuple[str, str]] = []
        for idx, timed in enumerate(day_sched.slots):
            local = timed.start.astimezone(tz)
            hhmm = local.strftime("%H:%M")
            if timed.is_free:
                cb, label = f"time:{idx}", hhmm
            else:
                # Уникальный id: WhatsApp list запрещает дубли row id
                cb, label = f"busy:time:{idx}", f"❌ {hhmm}"
            row.append((cb, label))
            if len(row) == 4:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([("dates:back", t("en", "btn_back_dates"))])
        return OutgoingMessage(
            text=t("en", "pick_time", date=date_label),
            button_rows=rows,
        )

    async def _resolve_agent(
        self,
        channel: str,
        user_id: str | int,
        telegram_id: Optional[int],
        whatsapp_id: Optional[str],
    ) -> Optional[Agent]:
        if channel == "telegram" and telegram_id is not None:
            return await self.agents.find_by_telegram(telegram_id)
        if channel == "whatsapp" and whatsapp_id is not None:
            return await self.agents.find_by_whatsapp(whatsapp_id)
        return None


def _format_day_button(day_sched: DaySchedule, timezone_name: str) -> str:
    """Подпись кнопки дня: дата или ❌ дата."""
    label = day_sched.day.strftime("%d %b")
    if day_sched.has_free:
        return label
    return f"❌ {label}"
