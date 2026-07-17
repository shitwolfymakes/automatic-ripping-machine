from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, Integer, String
from sqlmodel import Field, SQLModel

from arm_common.models._columns import created_at_column, enum_column, updated_at_column
from arm_common.enums import TrackKind, TrackStatus
from arm_common.ulid import new_id


def _track_id() -> str:
    return new_id("trk")


class Track(SQLModel, table=True):
    __tablename__ = "tracks"

    id: str = Field(default_factory=_track_id, primary_key=True)
    job_id: str = Field(sa_column=Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True))
    kind: TrackKind = Field(sa_column=enum_column(TrackKind, "track_kind"))
    index: int = Field(sa_column=Column(Integer, nullable=False))
    source_ref: str = Field(sa_column=Column(String, nullable=False))
    label: str | None = Field(default=None)
    role: str | None = Field(default=None)
    role_source: str | None = Field(default=None)
    edition: str | None = Field(default=None)
    # Per-track identity (operator-editable; null = inherit job-level). For
    # multi-title discs (TV box sets / multi-movie) each VIDEO_TITLE track
    # carries its own identity. B23 (TVDB matcher) later auto-fills episode_*.
    title: str | None = Field(default=None)
    year: int | None = Field(default=None)
    imdb_id: str | None = Field(default=None)
    poster_url: str | None = Field(default=None)
    video_type: str | None = Field(default=None)
    episode_number: int | None = Field(default=None)
    episode_name: str | None = Field(default=None)
    # Operator control. `excluded` omits this ripped title from transcode OUTPUT
    # (the disc still rips whole — makemkvcon `mkv all` invariant). `custom_filename`
    # overrides the pattern-rendered name for this track.
    excluded: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, server_default="false"))
    custom_filename: str | None = Field(default=None)
    expected_duration_seconds: int | None = Field(sa_column=Column(Integer, nullable=True))
    # Scan-time size estimate from MakeMKV TINFO:t,11. Lets the JobDetail
    # tracks table show a "~26 GB" size before the rip starts; the
    # post-rip actual `size_bytes` overrides it once the file lands.
    expected_size_bytes: int | None = Field(sa_column=Column(BigInteger, nullable=True))
    status: TrackStatus = Field(
        sa_column=enum_column(TrackStatus, "track_status", server_default=TrackStatus.QUEUED.value)
    )
    attempts: int = Field(sa_column=Column(Integer, nullable=False, server_default="0"))
    output_path: str | None = Field(default=None)
    size_bytes: int | None = Field(sa_column=Column(BigInteger, nullable=True))
    sha256: str | None = Field(default=None)
    duration_seconds: int | None = Field(sa_column=Column(Integer, nullable=True))
    last_error: str | None = Field(default=None)
    created_at: datetime | None = Field(sa_column=created_at_column())
    updated_at: datetime | None = Field(sa_column=updated_at_column())
