from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlmodel import Field, SQLModel

from arm_backend.models._columns import created_at_column, enum_column, updated_at_column
from arm_common import TranscodeTaskStatus, new_id


def _transcode_task_id() -> str:
    return new_id("txt")


class TranscodeTask(SQLModel, table=True):
    __tablename__ = "transcode_tasks"

    id: str = Field(default_factory=_transcode_task_id, primary_key=True)
    session_application_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("session_applications.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    source_track_id: str = Field(
        sa_column=Column(String, ForeignKey("tracks.id", ondelete="RESTRICT"), nullable=False)
    )
    status: TranscodeTaskStatus = Field(
        sa_column=enum_column(
            TranscodeTaskStatus,
            "transcode_task_status",
            server_default=TranscodeTaskStatus.QUEUED.value,
            index=True,
        )
    )
    claimed_by: str | None = Field(default=None)
    claim_heartbeat_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    attempts: int = Field(sa_column=Column(Integer, nullable=False, server_default="0"))
    output_path: str | None = Field(default=None)
    progress_pct: int = Field(
        sa_column=Column(Integer, nullable=False, server_default="0")
    )
    last_error: str | None = Field(default=None)
    created_at: datetime | None = Field(sa_column=created_at_column())
    updated_at: datetime | None = Field(sa_column=updated_at_column())
