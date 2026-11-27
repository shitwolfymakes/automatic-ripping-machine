from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlmodel import Field, SQLModel

from arm_common.enums import StageStatus
from arm_common.models._columns import created_at_column, enum_column, updated_at_column
from arm_common.ulid import new_id


def _track_stage_id() -> str:
    return new_id("stg")


class TrackStage(SQLModel, table=True):
    """One track's copy from /raw into staging; one row per track (D7)."""

    __tablename__ = "track_stages"

    id: str = Field(default_factory=_track_stage_id, primary_key=True)
    track_id: str = Field(
        sa_column=Column(String, ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    )
    job_id: str = Field(sa_column=Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True))
    status: StageStatus = Field(
        sa_column=enum_column(StageStatus, "stage_status", server_default=StageStatus.PENDING.value)
    )
    source_path: str = Field(sa_column=Column(String, nullable=False))
    # Stamped when the copy starts; a different stamp later means a re-rip replaced the source.
    source_size: int | None = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    source_mtime_ns: int | None = Field(default=None, sa_column=Column(BigInteger, nullable=True))
    dest_path: str = Field(sa_column=Column(String, nullable=False))
    # Last fsynced checkpoint of the copy.
    bytes_durable: int = Field(default=0, sa_column=Column(BigInteger, nullable=False, server_default="0"))
    linked: bool | None = Field(default=None, sa_column=Column(Boolean, nullable=True))
    attempts: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    last_error: str | None = Field(default=None)
    # Last time bytes advanced; not a liveness beat (a thread blocked in a syscall must stop it).
    heartbeat_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    staged_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime | None = Field(sa_column=created_at_column())
    updated_at: datetime | None = Field(sa_column=updated_at_column())
