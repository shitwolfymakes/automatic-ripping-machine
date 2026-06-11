from datetime import datetime

from sqlalchemy import Boolean, Column, ForeignKey, String
from sqlmodel import Field, SQLModel

from arm_common.models._columns import created_at_column
from arm_common.ulid import new_id


def _notification_dispatch_log_id() -> str:
    return new_id("ndl")


class NotificationDispatchLog(SQLModel, table=True):
    __tablename__ = "notification_dispatch_log"

    id: str = Field(default_factory=_notification_dispatch_log_id, primary_key=True)
    # null = ad-hoc test-send with no saved channel.
    channel_id: str | None = Field(
        sa_column=Column(
            String,
            ForeignKey("notification_channels.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        )
    )
    # null for test-sends; SET NULL so the log row survives event deletion.
    event_id: str | None = Field(sa_column=Column(String, ForeignKey("events.id", ondelete="SET NULL"), nullable=True))
    # Denormalized so the log survives event + channel deletion.
    event_type: str = Field(sa_column=Column(String, nullable=False))
    title: str = Field(sa_column=Column(String, nullable=False))
    body: str = Field(sa_column=Column(String, nullable=False))
    success: bool = Field(sa_column=Column(Boolean, nullable=False))
    error: str | None = Field(default=None)
    created_at: datetime | None = Field(sa_column=created_at_column())
