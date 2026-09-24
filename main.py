"""
Точка входа RepTrip: Telegram + WhatsApp + HTTP API.

Запуск: python main.py
"""

from __future__ import annotations

import asyncio
import logging

import uvicorn
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.adapters.calendar import GoogleCalendarAdapter
from app.adapters.telegram import (
    build_telegram_dispatcher,
    notify_agent_telegram,
    notify_owners_about_request,
)
from app.adapters.whatsapp import (
    WhatsAppClient,
    handle_whatsapp_webhook_payload,
    notify_agent_whatsapp,
)
from app.api import create_api_app
from app.config import get_settings
from app.db.base import init_db
from app.logging_setup import setup_logging
from app.runtime import set_bot, set_calendar, set_notify_agent, set_notify_owners

logger = logging.getLogger(__name__)


async def _run() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    if not settings.telegram_enabled and not settings.whatsapp_enabled:
        logger.error(
            "Оба канала отключены (TELEGRAM_ENABLED и WHATSAPP_ENABLED = false). "
            "Укажите хотя бы один канал в .env"
        )
        raise SystemExit(1)

    logger.info("Инициализация базы данных…")
    await init_db()
    logger.info("База данных готова")

    calendar = GoogleCalendarAdapter(settings)
    set_calendar(calendar)
    # Пробуем подключить Google только если есть credentials/token —
    # иначе предупреждение (слоты без busy всё равно посчитаются при ошибке вызова).
    try:
        from pathlib import Path

        if Path(settings.google_token_file).exists() or Path(
            settings.google_credentials_file
        ).exists():
            calendar._build_service()
            logger.info("Google Calendar готов к работе")
        else:
            logger.warning(
                "Файлы Google OAuth не найдены (%s / %s). "
                "Выполните scripts/google_oauth_setup.py перед Confirm.",
                settings.google_credentials_file,
                settings.google_token_file,
            )
    except Exception:
        logger.exception("Не удалось инициализировать Google Calendar при старте")

    wa_client = WhatsAppClient(settings)
    bot: Bot | None = None
    tasks: list[asyncio.Task] = []

    async def notify_owners(mr) -> None:
        if bot is None:
            logger.warning("Bot не запущен — уведомление владельцу пропущено")
            return
        await notify_owners_about_request(bot, settings, mr)

    async def notify_agent(mr, kind: str) -> None:
        channel = mr.source_channel
        if channel == "telegram" and bot is not None:
            await notify_agent_telegram(bot, mr, kind)
        elif channel == "whatsapp":
            await notify_agent_whatsapp(wa_client, mr, kind)
        else:
            # fallback: пробуем оба идентификатора
            if bot and mr.agent.telegram_id:
                await notify_agent_telegram(bot, mr, kind)
            if mr.agent.whatsapp_id:
                await notify_agent_whatsapp(wa_client, mr, kind)

    set_notify_owners(notify_owners)
    set_notify_agent(notify_agent)

    need_api = settings.whatsapp_enabled or True  # /go всегда полезен

    async def wa_handler(payload: dict) -> None:
        await handle_whatsapp_webhook_payload(payload, wa_client)

    api_app = create_api_app(whatsapp_handler=wa_handler if settings.whatsapp_enabled else None)

    if settings.telegram_enabled:
        if not settings.telegram_bot_token:
            logger.error("TELEGRAM_ENABLED=true, но TELEGRAM_BOT_TOKEN пуст")
            raise SystemExit(1)
        bot = Bot(
            token=settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        set_bot(bot)
        dp = build_telegram_dispatcher(settings)
        logger.info("Канал Telegram включён — запускаю polling")
        tasks.append(asyncio.create_task(dp.start_polling(bot), name="telegram"))
    else:
        logger.info("Канал Telegram отключён (TELEGRAM_ENABLED=false)")

    if settings.whatsapp_enabled:
        logger.info(
            "Канал WhatsApp включён — webhook на %s/webhooks/whatsapp",
            settings.public_base_url.rstrip("/"),
        )
    else:
        logger.info("Канал WhatsApp отключён (WHATSAPP_ENABLED=false)")

    if need_api:
        config = uvicorn.Config(
            api_app,
            host=settings.api_host,
            port=settings.api_port,
            log_level=settings.log_level.lower(),
        )
        server = uvicorn.Server(config)
        logger.info(
            "HTTP API слушает %s:%s (health, /go, whatsapp webhook)",
            settings.api_host,
            settings.api_port,
        )
        tasks.append(asyncio.create_task(server.serve(), name="api"))

    logger.info("RepTrip запущен")
    try:
        await asyncio.gather(*tasks)
    finally:
        if bot is not None:
            await bot.session.close()
        logger.info("RepTrip остановлен")


def main() -> None:
    """Синхронная обёртка запуска."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
