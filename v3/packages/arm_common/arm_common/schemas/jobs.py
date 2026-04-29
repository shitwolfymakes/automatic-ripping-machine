from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from arm_common.enums import DiscType, JobStatus, TrackKind, TrackStatus


class ResolveRequest(BaseModel):
    title: str
    year: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    drive_id: str
    disc_type: DiscType
    status: JobStatus
    title: str | None
    year: int | None
    metadata_json: dict[str, Any]


class TrackView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    kind: TrackKind
    index: int
    source_ref: str
    status: TrackStatus
    output_path: str | None
    size_bytes: int | None
    duration_seconds: int | None
    attempts: int
    last_error: str | None


class RipStartResponse(BaseModel):
    job_id: str
    rip_preset_id: str
    tracks: list[TrackView]
