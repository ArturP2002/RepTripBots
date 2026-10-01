"""
Конфигурация приложения RepTrip из переменных окружения (.env).
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки пилота RepTrip."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Каналы
    telegram_enabled: bool = True
    whatsapp_enabled: bool = False

    # БД
    database_url: str = "postgresql+asyncpg://reptrip:reptrip@localhost:5432/reptrip"

    # Telegram
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    owner_telegram_ids: List[int] = Field(default_factory=list)

    # WhatsApp
    whatsapp_token: str = ""
    whatsapp_phone_number_id: str = ""
    # Номер бота для ссылок wa.me (только цифры с кодом страны, без +)
    whatsapp_display_phone: str = ""
    whatsapp_verify_token: str = "reptrip_verify"
    whatsapp_api_version: str = "v21.0"

    # Часовые пояса
    default_timezone: str = "Europe/Moscow"
    timezone_kz: str = "Asia/Almaty"
    timezone_uz: str = "Asia/Tashkent"

    # Google Calendar
    google_calendar_id: str = "primary"
    google_credentials_file: str = "secrets/google_credentials.json"
    google_token_file: str = "secrets/google_token.json"
    # Цвет подтверждённых встреч: 1–11 (11 = красный tomato — хорошо заметен)
    google_event_color_id: str = "11"
    # Цвет метки всего дня с встречами (5 = жёлтый banana)
    google_day_highlight_color_id: str = "5"

    # HTTP API
    public_base_url: str = "http://localhost:8000"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    log_level: str = "INFO"

    @field_validator("owner_telegram_ids", mode="before")
    @classmethod
    def parse_owner_ids(cls, value: object) -> list[int]:
        """Парсит OWNER_TELEGRAM_IDS из строки через запятую или списка."""
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [int(v) for v in value]
        if isinstance(value, int):
            return [value]
        text = str(value).strip()
        if not text:
            return []
        return [int(part.strip()) for part in text.split(",") if part.strip()]

    @field_validator("telegram_enabled", "whatsapp_enabled", mode="before")
    @classmethod
    def parse_bool(cls, value: object) -> bool:
        """Нормализует true/false / True/False / 1/0."""
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def timezone_for_country(self, country_code: str) -> str:
        """Возвращает IANA-таймзону по коду страны поездки (KZ/UZ)."""
        code = (country_code or "").strip().upper()
        if code in {"KZ", "KAZAKHSTAN", "КАЗАХСТАН"}:
            return self.timezone_kz
        if code in {"UZ", "UZBEKISTAN", "УЗБЕКИСТАН"}:
            return self.timezone_uz
        return self.default_timezone

    def is_owner(self, telegram_id: int | None) -> bool:
        """Проверяет, является ли пользователь владельцем бота."""
        if telegram_id is None:
            return False
        return int(telegram_id) in self.owner_telegram_ids


@lru_cache
def get_settings() -> Settings:
    """Кэшированный экземпляр настроек."""
    return Settings()
