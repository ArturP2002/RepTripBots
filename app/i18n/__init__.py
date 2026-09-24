"""Хелпер локализации сообщений бота (ru / en)."""

from __future__ import annotations

from typing import Any, Mapping

from app.i18n import en as en_texts
from app.i18n import ru as ru_texts

_CATALOGS: dict[str, Mapping[str, str]] = {
    "ru": ru_texts.TEXTS,
    "en": en_texts.TEXTS,
}


def t(lang: str, key: str, **kwargs: Any) -> str:
    """
    Возвращает текст по ключу для языка lang.

    :param lang: 'ru' для владельца, 'en' для агентов
    :param key: ключ из словаря TEXTS
    """
    catalog = _CATALOGS.get(lang) or _CATALOGS["en"]
    template = catalog.get(key) or _CATALOGS["en"].get(key) or key
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError):
            return template
    return template
