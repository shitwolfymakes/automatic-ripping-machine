from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from arm_common.enums import DiscType, JobStatus, TrackKind, TrackStatus


class ResolveRequest(BaseModel):
    title: str
    year: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ManualTriggerRequest(BaseModel):
    """POST /api/jobs/manual — kick off a rip on a drive that already has a
    disc in the tray. The ripper picks it up via WS command and runs the
    normal scan→identify→rip flow; the optional `session_id` is stamped on
    the resulting Job's metadata so `rip-complete` auto-applies it.
    """

    drive_id: str
    session_id: str | None = None


class ManualTriggerResponse(BaseModel):
    drive_id: str
    session_id: str | None


class AbandonJobRequest(BaseModel):
    """POST /api/jobs/{id}/abandon body. `delete_raw=true` also wipes
    `/raw/{job_id}/` so the drive can be reused without leftover partial
    rips on disk. The DB row stays (status=abandoned) for audit."""

    delete_raw: bool = False


class JobView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    drive_id: str
    disc_type: DiscType
    status: JobStatus
    title: str | None
    year: int | None
    metadata_json: dict[str, Any]
    resumed_from_crash: bool


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
