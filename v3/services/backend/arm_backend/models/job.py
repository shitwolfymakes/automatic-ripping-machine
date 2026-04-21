from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, func
from sqlmodel import Field, SQLModel

from arm_common import DiscType, JobStatus, new_id


def _job_id() -> str:
    return new_id("job")


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: str = Field(default_factory=_job_id, primary_key=True)
    drive_id: str = Field(
        sa_column=Column(String, ForeignKey("drives.id"), nullable=False, index=True)
    )
    disc_type: DiscType = Field(
        sa_column=Column(
            Enum(
                DiscType,
                name="disc_type",
                native_enum=True,
                create_type=False,
                values_callable=lambda e: [x.value for x in e],
            ),
            nullable=False,
        )
    )
    title: str | None = Field(default=None)
    year: int | None = Field(sa_column=Column(Integer, nullable=True))
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default="{}"),
    )
    status: JobStatus = Field(
        sa_column=Column(
            Enum(
                JobStatus,
                name="job_status",
                native_enum=True,
                create_type=False,
                values_callable=lambda e: [x.value for x in e],
            ),
            nullable=False,
            server_default=JobStatus.CREATED.value,
            index=True,
        )
    )
    resumed_from_crash: bool = Field(
        sa_column=Column(Boolean, nullable=False, server_default="false")
    )
    started_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    ripped_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )
    updated_at: datetime | None = Field(
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        )
    )
