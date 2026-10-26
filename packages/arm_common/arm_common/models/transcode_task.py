from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, text
from sqlmodel import Field, SQLModel

from arm_common.models._columns import created_at_column, enum_column, updated_at_column
from arm_common.enums import TranscodeTaskStatus
from arm_common.ulid import new_id


def _transcode_task_id() -> str:
    return new_id("txt")


class TranscodeTask(SQLModel, table=True):
    __tablename__ = "transcode_tasks"
    # Mirrors 0001_initial so metadata-built schemas (the e2e harness) carry the
    # same indexes. The partial unique index is the race backstop for the
    # output_path collision check: only one live task may own a path.
    __table_args__ = (
        Index("ix_transcode_tasks_status_heartbeat", "status", "claim_heartbeat_at"),
        Index(
            "uq_transcode_tasks_output_path_live",
            "output_path",
            unique=True,
            postgresql_where=text("status IN ('queued', 'in_progress', 'done')"),
            sqlite_where=text("status IN ('queued', 'in_progress', 'done')"),
        ),
    )

    id: str = Field(default_factory=_transcode_task_id, primary_key=True)
    session_application_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("session_applications.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    source_track_id: str = Field(sa_column=Column(String, ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False))
    status: TranscodeTaskStatus = Field(
        sa_column=enum_column(
            TranscodeTaskStatus,
            "transcode_task_status",
            server_default=TranscodeTaskStatus.QUEUED.value,
        )
    )
    claimed_by: str | None = Field(default=None)
    claim_heartbeat_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    # When the current attempt was claimed; unlike claim_heartbeat_at it is not
    # touched by heartbeats, so the UI measures encode time from it.
    started_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    attempts: int = Field(sa_column=Column(Integer, nullable=False, server_default="0"))
    output_path: str | None = Field(default=None)
    progress_pct: int = Field(sa_column=Column(Integer, nullable=False, server_default="0"))
    # The latest heartbeat's encoder telemetry, so a client that polls (or a
    # card that mounts mid-encode) sees the same ETA and frame rate the live
    # transcode.progress.{task_id} event carries. Reset at claim; null until
    # the first heartbeat and for engines that do not report a value.
    current_pass: str | None = Field(default=None)
    eta_seconds: int | None = Field(default=None)
    fps: float | None = Field(sa_column=Column(Float, nullable=True))
    avg_fps: float | None = Field(sa_column=Column(Float, nullable=True))
    last_error: str | None = Field(default=None)
    created_at: datetime | None = Field(sa_column=created_at_column())
    updated_at: datetime | None = Field(sa_column=updated_at_column())
