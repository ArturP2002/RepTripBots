"""
Локальный сид демо-данных (Provider / Representative / Trip).

Запуск: python scripts/seed_demo.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.db.base import get_session_factory, init_db  # noqa: E402
from app.db.models import LocationMode, MeetingFormat  # noqa: E402
from app.domain.trips import TripService  # noqa: E402
from app.logging_setup import setup_logging  # noqa: E402


async def main() -> None:
    setup_logging("INFO")
    settings = get_settings()
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        service = TripService(session, settings)
        trip = await service.create_trip(
            provider_name="Demo University",
            rep_name="Ivan Petrov",
            rep_email="ivan@example.com",
            city="Almaty",
            country="KZ",
            start_date=date.today() + timedelta(days=14),
            end_date=date.today() + timedelta(days=16),
            hours_start="10:00",
            hours_end="18:00",
            meeting_format=MeetingFormat.BOTH,
            location_mode=LocationMode.AGENTS_COME,
            common_location="Hilton Almaty, lobby",
            online_meeting_link="https://meet.example.com/reptrip-demo",
        )
        links = service.build_links(trip)
        print("Демо Trip создан:")
        print(f"  id={trip.id} token={trip.share_token} tz={trip.timezone}")
        print(f"  Telegram: {links['tg_link']}")
        print(f"  Go page:  {links['go_link']}")


if __name__ == "__main__":
    asyncio.run(main())
