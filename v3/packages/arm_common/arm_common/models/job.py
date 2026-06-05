from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlmodel import Field, SQLModel

from arm_common.models._columns import created_at_column, enum_column, updated_at_column
from arm_common.enums import DiscType, JobStatus
from arm_common.ulid import new_id


def _job_id() -> str:
    return new_id("job")


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: str = Field(default_factory=_job_id, primary_key=True)
    drive_id: str = Field(sa_column=Column(String, ForeignKey("drives.id"), nullable=False, index=True))
    disc_type: DiscType = Field(sa_column=enum_column(DiscType, "disc_type"))
    # Fingerprints (CRC64, AACS Disc ID, MusicBrainz Disc ID, matrix256, …)
    # live in `disc_fingerprints` keyed by (job_id, algo) — see
    # arm_common.models.disc_fingerprint. Old single-value columns
    # (disc_fingerprint, disc_fingerprint_algo, aacs_disc_id) were dropped
    # in migration 0006 to make the multi-fingerprint design first-class.
    title: str | None = Field(default=None)
    year: int | None = Field(sa_column=Column(Integer, nullable=True))
    # Poster shown in the UI. `poster_url` is computed at identify time
    # (TMDB / OMDB / Cover Art Archive). `poster_url_manual` is a user
    # override editable from JobDetail; the UI prefers it when set.
    poster_url: str | None = Field(sa_column=Column(String, nullable=True))
    poster_url_manual: str | None = Field(sa_column=Column(String, nullable=True))
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default="{}"),
    )
    status: JobStatus = Field(
        sa_column=enum_column(JobStatus, "job_status", server_default=JobStatus.CREATED.value, index=True)
    )
    resumed_from_crash: bool = Field(sa_column=Column(Boolean, nullable=False, server_default="false"))
    started_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    ripped_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime | None = Field(sa_column=created_at_column())
    updated_at: datetime | None = Field(sa_column=updated_at_column())
