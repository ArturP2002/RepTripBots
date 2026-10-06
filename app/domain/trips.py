"""Сервисы Trip / Provider / Representative и deep-links."""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings, get_settings
from app.db.models import (
    LocationMode,
    MeetingFormat,
    Provider,
    Representative,
    Trip,
    TripStatus,
)

logger = logging.getLogger(__name__)


def build_whatsapp_chat_url(settings: Settings, share_token: str) -> str:
    """Ссылка wa.me на чат с ботом и предзаполненным JOIN {token}."""
    text = quote(f"JOIN {share_token}")
    phone = "".join(ch for ch in settings.whatsapp_display_phone if ch.isdigit())
    if not phone:
        logger.warning(
            "WHATSAPP_DISPLAY_PHONE не задан — ссылка WhatsApp без номера бота"
        )
        return f"https://wa.me/?text={text}"
    return f"https://wa.me/{phone}?text={text}"


class TripService:
    """Создание и чтение поездок."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def create_trip(
        self,
        *,
        provider_name: str,
        rep_name: str,
        rep_email: str,
        city: str,
        country: str,
        start_date: date,
        end_date: date,
        hours_start: str,
        hours_end: str,
        meeting_format: MeetingFormat,
        location_mode: Optional[LocationMode] = None,
        common_location: Optional[str] = None,
        online_meeting_link: Optional[str] = None,
    ) -> Trip:
        """Создаёт Provider+Representative при необходимости и Trip."""
        provider = Provider(name=provider_name.strip())
        self.session.add(provider)
        await self.session.flush()

        representative = Representative(
            provider_id=provider.id,
            name=rep_name.strip(),
            email=rep_email.strip(),
        )
        self.session.add(representative)
        await self.session.flush()

        country_code = country.strip().upper()
        if country_code.startswith("K"):
            country_code = "KZ"
        elif country_code.startswith("U"):
            country_code = "UZ"

        trip = Trip(
            representative_id=representative.id,
            city=city.strip(),
            country=country_code,
            start_date=start_date,
            end_date=end_date,
            availability_hours={"start": hours_start, "end": hours_end},
            meeting_format=meeting_format,
            location_mode=location_mode,
            common_location=common_location,
            online_meeting_link=online_meeting_link,
            timezone=self.settings.timezone_for_country(country_code),
            share_token=Trip.generate_token(),
            day_highlights={},
            status=TripStatus.ACTIVE,
        )
        self.session.add(trip)
        await self.session.commit()
        await self.session.refresh(trip)

        # Подгружаем связи для ссылок/карточек
        trip = await self.get_trip(trip.id)
        assert trip is not None
        logger.info(
            "Создан Trip id=%s token=%s city=%s country=%s tz=%s",
            trip.id,
            trip.share_token,
            trip.city,
            trip.country,
            trip.timezone,
        )
        return trip

    async def get_trip(self, trip_id: int) -> Optional[Trip]:
        """Trip по id с representative и provider."""
        result = await self.session.execute(
            select(Trip)
            .where(Trip.id == trip_id)
            .options(
                selectinload(Trip.representative).selectinload(Representative.provider)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_token(self, token: str) -> Optional[Trip]:
        """Trip по share_token."""
        result = await self.session.execute(
            select(Trip)
            .where(Trip.share_token == token, Trip.status == TripStatus.ACTIVE)
            .options(
                selectinload(Trip.representative).selectinload(Representative.provider)
            )
        )
        return result.scalar_one_or_none()

    async def list_active(self, limit: int = 20) -> list[Trip]:
        """Список активных поездок."""
        result = await self.session.execute(
            select(Trip)
            .where(Trip.status == TripStatus.ACTIVE)
            .order_by(Trip.id.desc())
            .limit(limit)
            .options(
                selectinload(Trip.representative).selectinload(Representative.provider)
            )
        )
        return list(result.scalars().all())

    def build_links(self, trip: Trip) -> dict[str, str]:
        """Собирает deep-links для ручной email-рассылки."""
        base = self.settings.public_base_url.rstrip("/")
        tg_username = self.settings.telegram_bot_username.strip().lstrip("@")
        tg_link = (
            f"https://t.me/{tg_username}?start={trip.share_token}"
            if tg_username
            else f"(set TELEGRAM_BOT_USERNAME) start={trip.share_token}"
        )
        go_link = f"{base}/go/{trip.share_token}"
        wa_link = build_whatsapp_chat_url(self.settings, trip.share_token)

        return {"tg_link": tg_link, "go_link": go_link, "wa_link": wa_link}
