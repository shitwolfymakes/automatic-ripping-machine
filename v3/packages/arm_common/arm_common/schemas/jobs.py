from datetime import datetime
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


class BulkDeleteJobsResponse(BaseModel):
    """DELETE /api/jobs response. `deleted_ids` lists the jobs whose DB
    rows were removed; `skipped_non_terminal` lists job IDs that were
    refused because they were still in flight (caller should abandon
    them first if they really want them gone)."""

    deleted_ids: list[str]
    skipped_non_terminal: list[str]


class DiscFingerprintView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    algo: str
    value: str
    created_at: datetime | None = None


class JobView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    drive_id: str
    disc_type: DiscType
    status: JobStatus
    title: str | None
    year: int | None
    # Computed at identify; UI prefers `poster_url_manual` if set.
    poster_url: str | None = None
    poster_url_manual: str | None = None
    metadata_json: dict[str, Any]
    resumed_from_crash: bool


class JobUpdateRequest(BaseModel):
    """PATCH /api/jobs/{id} body. Currently only the manual poster override
    is editable — title/year live behind the identify/resolve flow.
    """

    poster_url_manual: str | None = None


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
    # Per-rip `--minlength` override resolved from the Session's
    # `overrides_json["min_length_seconds"]`. None means "use the
    # ripper's host-side baseline" (`ARM_MIN_LENGTH_SECONDS`, default
    # 600). Surfaced here so the ripper doesn't have to read Session
    # state itself.
    min_length_seconds: int | None = None
