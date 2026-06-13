from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Field, SQLModel

from arm_common.models._columns import created_at_column, updated_at_column
from arm_common.ulid import new_id


def _notification_channel_id() -> str:
    return new_id("ncl")


class NotificationChannel(SQLModel, table=True):
    __tablename__ = "notification_channels"

    id: str = Field(default_factory=_notification_channel_id, primary_key=True)
    # Discriminator for the config union. Only "apprise" is implemented; the
    # column is VARCHAR so webhook/bash can be added later without a migration.
    type: str = Field(sa_column=Column(String, nullable=False))
    name: str = Field(sa_column=Column(String, nullable=False))
    enabled: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, server_default="true"))
    # The channel-config dict: {type, url, service_id?, fields?}.
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default="{}"))
    # Subset of NOTIFIABLE_EVENT_TYPES. ARRAY(String) mirrors the legacy
    # Config.notification_apprise_urls precedent (flat string set we filter on).
    subscribed_events: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )
    # {event_type: {"title"?: str, "body"?: str}} per-event overrides.
    templates: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False, server_default="{}")
    )
    last_fired_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    last_success_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    last_error: str | None = Field(default=None)
    created_by_user_id: str | None = Field(
        sa_column=Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    )
    created_at: datetime | None = Field(sa_column=created_at_column())
    updated_at: datetime | None = Field(sa_column=updated_at_column())
