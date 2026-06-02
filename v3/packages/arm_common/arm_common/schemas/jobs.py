from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from arm_common.enums import DiscType, JobStatus, SessionApplicationStatus, TrackKind, TrackStatus


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


class RipProgressSummary(BaseModel):
    """Per-job rip-phase summary surfaced on `JobView` so the dashboard can
    render `Track 3 / 8` without an N+1 fetch against `/api/jobs/{id}`.

    Populated only for jobs in `JobStatus.RIPPING`. `current_track_index`
    is the 1-based ordinal among `tracks` sorted by `Track.index` of the
    row currently in `IN_PROGRESS` (None if the rip is between tracks
    or just got going). Live progress percent for that track flows on
    the `ripper.progress.{job_id}` WS topic — not stored here.
    """

    tracks_total: int
    tracks_done: int
    tracks_failed: int
    current_track_id: str | None
    current_track_index: int | None


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
    # Populated only by the list endpoint for ripping jobs; None on
    # detail responses and on terminal/early-state jobs.
    rip_progress: RipProgressSummary | None = None


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
    # `expected_size_bytes` is the scan-time MakeMKV estimate (TINFO:t,11);
    # `size_bytes` is the post-rip actual from disk. UI prefers the actual
    # when present, falls back to the estimate (prefixed `~`) before the
    # rip starts so the tracks table isn't all em-dashes pre-rip.
    expected_size_bytes: int | None = None
    # `duration_seconds` is the post-rip actual; `expected_duration_seconds`
    # is the scan-time estimate (set by `select_tracks` at rip-start).
    # Until the ripper measures real durations from the produced files,
    # the dispatcher copies expected → actual at PATCH-DONE time so the
    # UI / transcoder don't see null durations on completed tracks.
    duration_seconds: int | None
    expected_duration_seconds: int | None = None
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


class ResolveFanOutOutcomeView(BaseModel):
    """One waiting_identify application's post-resolve outcome.

    `status='queued'` + `skipped_reason=None` → the application was
    promoted and `task_count` newly-created transcode tasks are queued.
    Anything else → the application stays parked in `waiting_identify`
    and `error_detail` carries the reason for the UI to surface.
    """

    session_application_id: str
    session_id: str
    status: SessionApplicationStatus
    task_count: int
    skipped_reason: Literal["collisions", "template", "session_missing"] | None = None
    error_detail: str | None = None


class ResolveResponse(BaseModel):
    """POST /api/jobs/{id}/resolve response. The job always reflects the
    just-applied identity (status flipped to `identified`); `fan_out` lists
    the per-application outcomes from the parked-applications promotion
    pass — empty when no session was applied to the job before resolve.
    """

    job: JobView
    fan_out: list[ResolveFanOutOutcomeView]
