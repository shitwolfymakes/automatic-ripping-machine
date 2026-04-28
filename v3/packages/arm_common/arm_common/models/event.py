from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from arm_common.ulid import new_id


def _event_id() -> str:
    return new_id("evt")


class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: str = Field(default_factory=_event_id, primary_key=True)
    event_type: str = Field(sa_column=Column(String, nullable=False, index=True))
    emitted_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    )
    job_id: str | None = Field(
        sa_column=Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True, index=True)
    )
    track_id: str | None = Field(sa_column=Column(String, ForeignKey("tracks.id", ondelete="CASCADE"), nullable=True))
    session_application_id: str | None = Field(
        sa_column=Column(String, ForeignKey("session_applications.id", ondelete="CASCADE"), nullable=True)
    )
    payload_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default="{}"),
    )
