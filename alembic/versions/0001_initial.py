"""Начальная схема RepTrip."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "providers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "agents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("agency", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=64), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("whatsapp_id", sa.String(length=64), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("country", sa.String(length=8), nullable=True),
        sa.Column("office_address", sa.String(length=500), nullable=True),
        sa.Column("do_not_contact", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id", name="uq_agents_telegram_id"),
        sa.UniqueConstraint("whatsapp_id", name="uq_agents_whatsapp_id"),
    )
    op.create_table(
        "representatives",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "trips",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("representative_id", sa.Integer(), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("country", sa.String(length=8), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("availability_hours", sa.JSON(), nullable=False),
        sa.Column("meeting_format", sa.String(length=32), nullable=False),
        sa.Column("location_mode", sa.String(length=32), nullable=True),
        sa.Column("common_location", sa.String(length=500), nullable=True),
        sa.Column("online_meeting_link", sa.String(length=500), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("share_token", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["representative_id"], ["representatives.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("share_token"),
    )
    op.create_index("ix_trips_share_token", "trips", ["share_token"])
    op.create_table(
        "meeting_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("requested_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("meeting_format", sa.String(length=32), nullable=False),
        sa.Column("office_address", sa.String(length=500), nullable=True),
        sa.Column("online_meeting_link", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_channel", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("meeting_request_id", sa.Integer(), nullable=False),
        sa.Column("confirmed_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("calendar_event_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["meeting_request_id"], ["meeting_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_request_id"),
    )


def downgrade() -> None:
    op.drop_table("bookings")
    op.drop_table("meeting_requests")
    op.drop_index("ix_trips_share_token", table_name="trips")
    op.drop_table("trips")
    op.drop_table("representatives")
    op.drop_table("agents")
    op.drop_table("providers")
