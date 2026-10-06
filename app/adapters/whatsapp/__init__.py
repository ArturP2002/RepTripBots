"""WhatsApp Cloud API клиент и обработка webhook."""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import Settings, get_settings
from app.db.base import get_session_factory
from app.domain.agent_flow import AgentFlow
from app.domain.agents import AgentService
from app.i18n import t
from app.runtime import get_calendar, get_notify_owners

logger = logging.getLogger(__name__)


class WhatsAppClient:
    """Исходящие сообщения WhatsApp Cloud API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def _url(self) -> str:
        return (
            f"https://graph.facebook.com/{self.settings.whatsapp_api_version}/"
            f"{self.settings.whatsapp_phone_number_id}/messages"
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.whatsapp_token}",
            "Content-Type": "application/json",
        }

    async def send_text(self, to: str, body: str) -> None:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        await self._post(payload)

    async def send_buttons(
        self, to: str, body: str, buttons: list[tuple[str, str]]
    ) -> None:
        """
        Interactive reply buttons (макс. 3) или список.
        buttons: (id, title) — title ≤ 20 символов.
        """
        if not buttons:
            await self.send_text(to, body)
            return

        if len(buttons) <= 3:
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": body},
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {
                                    "id": bid[:256],
                                    "title": title[:20],
                                },
                            }
                            for bid, title in buttons[:3]
                        ]
                    },
                },
            }
        else:
            # List message — секции
            rows = [
                {
                    "id": bid[:200],
                    "title": title[:24],
                }
                for bid, title in buttons[:10]
            ]
            payload = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {"text": body},
                    "action": {
                        "button": "Choose",
                        "sections": [{"title": "Options", "rows": rows}],
                    },
                },
            }
        await self._post(payload)

    async def _post(self, payload: dict[str, Any]) -> None:
        if not self.settings.whatsapp_token or not self.settings.whatsapp_phone_number_id:
            logger.warning(
                "WhatsApp credentials не заданы — исходящее сообщение пропущено"
            )
            return
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self._url, headers=self._headers(), json=payload
            )
            if resp.status_code >= 400:
                logger.error(
                    "Ошибка WhatsApp API %s: %s",
                    resp.status_code,
                    resp.text,
                )
            else:
                logger.info("WhatsApp сообщение отправлено to=%s", payload.get("to"))


async def handle_whatsapp_webhook_payload(
    data: dict[str, Any],
    client: WhatsAppClient,
) -> None:
    """Разбирает inbound webhook и прогоняет AgentFlow."""
    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
    except (KeyError, IndexError):
        logger.debug("WhatsApp webhook без полезной нагрузки")
        return

    messages = value.get("messages") or []
    if not messages:
        return

    msg = messages[0]
    wa_from = msg.get("from")
    if not wa_from:
        return

    text: Optional[str] = None
    button_id: Optional[str] = None

    if msg.get("type") == "text":
        text = (msg.get("text") or {}).get("body", "").strip()
    elif msg.get("type") == "interactive":
        interactive = msg.get("interactive") or {}
        if interactive.get("type") == "button_reply":
            button_id = interactive.get("button_reply", {}).get("id")
        elif interactive.get("type") == "list_reply":
            button_id = interactive.get("list_reply", {}).get("id")

    logger.info(
        "Входящее WhatsApp от %s text=%r button=%r",
        wa_from,
        text,
        button_id,
    )

    factory = get_session_factory()
    async with factory() as session:
        agents = AgentService(session)
        existing = await agents.find_by_whatsapp(wa_from)
        flow = AgentFlow(session, get_calendar())

        # Старт по JOIN <token>
        if text and text.upper().startswith("JOIN "):
            token = text.split(None, 1)[1].strip()
            out = await flow.open_trip(
                channel="whatsapp",
                user_id=wa_from,
                token=token,
                existing_agent=existing,
            )
            await _wa_send_out(client, wa_from, out)
            return

        if button_id in {"yes", "no"}:
            out = await flow.handle_invite_answer(
                channel="whatsapp",
                user_id=wa_from,
                answer=button_id,
                existing_agent=existing,
            )
            await _wa_send_out(client, wa_from, out)
            return

        if button_id and button_id.startswith("fmt:"):
            out = await flow.handle_format(
                channel="whatsapp",
                user_id=wa_from,
                fmt=button_id.split(":")[-1],
                whatsapp_id=wa_from,
            )
            await _wa_send_out(client, wa_from, out)
            return

        if button_id and button_id.startswith("day:"):
            day_iso = button_id.split(":", 1)[1]
            out = await flow.handle_day_choice(
                channel="whatsapp",
                user_id=wa_from,
                day_iso=day_iso,
            )
            await _wa_send_out(client, wa_from, out)
            return

        if button_id and button_id.startswith("time:"):
            idx = int(button_id.split(":")[-1])
            out, mr = await flow.handle_time_choice(
                channel="whatsapp",
                user_id=wa_from,
                slot_index=idx,
                whatsapp_id=wa_from,
            )
            await client.send_text(wa_from, out.text)
            if mr:
                notify = get_notify_owners()
                if notify:
                    await notify(mr)
            return

        if button_id and button_id.startswith("busy:"):
            await client.send_text(
                wa_from,
                t("en", "day_busy_alert")
                if button_id.startswith("busy:day")
                else t("en", "slot_busy_alert"),
            )
            return

        if button_id == "times:more":
            out = await flow.handle_more_times(
                channel="whatsapp",
                user_id=wa_from,
            )
            await _wa_send_out(client, wa_from, out)
            return

        if button_id == "dates:back":
            out = await flow.handle_back_to_dates(
                channel="whatsapp",
                user_id=wa_from,
            )
            await _wa_send_out(client, wa_from, out)
            return

        if button_id and button_id.startswith("slot:"):
            idx = int(button_id.split(":")[-1])
            out, mr = await flow.handle_slot_choice(
                channel="whatsapp",
                user_id=wa_from,
                slot_index=idx,
                whatsapp_id=wa_from,
            )
            await client.send_text(wa_from, out.text)
            if mr:
                notify = get_notify_owners()
                if notify:
                    await notify(mr)
            return

        if button_id and button_id.startswith("sug:"):
            from app.domain.bookings import BookingService
            from app.domain.formatting import (
                format_line_for_request,
                format_when,
                location_line_for_request,
            )

            parts = button_id.split(":")
            action, request_id = parts[1], int(parts[2])
            svc = BookingService(session, get_calendar())
            if action == "yes":
                result = await svc.confirm(request_id)
                mr = await svc.get_request(request_id)
                if result.ok and mr:
                    trip = mr.trip
                    rep = trip.representative
                    await client.send_text(
                        wa_from,
                        t(
                            "en",
                            "confirmed",
                            rep_name=rep.name,
                            provider=rep.provider.name,
                            when=format_when(mr.requested_start, trip.timezone),
                            format_line=format_line_for_request(mr),
                            location_line=location_line_for_request(mr),
                        ),
                    )
                else:
                    await client.send_text(wa_from, t("en", "no_slots"))
            else:
                mr = await svc.get_request(request_id)
                if mr:
                    from app.domain.agent_flow import get_state

                    st = get_state("whatsapp", wa_from)
                    st.trip_id = mr.trip_id
                    st.meeting_format = mr.meeting_format
                    out = await flow._offer_slots(mr.trip, st)
                    await _wa_send_out(client, wa_from, out)
            return

        if button_id and button_id.startswith("cancel:"):
            from app.domain.bookings import BookingService
            from app.domain.formatting import format_when
            from app.runtime import get_bot

            request_id = int(button_id.split(":")[-1])
            svc = BookingService(session, get_calendar())
            booking = await svc.cancel_by_agent(request_id)
            mr = await svc.get_request(request_id)
            await client.send_text(wa_from, t("en", "cancelled"))
            bot = get_bot()
            settings = get_settings()
            if bot and booking and mr:
                for owner_id in settings.owner_telegram_ids:
                    await bot.send_message(
                        owner_id,
                        t(
                            "ru",
                            "cancel_notify_owner",
                            agent_name=mr.agent.name,
                            agency=mr.agent.agency,
                            when=format_when(mr.requested_start, mr.trip.timezone),
                        ),
                    )
            return

        if text:
            out = await flow.handle_text(
                channel="whatsapp",
                user_id=wa_from,
                text=text,
                whatsapp_id=wa_from,
            )
            await _wa_send_out(client, wa_from, out)


async def _wa_send_out(client: WhatsAppClient, to: str, out) -> None:
    """Отправляет OutgoingMessage: сетку сплющивает в список кнопок WA."""
    flat: list[tuple[str, str]] = list(out.buttons)
    if out.button_rows:
        for row in out.button_rows:
            flat.extend(row)
    # WhatsApp list — макс ~10; занятые тоже показываем с ❌ в title
    await client.send_buttons(to, out.text, flat[:10])


async def notify_agent_whatsapp(client: WhatsAppClient, mr, kind: str) -> None:
    """Уведомление агента в WhatsApp."""
    from app.domain.formatting import (
        format_line_for_request,
        format_when,
        location_line_for_request,
    )

    wa_id = mr.agent.whatsapp_id
    if not wa_id:
        return
    trip = mr.trip
    rep = trip.representative
    if kind == "confirmed":
        await client.send_buttons(
            wa_id,
            t(
                "en",
                "confirmed",
                rep_name=rep.name,
                provider=rep.provider.name,
                when=format_when(mr.requested_start, trip.timezone),
                format_line=format_line_for_request(mr),
                location_line=location_line_for_request(mr),
            ),
            [("cancel:" + str(mr.id), t("en", "btn_cancel_meeting")[:20])],
        )
    elif kind == "declined":
        await client.send_text(wa_id, t("en", "declined"))
    elif kind == "suggest":
        await client.send_buttons(
            wa_id,
            t(
                "en",
                "suggest_received",
                rep_name=rep.name,
                when=format_when(mr.requested_start, trip.timezone),
            ),
            [
                (f"sug:yes:{mr.id}", t("en", "btn_suggest_yes")),
                (f"sug:other:{mr.id}", "Other time"),
            ],
        )
