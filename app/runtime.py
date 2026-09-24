"""Хранилище runtime-зависимостей (бот Telegram, календарь, нотификатор)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Coroutine, Optional

if TYPE_CHECKING:
    from aiogram import Bot

    from app.adapters.calendar import CalendarPort

_bot: Optional["Bot"] = None
_calendar: Optional["CalendarPort"] = None
# callback: async (meeting_request) -> None — уведомить владельцев в TG
_notify_owners: Optional[Callable[..., Coroutine[Any, Any, None]]] = None
# callback: async (meeting_request, kind, **kwargs) -> None — ответ агенту
_notify_agent: Optional[Callable[..., Coroutine[Any, Any, None]]] = None


def set_bot(bot: "Bot") -> None:
    global _bot
    _bot = bot


def get_bot() -> Optional["Bot"]:
    return _bot


def set_calendar(calendar: "CalendarPort") -> None:
    global _calendar
    _calendar = calendar


def get_calendar() -> "CalendarPort":
    if _calendar is None:
        raise RuntimeError("Календарь ещё не инициализирован")
    return _calendar


def set_notify_owners(cb: Callable[..., Coroutine[Any, Any, None]]) -> None:
    global _notify_owners
    _notify_owners = cb


def get_notify_owners():
    return _notify_owners


def set_notify_agent(cb: Callable[..., Coroutine[Any, Any, None]]) -> None:
    global _notify_agent
    _notify_agent = cb


def get_notify_agent():
    return _notify_agent
