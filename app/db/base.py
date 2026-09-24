"""Базовый declarative Base и фабрика сессий SQLAlchemy."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


class Base(DeclarativeBase):
    """Базовый класс ORM-моделей."""


def get_engine(database_url: str | None = None) -> AsyncEngine:
    """Возвращает (или создаёт) async engine."""
    global _engine, _session_factory
    url = database_url or get_settings().database_url
    if _engine is None or (database_url and str(_engine.url) != url):
        _engine = create_async_engine(url, echo=False, pool_pre_ping=True)
        _session_factory = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Фабрика сессий."""
    get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Асинхронный генератор сессии БД."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def init_db(database_url: str | None = None) -> None:
    """Создаёт таблицы и догоняет схему для уже существующей БД."""
    from app.db import models  # noqa: F401

    engine = get_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        dialect = conn.dialect.name
        if dialect == "postgresql":
            await conn.execute(
                text(
                    "ALTER TABLE trips "
                    "ADD COLUMN IF NOT EXISTS day_highlights JSONB "
                    "NOT NULL DEFAULT '{}'::jsonb"
                )
            )
        elif dialect == "sqlite":
            try:
                await conn.execute(
                    text(
                        "ALTER TABLE trips ADD COLUMN day_highlights TEXT "
                        "DEFAULT '{}'"
                    )
                )
            except Exception:
                pass
