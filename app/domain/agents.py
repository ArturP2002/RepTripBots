"""Регистрация и поиск агентов."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Agent

logger = logging.getLogger(__name__)


class AgentService:
    """Persistent профили агентов."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_telegram(self, telegram_id: int) -> Optional[Agent]:
        result = await self.session.execute(
            select(Agent).where(Agent.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def find_by_whatsapp(self, whatsapp_id: str) -> Optional[Agent]:
        result = await self.session.execute(
            select(Agent).where(Agent.whatsapp_id == whatsapp_id)
        )
        return result.scalar_one_or_none()

    async def register(
        self,
        *,
        name: str,
        agency: str,
        email: str,
        phone: str,
        telegram_id: Optional[int] = None,
        whatsapp_id: Optional[str] = None,
        office_address: Optional[str] = None,
        city: Optional[str] = None,
        country: Optional[str] = None,
    ) -> Agent:
        """Создаёт нового агента или обновляет messenger id у существующего email."""
        agent = Agent(
            name=name.strip(),
            agency=agency.strip(),
            email=email.strip(),
            phone=phone.strip(),
            telegram_id=telegram_id,
            whatsapp_id=whatsapp_id,
            office_address=office_address,
            city=city,
            country=country,
        )
        self.session.add(agent)
        await self.session.commit()
        await self.session.refresh(agent)
        logger.info(
            "Зарегистрирован агент id=%s name=%s tg=%s wa=%s",
            agent.id,
            agent.name,
            agent.telegram_id,
            agent.whatsapp_id,
        )
        return agent

    async def update_office(self, agent: Agent, office_address: str) -> Agent:
        agent.office_address = office_address.strip()
        await self.session.commit()
        await self.session.refresh(agent)
        return agent
