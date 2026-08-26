from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from arm_common.enums import DiscType, JobStatus, SessionApplicationStatus, TrackKind, TrackStatus, TranscodeTaskStatus


class ResolveRequest(BaseModel):
    title: str
    year: int | None = None
    disc_number: int | None = None
    disc_total: int | None = None
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


class TranscodeProgressSummary(BaseModel):
    """Per-job transcode-phase summary surfaced on `JobView`, derived by
    aggregating ALL of a job's `SessionApplication` rows. `state` is the
    job-level rollup (see `_summarize_transcode_progress`): `transcoding`
    while any session is in-flight, `done`/`done_partial`/`failed` once all
    are terminal. `None` on `JobView` means no session was applied (the job
    is `ripped`/awaiting action). Live per-task percent flows on the
    `transcode.progress.{task_id}` WS topic; `percent` here is a poll-time
    mean of the job's task `progress_pct`.
    """

    state: Literal["transcoding", "done", "done_partial", "failed"]
    tasks_total: int
    tasks_done: int
    percent: float


class JobView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    # Nullable: SET NULL when the drive that ran this job is later deleted
    # (a Drive row is disposable operational state). `drive_serial` is the
    # permanent record of which physical drive this was.
    drive_id: str | None
    drive_serial: str | None = None
    disc_type: DiscType
    status: JobStatus
    title: str | None
    year: int | None
    disc_number: int | None = None
    disc_total: int | None = None
    # Computed at identify; UI prefers `poster_url_manual` if set.
    poster_url: str | None = None
    poster_url_manual: str | None = None
    metadata_json: dict[str, Any]
    resumed_from_crash: bool
    # Timed review gate: when the countdown started (AWAITING_REVIEW). Drives the
    # ripper's remaining-delay calc + the UI's cosmetic countdown. Null otherwise.
    wait_start_time: datetime | None = None
    # Per-job review-gate pause: freezes this disc's countdown (UI shows paused).
    manual_pause: bool = False
    # Populated only by the list endpoint for ripping jobs; None on
    # detail responses and on terminal/early-state jobs.
    rip_progress: RipProgressSummary | None = None
    # Populated by the jobs list + detail endpoints by aggregating the job's
    # session_applications. None when no session has been applied.
    transcode_progress: TranscodeProgressSummary | None = None


class HeldJobView(BaseModel):
    """Boot-probe payload for a disc held in AWAITING_REVIEW (timed review gate).

    `paused` is true when the held disc should survive a ripper reboot as a hold
    (global `ripping_paused` on — or, once it lands, a per-job pause). The ripper
    uses it to choose re-park (paused) vs. abandon-and-self-heal (counting down)
    on restart. See the timed-review-gate spec §6.3.
    """

    job: JobView
    paused: bool


class TrackEditRequest(BaseModel):
    """One entry in JobUpdateRequest.tracks. `track_id` selects the row; every
    other field is an optional operator edit (omitted=untouched, null=clear)."""

    model_config = ConfigDict(extra="forbid")

    track_id: str
    title: str | None = None
    year: int | None = None
    imdb_id: str | None = None
    poster_url: str | None = None
    video_type: str | None = None
    episode_number: int | None = None
    episode_name: str | None = None
    excluded: bool | None = None
    custom_filename: str | None = None


class JobUpdateRequest(BaseModel):
    """PATCH /api/jobs/{id} body. `poster_url_manual` + disc fields edit the job;
    `tracks` applies per-track operator edits in the same atomic save. The JOB's
    title/year still live behind identify/resolve."""

    model_config = ConfigDict(extra="forbid")

    poster_url_manual: str | None = None
    disc_number: int | None = None
    disc_total: int | None = None
    tracks: list[TrackEditRequest] | None = None


class TrackView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    kind: TrackKind
    index: int
    source_ref: str
    status: TrackStatus
    # Status of the track's MOST-RECENT transcode_task (queued | in_progress |
    # done | failed). None when no transcode task exists yet (pre-session,
    # music, data tracks). NOT the rip status (`status` above) — this is the
    # transcode phase. Display-only; set by get_job_detail, not a Track column.
    transcode_status: TranscodeTaskStatus | None = None
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
    label: str | None = None
    role: str | None = None
    edition: str | None = None
    title: str | None = None
    year: int | None = None
    imdb_id: str | None = None
    poster_url: str | None = None
    video_type: str | None = None
    episode_number: int | None = None
    episode_name: str | None = None
    excluded: bool = False
    custom_filename: str | None = None


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


class JobStatsResponse(BaseModel):
    """Dashboard aggregates. `by_type` counts `Job.disc_type` (the only type
    fact on the Job row itself; media_type lives on the applied Session)."""

    total: int
    by_status: dict[str, int]
    by_type: dict[str, int]
