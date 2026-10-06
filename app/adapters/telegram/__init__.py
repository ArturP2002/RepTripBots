"""Telegram-адаптер RepTrip (aiogram 3)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.config import Settings, get_settings
from app.db.base import get_session_factory
from app.db.models import LocationMode, MeetingFormat
from app.domain.agent_flow import AgentFlow
from app.domain.agents import AgentService
from app.domain.availability import list_candidate_slots
from app.domain.bookings import BookingService
from app.domain.formatting import (
    format_line_for_request,
    format_when,
    location_line_for_request,
)
from app.domain.trips import TripService
from app.i18n import t
from app.runtime import get_calendar, get_notify_agent

logger = logging.getLogger(__name__)


class OwnerTripFSM(StatesGroup):
    """FSM создания Trip владельцем (EN)."""

    provider = State()
    rep_name = State()
    rep_email = State()
    city = State()
    country = State()
    start_date = State()
    end_date = State()
    hours = State()
    meeting_format = State()
    location_mode = State()
    common_location = State()
    online_link = State()


def _owner_kb_country() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("en", "btn_kz"), callback_data="own:country:KZ"
                ),
                InlineKeyboardButton(
                    text=t("en", "btn_uz"), callback_data="own:country:UZ"
                ),
            ]
        ]
    )


def _owner_kb_format() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("en", "btn_in_person"), callback_data="own:fmt:in_person"
                ),
                InlineKeyboardButton(
                    text=t("en", "btn_online"), callback_data="own:fmt:online"
                ),
                InlineKeyboardButton(
                    text=t("en", "btn_both"), callback_data="own:fmt:both"
                ),
            ]
        ]
    )


def _owner_kb_location() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("en", "btn_visit_offices"),
                    callback_data="own:loc:visit_offices",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("en", "btn_agents_come"),
                    callback_data="own:loc:agents_come",
                )
            ],
        ]
    )


def _request_kb(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("en", "btn_confirm"),
                    callback_data=f"own:confirm:{request_id}",
                ),
                InlineKeyboardButton(
                    text=t("en", "btn_suggest"),
                    callback_data=f"own:suggest:{request_id}",
                ),
                InlineKeyboardButton(
                    text=t("en", "btn_decline"),
                    callback_data=f"own:decline:{request_id}",
                ),
            ]
        ]
    )


def _parse_date(text: str):
    text = text.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def build_telegram_dispatcher(settings: Settings | None = None) -> Dispatcher:
    """Собирает Dispatcher с роутерами владельца и агента."""
    settings = settings or get_settings()
    dp = Dispatcher()
    owner_router = Router(name="owner")
    agent_router = Router(name="agent")

    def is_owner(user_id: int) -> bool:
        return settings.is_owner(user_id)

    # ----- Owner -----
    @owner_router.message(Command("start"))
    async def owner_or_fallback_start(
        message: Message, command: CommandObject, state: FSMContext
    ) -> None:
        # Если есть deep-link token — это агентский вход (даже для владельца)
        args = (command.args or "").strip()
        if args:
            await agent_start(message, command, state)
            return
        if not message.from_user or not is_owner(message.from_user.id):
            await message.answer(t("en", "non_owner_hint"))
            return
        await message.answer(t("en", "owner_welcome"))

    @owner_router.message(Command("help"))
    async def owner_help(message: Message) -> None:
        if not message.from_user or not is_owner(message.from_user.id):
            await message.answer(t("en", "owner_only"))
            return
        await message.answer(t("en", "help_owner"))

    @owner_router.message(Command("new_trip"))
    async def new_trip(message: Message, state: FSMContext) -> None:
        if not message.from_user or not is_owner(message.from_user.id):
            await message.answer(t("en", "owner_only"))
            return
        await state.clear()
        await state.set_state(OwnerTripFSM.provider)
        await message.answer(t("en", "trip_create_start"))

    @owner_router.message(OwnerTripFSM.provider)
    async def trip_provider(message: Message, state: FSMContext) -> None:
        await state.update_data(provider=message.text)
        await state.set_state(OwnerTripFSM.rep_name)
        await message.answer(t("en", "trip_ask_rep_name"))

    @owner_router.message(OwnerTripFSM.rep_name)
    async def trip_rep_name(message: Message, state: FSMContext) -> None:
        await state.update_data(rep_name=message.text)
        await state.set_state(OwnerTripFSM.rep_email)
        await message.answer(t("en", "trip_ask_rep_email"))

    @owner_router.message(OwnerTripFSM.rep_email)
    async def trip_rep_email(message: Message, state: FSMContext) -> None:
        await state.update_data(rep_email=message.text)
        await state.set_state(OwnerTripFSM.city)
        await message.answer(t("en", "trip_ask_city"))

    @owner_router.message(OwnerTripFSM.city)
    async def trip_city(message: Message, state: FSMContext) -> None:
        await state.update_data(city=message.text)
        await state.set_state(OwnerTripFSM.country)
        await message.answer(t("en", "trip_ask_country"), reply_markup=_owner_kb_country())

    @owner_router.callback_query(OwnerTripFSM.country, F.data.startswith("own:country:"))
    async def trip_country_cb(query: CallbackQuery, state: FSMContext) -> None:
        country = query.data.split(":")[-1]  # type: ignore[union-attr]
        await state.update_data(country=country)
        await state.set_state(OwnerTripFSM.start_date)
        await query.message.answer(t("en", "trip_ask_start_date"))  # type: ignore[union-attr]
        await query.answer()

    @owner_router.message(OwnerTripFSM.country)
    async def trip_country_text(message: Message, state: FSMContext) -> None:
        await state.update_data(country=message.text)
        await state.set_state(OwnerTripFSM.start_date)
        await message.answer(t("en", "trip_ask_start_date"))

    @owner_router.message(OwnerTripFSM.start_date)
    async def trip_start(message: Message, state: FSMContext) -> None:
        d = _parse_date(message.text or "")
        if not d:
            await message.answer(t("en", "trip_invalid_date"))
            return
        await state.update_data(start_date=d.isoformat())
        await state.set_state(OwnerTripFSM.end_date)
        await message.answer(t("en", "trip_ask_end_date"))

    @owner_router.message(OwnerTripFSM.end_date)
    async def trip_end(message: Message, state: FSMContext) -> None:
        d = _parse_date(message.text or "")
        if not d:
            await message.answer(t("en", "trip_invalid_date"))
            return
        await state.update_data(end_date=d.isoformat())
        await state.set_state(OwnerTripFSM.hours)
        await message.answer(t("en", "trip_ask_hours"))

    @owner_router.message(OwnerTripFSM.hours)
    async def trip_hours(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip().replace(" ", "")
        if "-" not in raw:
            await message.answer(t("en", "trip_invalid_hours"))
            return
        start_h, end_h = raw.split("-", 1)
        await state.update_data(hours_start=start_h, hours_end=end_h)
        await state.set_state(OwnerTripFSM.meeting_format)
        await message.answer(t("en", "trip_ask_format"), reply_markup=_owner_kb_format())

    @owner_router.callback_query(OwnerTripFSM.meeting_format, F.data.startswith("own:fmt:"))
    async def trip_fmt(query: CallbackQuery, state: FSMContext) -> None:
        fmt = query.data.split(":")[-1]  # type: ignore[union-attr]
        await state.update_data(meeting_format=fmt)
        if fmt in {"in_person", "both"}:
            await state.set_state(OwnerTripFSM.location_mode)
            await query.message.answer(  # type: ignore[union-attr]
                t("en", "trip_ask_location_mode"), reply_markup=_owner_kb_location()
            )
        elif fmt == "online":
            await state.set_state(OwnerTripFSM.online_link)
            await query.message.answer(t("en", "trip_ask_online_link"))  # type: ignore[union-attr]
        await query.answer()

    @owner_router.callback_query(OwnerTripFSM.location_mode, F.data.startswith("own:loc:"))
    async def trip_loc(query: CallbackQuery, state: FSMContext) -> None:
        mode = query.data.split(":")[-1]  # type: ignore[union-attr]
        await state.update_data(location_mode=mode)
        data = await state.get_data()
        fmt = data.get("meeting_format")
        if mode == "agents_come":
            await state.set_state(OwnerTripFSM.common_location)
            await query.message.answer(t("en", "trip_ask_common_location"))  # type: ignore[union-attr]
        elif fmt == "both":
            # In person + Online: нужна online-ссылка
            await state.set_state(OwnerTripFSM.online_link)
            await query.message.answer(t("en", "trip_ask_online_link"))  # type: ignore[union-attr]
        else:
            # in_person + visit_offices — без online link
            await _finalize_trip(query.message, state)  # type: ignore[arg-type]
        await query.answer()

    @owner_router.message(OwnerTripFSM.common_location)
    async def trip_common_loc(message: Message, state: FSMContext) -> None:
        await state.update_data(common_location=message.text)
        data = await state.get_data()
        if data.get("meeting_format") in {"both", "online"}:
            await state.set_state(OwnerTripFSM.online_link)
            await message.answer(t("en", "trip_ask_online_link"))
        else:
            await _finalize_trip(message, state)

    @owner_router.message(OwnerTripFSM.online_link)
    async def trip_online(message: Message, state: FSMContext) -> None:
        await state.update_data(online_link=message.text)
        await _finalize_trip(message, state)

    async def _finalize_trip(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        await state.clear()
        fmt_map = {
            "in_person": MeetingFormat.IN_PERSON,
            "online": MeetingFormat.ONLINE,
            "both": MeetingFormat.BOTH,
        }
        loc_map = {
            "visit_offices": LocationMode.VISIT_OFFICES,
            "agents_come": LocationMode.AGENTS_COME,
        }
        factory = get_session_factory()
        async with factory() as session:
            service = TripService(session, settings)
            trip = await service.create_trip(
                provider_name=data["provider"],
                rep_name=data["rep_name"],
                rep_email=data["rep_email"],
                city=data["city"],
                country=data["country"],
                start_date=datetime.fromisoformat(data["start_date"]).date(),
                end_date=datetime.fromisoformat(data["end_date"]).date(),
                hours_start=data["hours_start"],
                hours_end=data["hours_end"],
                meeting_format=fmt_map[data["meeting_format"]],
                location_mode=loc_map.get(data.get("location_mode") or ""),
                common_location=data.get("common_location"),
                online_meeting_link=data.get("online_link"),
            )
            links = service.build_links(trip)
            format_label = {
                MeetingFormat.IN_PERSON: t("en", "format_in_person"),
                MeetingFormat.ONLINE: t("en", "format_online"),
                MeetingFormat.BOTH: t("en", "format_both"),
            }.get(trip.meeting_format, trip.meeting_format.value)
            country_label = {"KZ": "Kazakhstan", "UZ": "Uzbekistan"}.get(
                trip.country, trip.country
            )
            text = t(
                "en",
                "trip_created",
                trip_id=trip.id,
                provider=trip.representative.provider.name,
                rep_name=trip.representative.name,
                city=trip.city,
                country=country_label,
                start_date=trip.start_date.isoformat(),
                end_date=trip.end_date.isoformat(),
                timezone=trip.timezone,
                meeting_format=format_label,
                go_link=links["go_link"],
            )
            await message.answer(text)
            logger.info("Владелец создал Trip id=%s через Telegram", trip.id)

    @owner_router.message(Command("trips"))
    async def list_trips(message: Message) -> None:
        if not message.from_user or not is_owner(message.from_user.id):
            await message.answer(t("en", "owner_only"))
            return
        factory = get_session_factory()
        async with factory() as session:
            trips = await TripService(session, settings).list_active()
        if not trips:
            await message.answer(t("en", "trips_empty"))
            return
        lines = [
            t(
                "en",
                "trips_list_item",
                id=tr.id,
                city=tr.city,
                country=tr.country,
                start=tr.start_date.isoformat(),
                end=tr.end_date.isoformat(),
                token=tr.share_token,
            )
            for tr in trips
        ]
        await message.answer("\n".join(lines))

    @owner_router.callback_query(F.data.startswith("own:confirm:"))
    async def owner_confirm(query: CallbackQuery) -> None:
        if not query.from_user or not is_owner(query.from_user.id):
            await query.answer(t("en", "owner_only"), show_alert=True)
            return
        request_id = int(query.data.split(":")[-1])  # type: ignore[union-attr]
        factory = get_session_factory()
        async with factory() as session:
            svc = BookingService(session, get_calendar())
            result = await svc.confirm(request_id)
            mr = await svc.get_request(request_id)
        if result.ok and mr:
            await query.message.answer(t("en", "confirm_ok"))  # type: ignore[union-attr]
            notify = get_notify_agent()
            if notify:
                await notify(mr, "confirmed")
        else:
            await query.message.answer(t("en", "confirm_busy"))  # type: ignore[union-attr]
        await query.answer()

    @owner_router.callback_query(F.data.startswith("own:decline:"))
    async def owner_decline(query: CallbackQuery) -> None:
        if not query.from_user or not is_owner(query.from_user.id):
            await query.answer(t("en", "owner_only"), show_alert=True)
            return
        request_id = int(query.data.split(":")[-1])  # type: ignore[union-attr]
        factory = get_session_factory()
        async with factory() as session:
            svc = BookingService(session, get_calendar())
            mr = await svc.decline(request_id)
        await query.message.answer(t("en", "decline_ok"))  # type: ignore[union-attr]
        if mr:
            notify = get_notify_agent()
            if notify:
                await notify(mr, "declined")
        await query.answer()

    @owner_router.callback_query(F.data.startswith("own:suggest:"))
    async def owner_suggest(query: CallbackQuery) -> None:
        if not query.from_user or not is_owner(query.from_user.id):
            await query.answer(t("en", "owner_only"), show_alert=True)
            return
        request_id = int(query.data.split(":")[-1])  # type: ignore[union-attr]
        factory = get_session_factory()
        async with factory() as session:
            svc = BookingService(session, get_calendar())
            mr = await svc.get_request(request_id)
            if mr is None:
                await query.answer("Not found", show_alert=True)
                return
            slots = await list_candidate_slots(mr.trip, get_calendar())
            if not slots:
                await query.message.answer(t("en", "suggest_no_slots"))  # type: ignore[union-attr]
                await query.answer()
                return
            rows = []
            for idx, slot in enumerate(slots[:15]):
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=format_when(slot, mr.trip.timezone),
                            callback_data=f"own:suggestslot:{request_id}:{idx}",
                        )
                    ]
                )
            # сохраняем слоты в runtime через message — упростим: пересчитаем в callback
            await query.message.answer(  # type: ignore[union-attr]
                t("en", "suggest_ask_slot"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
        await query.answer()

    @owner_router.callback_query(F.data.startswith("own:suggestslot:"))
    async def owner_suggest_slot(query: CallbackQuery) -> None:
        if not query.from_user or not is_owner(query.from_user.id):
            await query.answer(t("en", "owner_only"), show_alert=True)
            return
        parts = query.data.split(":")  # type: ignore[union-attr]
        request_id = int(parts[2])
        slot_idx = int(parts[3])
        factory = get_session_factory()
        async with factory() as session:
            svc = BookingService(session, get_calendar())
            mr = await svc.get_request(request_id)
            if mr is None:
                await query.answer("Not found", show_alert=True)
                return
            slots = await list_candidate_slots(mr.trip, get_calendar())
            if slot_idx >= len(slots):
                await query.answer("Bad slot", show_alert=True)
                return
            mr = await svc.reschedule_request(request_id, slots[slot_idx])
        await query.message.answer(t("en", "suggest_sent"))  # type: ignore[union-attr]
        if mr:
            notify = get_notify_agent()
            if notify:
                await notify(mr, "suggest")
        await query.answer()

    # ----- Agent -----
    async def agent_start(
        message: Message, command: CommandObject, state: FSMContext
    ) -> None:
        token = (command.args or "").strip()
        if not token or not message.from_user:
            await message.answer(t("en", "trip_not_found"))
            return
        await state.clear()
        factory = get_session_factory()
        async with factory() as session:
            agents = AgentService(session)
            existing = await agents.find_by_telegram(message.from_user.id)
            flow = AgentFlow(session, get_calendar())
            out = await flow.open_trip(
                channel="telegram",
                user_id=message.from_user.id,
                token=token,
                existing_agent=existing,
            )
        await message.answer(
            out.text,
            reply_markup=_agent_buttons_from_out(out),
        )

    @agent_router.message(CommandStart(deep_link=True))
    async def agent_deep_start(
        message: Message, command: CommandObject, state: FSMContext
    ) -> None:
        await agent_start(message, command, state)

    @agent_router.callback_query(F.data.in_({"yes", "no"}))
    async def agent_yes_no(query: CallbackQuery) -> None:
        if not query.from_user:
            return
        factory = get_session_factory()
        async with factory() as session:
            existing = await AgentService(session).find_by_telegram(query.from_user.id)
            flow = AgentFlow(session, get_calendar())
            out = await flow.handle_invite_answer(
                channel="telegram",
                user_id=query.from_user.id,
                answer=query.data or "no",
                existing_agent=existing,
            )
        await query.message.answer(  # type: ignore[union-attr]
            out.text, reply_markup=_agent_buttons_from_out(out)
        )
        await query.answer()

    @agent_router.callback_query(F.data.startswith("fmt:"))
    async def agent_fmt(query: CallbackQuery) -> None:
        if not query.from_user:
            return
        fmt = (query.data or "").split(":")[-1]
        factory = get_session_factory()
        async with factory() as session:
            flow = AgentFlow(session, get_calendar())
            out = await flow.handle_format(
                channel="telegram",
                user_id=query.from_user.id,
                fmt=fmt,
                telegram_id=query.from_user.id,
            )
        await query.message.answer(  # type: ignore[union-attr]
            out.text, reply_markup=_agent_buttons_from_out(out)
        )
        await query.answer()

    @agent_router.callback_query(F.data.startswith("day:"))
    async def agent_day(query: CallbackQuery) -> None:
        if not query.from_user or not query.data:
            return
        day_iso = query.data.split(":", 1)[1]
        factory = get_session_factory()
        async with factory() as session:
            flow = AgentFlow(session, get_calendar())
            out = await flow.handle_day_choice(
                channel="telegram",
                user_id=query.from_user.id,
                day_iso=day_iso,
            )
        await query.message.answer(  # type: ignore[union-attr]
            out.text, reply_markup=_agent_buttons_from_out(out)
        )
        await query.answer()

    @agent_router.callback_query(F.data.startswith("time:"))
    async def agent_time(query: CallbackQuery) -> None:
        if not query.from_user or not query.data:
            return
        idx = int(query.data.split(":")[-1])
        factory = get_session_factory()
        async with factory() as session:
            flow = AgentFlow(session, get_calendar())
            out, mr = await flow.handle_time_choice(
                channel="telegram",
                user_id=query.from_user.id,
                slot_index=idx,
                telegram_id=query.from_user.id,
            )
            if mr:
                from app.runtime import get_notify_owners

                notify_owners = get_notify_owners()
                if notify_owners:
                    await notify_owners(mr)
        await query.message.answer(out.text)  # type: ignore[union-attr]
        await query.answer()

    @agent_router.callback_query(F.data.startswith("busy:"))
    async def agent_busy(query: CallbackQuery) -> None:
        """Занятый день/час — крестик, без перехода."""
        data = query.data or ""
        alert = (
            t("en", "day_busy_alert")
            if data.startswith("busy:day")
            else t("en", "slot_busy_alert")
        )
        await query.answer(alert, show_alert=True)

    @agent_router.callback_query(F.data == "dates:back")
    async def agent_back_dates(query: CallbackQuery) -> None:
        if not query.from_user:
            return
        factory = get_session_factory()
        async with factory() as session:
            flow = AgentFlow(session, get_calendar())
            out = await flow.handle_back_to_dates(
                channel="telegram",
                user_id=query.from_user.id,
            )
        await query.message.answer(  # type: ignore[union-attr]
            out.text, reply_markup=_agent_buttons_from_out(out)
        )
        await query.answer()

    @agent_router.callback_query(F.data.startswith("slot:"))
    async def agent_slot(query: CallbackQuery) -> None:
        """Старый callback slot: — на случай старых сообщений."""
        if not query.from_user:
            return
        idx = int((query.data or "").split(":")[-1])
        factory = get_session_factory()
        async with factory() as session:
            flow = AgentFlow(session, get_calendar())
            out, mr = await flow.handle_slot_choice(
                channel="telegram",
                user_id=query.from_user.id,
                slot_index=idx,
                telegram_id=query.from_user.id,
            )
            if mr:
                from app.runtime import get_notify_owners

                notify_owners = get_notify_owners()
                if notify_owners:
                    await notify_owners(mr)
        await query.message.answer(out.text)  # type: ignore[union-attr]
        await query.answer()

    @agent_router.callback_query(F.data.startswith("sug:"))
    async def agent_suggest_answer(query: CallbackQuery) -> None:
        """Ответ агента на предложение другого времени: sug:yes:ID / sug:other:ID."""
        if not query.from_user or not query.data:
            return
        parts = query.data.split(":")
        action, request_id = parts[1], int(parts[2])
        factory = get_session_factory()
        async with factory() as session:
            svc = BookingService(session, get_calendar())
            if action == "yes":
                result = await svc.confirm(request_id)
                mr = await svc.get_request(request_id)
                if result.ok and mr:
                    await query.message.answer(  # type: ignore[union-attr]
                        _confirmed_text(mr)
                    )
                else:
                    await query.message.answer(t("en", "no_slots"))  # type: ignore[union-attr]
            else:
                mr = await svc.get_request(request_id)
                if mr:
                    flow = AgentFlow(session, get_calendar())
                    from app.domain.agent_flow import get_state

                    st = get_state("telegram", query.from_user.id)
                    st.trip_id = mr.trip_id
                    st.meeting_format = mr.meeting_format
                    out = await flow._offer_slots(mr.trip, st)
                    await query.message.answer(  # type: ignore[union-attr]
                        out.text, reply_markup=_agent_buttons_from_out(out)
                    )
        await query.answer()

    @agent_router.callback_query(F.data.startswith("cancel:"))
    async def agent_cancel(query: CallbackQuery) -> None:
        if not query.from_user or not query.data:
            return
        request_id = int(query.data.split(":")[-1])
        factory = get_session_factory()
        async with factory() as session:
            svc = BookingService(session, get_calendar())
            booking = await svc.cancel_by_agent(request_id)
            mr = await svc.get_request(request_id)
        if booking and mr:
            await query.message.answer(t("en", "cancelled"))  # type: ignore[union-attr]
            # уведомить владельцев
            bot = query.bot
            for owner_id in settings.owner_telegram_ids:
                await bot.send_message(
                    owner_id,
                    t(
                        "en",
                        "cancel_notify_owner",
                        agent_name=mr.agent.name,
                        agency=mr.agent.agency,
                        when=format_when(mr.requested_start, mr.trip.timezone),
                    ),
                )
        await query.answer()

    @agent_router.message(F.text)
    async def agent_text(message: Message) -> None:
        if not message.from_user or not message.text:
            return
        # Владелец в FSM Trip обрабатывается выше; здесь — регистрация агента
        if is_owner(message.from_user.id):
            return
        factory = get_session_factory()
        async with factory() as session:
            flow = AgentFlow(session, get_calendar())
            out = await flow.handle_text(
                channel="telegram",
                user_id=message.from_user.id,
                text=message.text,
                telegram_id=message.from_user.id,
            )
        await message.answer(out.text, reply_markup=_agent_buttons_from_out(out))

    dp.include_router(owner_router)
    dp.include_router(agent_router)
    return dp


def _agent_buttons_from_out(out) -> Optional[InlineKeyboardMarkup]:
    """Собирает клавиатуру из OutgoingMessage (сетка или плоский список)."""
    if out.button_rows:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=label, callback_data=cb) for cb, label in row]
                for row in out.button_rows
            ]
        )
    return _agent_buttons(out.buttons)


def _agent_buttons(buttons: list[tuple[str, str]]) -> Optional[InlineKeyboardMarkup]:
    if not buttons:
        return None
    # Yes/No и формат — в один ряд по 2, иначе столбец
    if len(buttons) <= 3:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=label, callback_data=cb) for cb, label in buttons]
            ]
        )
    rows = [
        [InlineKeyboardButton(text=label, callback_data=cb)] for cb, label in buttons
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirmed_text(mr) -> str:
    trip = mr.trip
    rep = trip.representative
    return t(
        "en",
        "confirmed",
        rep_name=rep.name,
        provider=rep.provider.name,
        when=format_when(mr.requested_start, trip.timezone),
        format_line=format_line_for_request(mr),
        location_line=location_line_for_request(mr),
    )


async def notify_owners_about_request(bot: Bot, settings: Settings, mr) -> None:
    """Sends an English meeting request card to the owners."""
    text = t(
        "en",
        "new_meeting_request",
        agent_name=mr.agent.name,
        agency=mr.agent.agency,
        when=format_when(mr.requested_start, mr.trip.timezone, with_tz_label=True),
        meeting_format=format_line_for_request(mr, lang="en"),
        location_line=location_line_for_request(mr, lang="en"),
        city=mr.trip.city,
        trip_id=mr.trip_id,
    )
    for owner_id in settings.owner_telegram_ids:
        try:
            await bot.send_message(
                owner_id, text, reply_markup=_request_kb(mr.id)
            )
            logger.info(
                "Владельцу %s отправлена заявка MeetingRequest id=%s",
                owner_id,
                mr.id,
            )
        except Exception:
            logger.exception("Не удалось уведомить владельца %s", owner_id)


async def notify_agent_telegram(bot: Bot, mr, kind: str) -> None:
    """Ответ агенту в Telegram после решения владельца."""
    agent = mr.agent
    if not agent.telegram_id:
        return
    if kind == "confirmed":
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t("en", "btn_cancel_meeting"),
                        callback_data=f"cancel:{mr.id}",
                    )
                ]
            ]
        )
        await bot.send_message(agent.telegram_id, _confirmed_text(mr), reply_markup=kb)
    elif kind == "declined":
        await bot.send_message(agent.telegram_id, t("en", "declined"))
    elif kind == "suggest":
        trip = mr.trip
        text = t(
            "en",
            "suggest_received",
            rep_name=trip.representative.name,
            when=format_when(mr.requested_start, trip.timezone),
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t("en", "btn_suggest_yes"),
                        callback_data=f"sug:yes:{mr.id}",
                    ),
                    InlineKeyboardButton(
                        text=t("en", "btn_choose_another"),
                        callback_data=f"sug:other:{mr.id}",
                    ),
                ]
            ]
        )
        await bot.send_message(agent.telegram_id, text, reply_markup=kb)
