"""ORM-модели сущностей RepTrip."""

from __future__ import annotations

import enum
import secrets
from datetime import date, datetime, time
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

# JSONB на PostgreSQL, JSON на SQLite (тесты)
JsonType = JSON().with_variant(JSONB(), "postgresql")


class MeetingFormat(str, enum.Enum):
    """Формат встречи Trip / MeetingRequest."""

    IN_PERSON = "in_person"
    ONLINE = "online"
    BOTH = "both"


class LocationMode(str, enum.Enum):
    """Режим локации для In person."""

    VISIT_OFFICES = "visit_offices"
    AGENTS_COME = "agents_come"


class TripStatus(str, enum.Enum):
    """Статус поездки."""

    ACTIVE = "active"
    CLOSED = "closed"


class MeetingRequestStatus(str, enum.Enum):
    """Статус заявки агента."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    DECLINED = "declined"


class BookingStatus(str, enum.Enum):
    """Статус бронирования."""

    ACTIVE = "active"
    CANCELLED = "cancelled"


class Provider(Base):
    """Educational provider (организация)."""

    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    representatives: Mapped[list["Representative"]] = relationship(
        back_populates="provider"
    )


class Representative(Base):
    """Представитель provider, который едет в поездку."""

    __tablename__ = "representatives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    provider: Mapped[Provider] = relationship(back_populates="representatives")
    trips: Mapped[list["Trip"]] = relationship(back_populates="representative")


class Trip(Base):
    """Поездка / встреча с уникальной share-ссылкой."""

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    representative_id: Mapped[int] = mapped_column(
        ForeignKey("representatives.id"), nullable=False
    )
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    country: Mapped[str] = mapped_column(String(8), nullable=False)  # KZ / UZ
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Часы встреч: {"start": "10:00", "end": "18:00"}
    availability_hours: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    meeting_format: Mapped[MeetingFormat] = mapped_column(
        Enum(MeetingFormat, name="meeting_format", native_enum=False),
        nullable=False,
    )
    location_mode: Mapped[Optional[LocationMode]] = mapped_column(
        Enum(LocationMode, name="location_mode", native_enum=False),
        nullable=True,
    )
    common_location: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    online_meeting_link: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    share_token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    # Метки дней в Google Calendar: {"2026-09-21": "eventId", ...}
    day_highlights: Mapped[dict[str, Any]] = mapped_column(
        JsonType, nullable=False, default=dict, server_default="{}"
    )
    status: Mapped[TripStatus] = mapped_column(
        Enum(TripStatus, name="trip_status", native_enum=False),
        default=TripStatus.ACTIVE,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    representative: Mapped[Representative] = relationship(back_populates="trips")
    meeting_requests: Mapped[list["MeetingRequest"]] = relationship(
        back_populates="trip"
    )

    @staticmethod
    def generate_token() -> str:
        """Генерирует уникальный token для ссылки на Trip."""
        return secrets.token_urlsafe(16)


class Agent(Base):
    """Агент — persistent профиль после регистрации."""

    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("telegram_id", name="uq_agents_telegram_id"),
        UniqueConstraint("whatsapp_id", name="uq_agents_whatsapp_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    agency: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(64), nullable=False)
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    whatsapp_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    office_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    do_not_contact: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    meeting_requests: Mapped[list["MeetingRequest"]] = relationship(
        back_populates="agent"
    )


class MeetingRequest(Base):
    """Заявка агента на слот (ещё не бронь)."""

    __tablename__ = "meeting_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), nullable=False)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    requested_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    meeting_format: Mapped[MeetingFormat] = mapped_column(
        Enum(MeetingFormat, name="mr_meeting_format", native_enum=False),
        nullable=False,
    )
    office_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    online_meeting_link: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[MeetingRequestStatus] = mapped_column(
        Enum(
            MeetingRequestStatus,
            name="meeting_request_status",
            native_enum=False,
        ),
        default=MeetingRequestStatus.PENDING,
        nullable=False,
    )
    # Канал, с которого пришла заявка (для ответа агенту)
    source_channel: Mapped[str] = mapped_column(String(16), nullable=False)  # telegram|whatsapp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    trip: Mapped[Trip] = relationship(back_populates="meeting_requests")
    agent: Mapped[Agent] = relationship(back_populates="meeting_requests")
    booking: Mapped[Optional["Booking"]] = relationship(
        back_populates="meeting_request", uselist=False
    )


class Booking(Base):
    """Подтверждённая встреча."""

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_request_id: Mapped[int] = mapped_column(
        ForeignKey("meeting_requests.id"), unique=True, nullable=False
    )
    confirmed_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    calendar_event_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status", native_enum=False),
        default=BookingStatus.ACTIVE,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    meeting_request: Mapped[MeetingRequest] = relationship(back_populates="booking")
