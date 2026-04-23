from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from arm_backend.models._columns import created_at_column, enum_column
from arm_common import SessionApplicationStatus, new_id


def _session_application_id() -> str:
    return new_id("sap")


class SessionApplication(SQLModel, table=True):
    __tablename__ = "session_applications"

    id: str = Field(default_factory=_session_application_id, primary_key=True)
    session_id: str = Field(
        sa_column=Column(String, ForeignKey("sessions.id", ondelete="RESTRICT"), nullable=False, index=True)
    )
    job_id: str = Field(sa_column=Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True))
    status: SessionApplicationStatus = Field(
        sa_column=enum_column(
            SessionApplicationStatus,
            "session_application_status",
            server_default=SessionApplicationStatus.QUEUED.value,
        )
    )
    overrides_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    overwrite: bool = Field(sa_column=Column(Boolean, nullable=False, server_default="false"))
    created_by_user_id: str | None = Field(
        sa_column=Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    )
    created_at: datetime | None = Field(sa_column=created_at_column())
    completed_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
