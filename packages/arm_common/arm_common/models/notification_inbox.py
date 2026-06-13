from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlmodel import Field, SQLModel

from arm_common.models._columns import created_at_column
from arm_common.ulid import new_id


def _notification_inbox_id() -> str:
    return new_id("nin")


class NotificationInbox(SQLModel, table=True):
    __tablename__ = "notification_inbox"

    id: str = Field(default_factory=_notification_inbox_id, primary_key=True)
    # The source event; SET NULL so the inbox row survives event deletion.
    event_id: str | None = Field(sa_column=Column(String, ForeignKey("events.id", ondelete="SET NULL"), nullable=True))
    # The inapp channel that recorded this row.
    channel_id: str | None = Field(
        sa_column=Column(String, ForeignKey("notification_channels.id", ondelete="CASCADE"), nullable=True)
    )
    # Denormalized so the row survives event deletion.
    event_type: str = Field(sa_column=Column(String, nullable=False))
    title: str = Field(sa_column=Column(String, nullable=False))
    message: str = Field(sa_column=Column(String, nullable=False))
    # UI deep-link target.
    job_id: str | None = Field(sa_column=Column(String, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True))
    seen: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default="false"))
    cleared: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default="false"))
    seen_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    cleared_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime | None = Field(sa_column=created_at_column())
