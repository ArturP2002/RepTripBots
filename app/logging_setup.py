"""
Настройка подробного логирования RepTrip на русском языке.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(level: str = "INFO") -> None:
    """
    Инициализирует логирование в консоль и файл logs/reptrip.log.

    Все сообщения приложения пишутся на русском (в местах вызова logger).
    """
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        log_dir / "reptrip.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Приглушаем шумные сторонние логгеры
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)

    logging.getLogger(__name__).info(
        "Логирование инициализировано (уровень=%s, файл=logs/reptrip.log)",
        level.upper(),
    )
