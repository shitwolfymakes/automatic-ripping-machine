import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import ColumnElement, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt, require_writer
from arm_backend.auto_session import (
    SessionNotFoundError,
    apply_session_internal,
)
from arm_backend.config import settings
from arm_backend.db import get_session
from arm_backend.identity.apply import apply_identity_result, suggestion_to_result
from arm_backend.identity.manual_edits import apply_manual_edits
from arm_backend.identity.resolve_service import identity_snapshot, resolve_identity
from arm_backend.identity.stage_runner import EpisodeStageRunner
from arm_backend.job_abandon import abandon_job_transition
from arm_backend.job_files import delete_job_files
from arm_backend.job_views import job_detail_view, job_list_views
from arm_backend.log_reader import per_job_log_path
from arm_backend.metadata.identity_payload import external_ids_of
from arm_backend.path_template import TemplateValidationError
from arm_backend.routers._deps import get_hub, get_stage_runner
from arm_backend.routers._params import JobIdParam
from arm_backend.constants import CONFIG_SINGLETON_ID
from arm_backend.ws import WSHub
from arm_common import (
    Config,
    DiscFingerprint,
    Drive,
    DriveMediaStatus,
    Job,
    JobStatus,
    MediaType,
    Session,
    TranscodeTaskStatus,
    User,
)
from arm_common.models import Track, TranscodeTask
from arm_common.models._columns import enum_value_str
from arm_common.schemas import (
    AbandonJobRequest,
    ApplySessionRequest,
    ApplySessionResponse,
    BulkDeleteJobsRequest,
    BulkDeleteJobsResponse,
    JobDetailView,
    JobStatsResponse,
    JobUpdateRequest,
    JobView,
    ManualTriggerRequest,
    ManualTriggerResponse,
    RipAgainResponse,
    ResolveRequest,
    ResolveResponse,
    SessionApplicationView,
    TranscodeTaskView,
)
from arm_common.enums import (
    NON_TERMINAL_JOB_STATUSES,
    POST_RIP_JOB_STATUSES,
    RESOLVABLE_JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
)
from arm_common.schemas.job_metadata import (
    identity_suggestion_of,
    previously_ripped_job_id,
    with_flags,
    without_identity_suggestion,
)

logger = logging.getLogger("arm_backend.routers.jobs")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# Manual-trigger pre-check (drive media status). The ripper posts every
# HEARTBEAT_INTERVAL_SECONDS (currently 30s); a 90s window forgives
# heartbeats delayed by transient network blips while still catching
# tray-open/no-disc clicks made seconds after the ripper noticed. A reading
# older than this means the ripper stopped beating, and the trigger is
# refused rather than sent to nobody.
_MEDIA_STATUS_FRESHNESS = timedelta(seconds=90)
_MEDIA_STATUS_READY: frozenset[DriveMediaStatus] = frozenset({DriveMediaStatus.LOADED, DriveMediaStatus.UNKNOWN})
_MEDIA_STATUS_DETAIL: dict[DriveMediaStatus, str] = {
    DriveMediaStatus.NO_DISC: "no disc loaded in the drive",
    DriveMediaStatus.TRAY_OPEN: "the drive tray is open; close it before starting a rip",
    DriveMediaStatus.NOT_READY: "the drive is busy or spinning up; try again in a moment",
    DriveMediaStatus.DETACHED: "the drive is detached; reconnect it before starting a rip",
    DriveMediaStatus.UNAVAILABLE: (
        "the drive node exists but could not be opened; check the device cgroup rule and CDROM_GID"
    ),
}


_LIST_JOBS_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "headers": {
            "X-Total-Count": {
                "description": "Number of jobs matching the filters, before limit/offset.",
                "schema": {"type": "integer"},
            }
        }
    }
}


def _job_filters(status_filter: JobStatus | None, drive_id: str | None) -> list[ColumnElement[bool]]:
    """The optional status and drive filters of the job list, in query order."""
    filters: list[ColumnElement[bool]] = []
    if status_filter is not None:
        filters.append(col(Job.status) == status_filter)
    if drive_id is not None:
        filters.append(col(Job.drive_id) == drive_id)
    return filters


async def _total_count(
    session: AsyncSession, jobs: list[Job], filters: list[ColumnElement[bool]], *, limit: int, offset: int
) -> int:
    """The number of jobs matching the filters, before limit/offset."""
    # A short page already pins the total (the poll's common case), so the
    # COUNT round trip runs only for a full page or one past the end.
    if len(jobs) < limit and (jobs or offset == 0):
        return offset + len(jobs)
    return (await session.execute(select(func.count()).select_from(Job).where(*filters))).scalar_one()


@router.get("", response_model=list[JobView], responses=_LIST_JOBS_RESPONSES)
async def list_jobs(
    response: Response,
    _: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    drive_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[JobView]:
    """One page of jobs, newest first with a stable `id` tiebreak so a page
    does not shuffle between polls. The filtered total rides in the
    `X-Total-Count` header; the body stays a plain `JobView[]`."""
    filters = _job_filters(status_filter, drive_id)
    stmt = (
        select(Job).where(*filters).order_by(col(Job.created_at).desc(), col(Job.id).desc()).limit(limit).offset(offset)
    )
    result = await session.execute(stmt)
    jobs = list(result.scalars().all())
    total = await _total_count(session, jobs, filters, limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(total)
    return await job_list_views(session, jobs)


@router.get("/stats", response_model=JobStatsResponse)
async def job_stats(
    _: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
) -> JobStatsResponse:
    """Dashboard aggregates. Full-scan + count in Python (mirrors the
    dispatcher pattern) so the in-memory FakeSession stays sufficient;
    job counts are small at the hobbyist scale this serves."""
    jobs = list((await session.execute(select(Job))).scalars().all())
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for j in jobs:
        skey = j.status.value if hasattr(j.status, "value") else str(j.status)
        by_status[skey] = by_status.get(skey, 0) + 1
        tkey = j.disc_type.value if hasattr(j.disc_type, "value") else str(j.disc_type)
        by_type[tkey] = by_type.get(tkey, 0) + 1
    return JobStatsResponse(total=len(jobs), by_status=by_status, by_type=by_type)


@router.get("/{job_id}", response_model=JobDetailView)
async def get_job_detail(
    job_id: JobIdParam,
    _: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
) -> JobDetailView:
    job = (await session.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    return await job_detail_view(session, job)


@router.post("/{job_id}/abandon", response_model=JobView)
async def abandon_job(
    job_id: JobIdParam,
    req: AbandonJobRequest | None = None,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(get_hub),
) -> Job:
    """Move a non-terminal job to `abandoned` and tell the ripper to clean up.

    Two cases the ripper handles via the `job.abandoned` WS command:
      * AWAITING_USER_ID — the ripper is parked in `_await_resolution`;
        the waiter polls, sees the non-IDENTIFIED status, exits cleanly.
      * RIPPING — the ripper has an active scan/identify/rip pipeline. The
        WS handler cancels the asyncio task, which kills the makemkvcon
        subprocess so file handles release on `/raw/<id>/`.

    `delete_raw` is plumbed in the WS payload because only the ripper has
    `/raw` mounted; doing the rmtree here would silently no-op. Even when there's no active task, the ripper still runs the
    rmtree against any orphaned partial-rip directory.
    """
    job = (await db.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    if job.status not in NON_TERMINAL_JOB_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job already in terminal status {enum_value_str(job.status)}",
        )

    delete_raw = bool(req and req.delete_raw)
    await abandon_job_transition(db, hub, job, delete_raw=delete_raw)
    await db.commit()
    await db.refresh(job)

    logger.info("abandon job_id=%s delete_raw=%s", job.id, delete_raw)
    return job


@router.post("/{job_id}/rip-start-review", response_model=JobView)
async def rip_start_review(
    job_id: JobIdParam,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(get_hub),
) -> Job:
    """Operator Start for a disc held in the timed review gate.

    Transitions AWAITING_REVIEW -> RIPPING here (the backend owns the transition;
    rip-start then tolerates already-RIPPING) and emits the `rip.start` WS command
    so the parked ripper unblocks. Operator-initiated, so JWT-authed on the jobs
    router — NOT the ripper's service-token rip-start path. Pre-flight: at least
    one kept (non-excluded) track, else 422 (don't let it fail deep in the ripper).
    """
    job = (await db.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    if job.status != JobStatus.AWAITING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"rip-start-review only valid for awaiting_review, got {enum_value_str(job.status)}",
        )
    await _start_held_job(db, hub, job)
    await db.refresh(job)
    logger.info("rip-start-review job_id=%s -> ripping", job.id)
    return job


async def _start_held_job(db: AsyncSession, hub: WSHub, job: Job) -> None:
    """AWAITING_REVIEW -> RIPPING, plus the `rip.start` command that unblocks
    the parked ripper. Commits. 422 when every track is excluded."""
    tracks = list((await db.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all())
    if tracks and all(t.excluded for t in tracks):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="at least one track must be kept (not excluded) to start the rip",
        )

    job.status = JobStatus.RIPPING
    job.started_at = datetime.now(timezone.utc)
    db.add(job)
    await db.flush()

    payload = {"job_id": job.id, "drive_id": job.drive_id}
    await hub.emit(
        topic=f"ripper.commands.{job.drive_id}",
        event_type="rip.start",
        payload=payload,
        job_id=job.id,
        session=db,
    )
    await hub.emit(
        topic="ripper.events",
        event_type="rip.started",
        payload=payload,
        job_id=job.id,
        session=db,
    )
    await db.commit()


@router.post("/{job_id}/rip-again", response_model=RipAgainResponse)
async def rip_again(
    job_id: JobIdParam,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(get_hub),
) -> RipAgainResponse:
    """Operator "Rip again" on a ripped job (on_previously_ripped hold/reject).

    If a copy of this disc is held right now (a previously-ripped hold sharing
    a fingerprint with this job, whichever earlier rip it names), start that
    one. Otherwise flag this job so the next identify of the disc skips the
    previously-ripped check once.
    """
    job = (await db.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    if job.status not in POST_RIP_JOB_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"rip-again only valid for a ripped job, got {enum_value_str(job.status)}",
        )
    held = (
        (await db.execute(select(Job).where(col(Job.status) == JobStatus.AWAITING_REVIEW).order_by(col(Job.id))))
        .scalars()
        .all()
    )
    held = [h for h in held if previously_ripped_job_id(h.metadata_json) is not None]
    same_disc: set[str] = set()
    if held:
        fps = {
            (fp.algo, fp.value)
            for fp in (await db.execute(select(DiscFingerprint).where(col(DiscFingerprint.job_id) == job.id)))
            .scalars()
            .all()
        }
        if fps:
            held_fps = (
                (
                    await db.execute(
                        select(DiscFingerprint).where(col(DiscFingerprint.job_id).in_(tuple(h.id for h in held)))
                    )
                )
                .scalars()
                .all()
            )
            same_disc = {fp.job_id for fp in held_fps if (fp.algo, fp.value) in fps}
    copy = next(
        (h for h in held if h.id in same_disc or previously_ripped_job_id(h.metadata_json) == job.id),
        None,
    )
    if copy is not None:
        await _start_held_job(db, hub, copy)
        logger.info("rip-again job_id=%s: started held copy job_id=%s", job.id, copy.id)
        return RipAgainResponse(started_job_id=copy.id)
    job.metadata_json = with_flags(job.metadata_json, rerip_allowed=True)
    db.add(job)
    await db.commit()
    logger.info("rip-again job_id=%s: next identify of this disc may rip it", job.id)
    return RipAgainResponse(armed=True)


@router.post("/{job_id}/review-pause", response_model=JobView)
async def review_pause(
    job_id: JobIdParam,
    paused: bool = True,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(get_hub),
) -> Job:
    """Pause/resume ONE held disc's review countdown (per-job pause).

    `?paused=true` freezes this disc's auto-start countdown (waits indefinitely
    for Start) while other discs keep counting; `?paused=false` resumes with a
    FRESH countdown (new wait_start_time) so it doesn't auto-rip instantly on a
    long-paused disc. Only valid for AWAITING_REVIEW. Emits a WS command so the
    parked ripper re-evaluates the countdown on its next poll.
    """
    job = (await db.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    if job.status != JobStatus.AWAITING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"review-pause only valid for awaiting_review, got {enum_value_str(job.status)}",
        )
    if previously_ripped_job_id(job.metadata_json) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this disc was ripped before; it has no countdown to pause",
        )
    if identity_suggestion_of(job.metadata_json) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="this disc is waiting for you to confirm its identity; it has no countdown to pause",
        )
    job.manual_pause = paused
    if not paused:
        job.wait_start_time = datetime.now(timezone.utc)  # fresh countdown on resume
    db.add(job)
    await db.flush()
    await hub.emit(
        topic=f"ripper.commands.{job.drive_id}",
        event_type="review.pause",
        payload={"job_id": job.id, "drive_id": job.drive_id, "paused": paused},
        job_id=job.id,
        session=db,
    )
    await db.commit()
    await db.refresh(job)
    logger.info("review-pause job_id=%s paused=%s", job.id, paused)
    return job


async def _resolve_media_outputs(db: AsyncSession, job_id: str) -> list[Path]:
    """Return absolute paths of every finished transcode output recorded
    against this job's tracks. `output_path` is relative; join to MEDIA_ROOT.

    Only DONE tasks count: `output_path` is recorded at fan-out, before the
    output lands, so a queued, running, or failed task's path can name a file
    or folder this job never wrote. A disc backup whose move was refused
    because the destination already existed ends FAILED naming that folder,
    which belongs to another job or the user."""
    media_root = Path(settings.MEDIA_ROOT)
    rows = (
        await db.execute(
            select(TranscodeTask.output_path)
            .join(Track, col(TranscodeTask.source_track_id) == col(Track.id))
            .where(col(Track.job_id) == job_id)
            .where(col(TranscodeTask.status) == TranscodeTaskStatus.DONE)
            .where(col(TranscodeTask.output_path).is_not(None))
        )
    ).all()
    return [media_root / r[0] for r in rows]


def _delete_per_job_log(job_id: str) -> None:
    """Best-effort removal of `/logs/jobs/{job_id}.log`. Logged-but-swallowed
    on any error — DB delete already succeeded by the time we reach here,
    so a stale log file is far better than aborting the user's delete."""
    path = per_job_log_path(job_id)
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("per-job log delete failed job_id=%s path=%s err=%s", job_id, path, exc)


def _bulk_delete_status(req: BulkDeleteJobsRequest) -> JobStatus | None:
    """The status filter of a bulk delete; 400 when it is not a JobStatus."""
    if not req.status:
        return None
    try:
        return JobStatus(req.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid status: {req.status}") from exc


def _bulk_delete_candidates(
    rows: Sequence[Job], req: BulkDeleteJobsRequest, target_status: JobStatus | None
) -> list[Job]:
    """The jobs a bulk delete targets: `job_ids` wins over `status`, else all."""
    if req.job_ids:
        wanted = set(req.job_ids)
        return [j for j in rows if j.id in wanted]
    if target_status is not None:
        return [j for j in rows if j.status == target_status]
    return list(rows)


async def _clean_up_job_files(db: AsyncSession, job_id: str, *, raw_root: Path, media_root: Path) -> dict[str, int]:
    """Delete a job's raw dir and recorded media outputs. Returns the counters."""
    media_outputs = await _resolve_media_outputs(db, job_id)
    return delete_job_files(job_id, media_outputs, raw_root=raw_root, media_root=media_root)


def _log_delete_summary(job_id: str, counters: dict[str, int] | None) -> None:
    """Log the one-line summary of a single job delete."""
    if counters is None:
        logger.info("delete job_id=%s delete_raw=False", job_id)
        return
    logger.info(
        "delete job_id=%s delete_raw=True raw_dir_removed=%d media_files_removed=%d media_dirs_pruned=%d",
        job_id,
        counters["raw_dir_removed"],
        counters["media_files_removed"],
        counters["media_dirs_pruned"],
    )


def _log_bulk_delete_summary(deleted: int, skipped: int, totals: dict[str, int] | None) -> None:
    """Log the one-line summary of a bulk delete."""
    if totals is None:
        logger.info("delete-all jobs deleted=%d skipped=%d delete_raw=False", deleted, skipped)
        return
    logger.info(
        "delete-all jobs deleted=%d skipped=%d delete_raw=True raw_dirs=%d media_files=%d media_dirs_pruned=%d",
        deleted,
        skipped,
        totals["raw_dir_removed"],
        totals["media_files_removed"],
        totals["media_dirs_pruned"],
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: JobIdParam,
    delete_raw: bool = Query(default=False),
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> None:
    """Hard-delete a Job. Tracks, fingerprints, session_applications,
    transcode_tasks, and events cascade via Postgres FK ondelete=CASCADE.

    Refuses non-terminal jobs (CREATED / AWAITING_USER_ID / IDENTIFIED /
    RIPPING) — caller must `POST /abandon` first if they want a job in
    flight gone. This keeps the active-rip cancel logic in one place.

    `delete_raw=true` also unlinks every transcode output recorded for the
    job and rmtrees `/raw/{job_id}/`. Backend mounts both bind paths
    directly, so the cleanup runs synchronously here — no WS roundtrip,
    no dependency on the ripper container being up. Per-file unlink for
    media (sibling re-rips share the `media/<Title>/` parent dir); empty
    parents are pruned after the unlink phase.
    """
    job = (await db.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    if job.status not in TERMINAL_JOB_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job in non-terminal status {enum_value_str(job.status)}; abandon it first",
        )

    counters: dict[str, int] | None = None
    if delete_raw:
        counters = await _clean_up_job_files(
            db, job.id, raw_root=Path(settings.RAW_ROOT), media_root=Path(settings.MEDIA_ROOT)
        )

    await db.delete(job)
    await db.commit()
    _delete_per_job_log(job_id)
    _log_delete_summary(job_id, counters)


@router.delete("", response_model=BulkDeleteJobsResponse)
async def delete_all_jobs(
    delete_raw: bool = Query(default=False),
    req: BulkDeleteJobsRequest | None = Body(default=None),
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> BulkDeleteJobsResponse:
    """Hard-delete terminal jobs. An optional body filters the set:
    `job_ids` (only those), `status` (only that JobStatus), or neither
    (all terminal jobs — legacy). `job_ids` wins over `status`. Non-terminal
    jobs are always skipped and reported in `skipped_non_terminal`.

    `delete_raw=true` runs the filesystem cleanup (raw rmtree + media file
    unlink + empty-parent prune) for each deleted job. Cleanups are
    independent — a failure on one job is logged and the next continues.
    """
    req = req or BulkDeleteJobsRequest()

    target_status = _bulk_delete_status(req)

    rows = (await db.execute(select(Job))).scalars().all()
    candidates = _bulk_delete_candidates(rows, req, target_status)

    raw_root = Path(settings.RAW_ROOT)
    media_root = Path(settings.MEDIA_ROOT)
    deleted_ids: list[str] = []
    skipped: list[str] = []
    totals = {"raw_dir_removed": 0, "media_files_removed": 0, "media_dirs_pruned": 0}
    for job in candidates:
        if job.status not in TERMINAL_JOB_STATUSES:
            skipped.append(job.id)
            continue
        if delete_raw:
            counters = await _clean_up_job_files(db, job.id, raw_root=raw_root, media_root=media_root)
            for k, v in counters.items():
                totals[k] += v
        await db.delete(job)
        deleted_ids.append(job.id)

    await db.commit()
    for jid in deleted_ids:
        _delete_per_job_log(jid)
    _log_bulk_delete_summary(len(deleted_ids), len(skipped), totals if delete_raw else None)
    return BulkDeleteJobsResponse(deleted_ids=deleted_ids, skipped_non_terminal=skipped)


@router.post("/manual", response_model=ManualTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
async def manual_trigger(
    req: ManualTriggerRequest,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(get_hub),
) -> ManualTriggerResponse:
    """Kick the ripper to run a job on a drive that already has a disc in
    the tray. The ripper handles the WS command, scans the disc, and
    threads `pending_session_id` through identify so the resulting Job's
    `pending_session_id` column carries it. `rip-complete` then auto-applies
    that session.
    """
    drive = (await db.execute(select(Drive).where(col(Drive.id) == req.drive_id))).scalar_one_or_none()
    if drive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {req.drive_id}")

    cfg = (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is not None and cfg.ripping_paused:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ripping is paused; no new jobs accepted",
        )

    # The ripper drops a trigger while it owns any job, and no ripper acts on
    # one for a detached drive or after it stopped beating. Refuse those here,
    # in the DriveCard's order and wording, so the click gets a reason
    # it can show instead of a 202 nothing follows. The card gates the first
    # two itself; heartbeat age it cannot judge against the browser clock.
    live = (
        (
            await db.execute(
                select(Job)
                .where(col(Job.drive_id) == req.drive_id)
                .where(col(Job.status).in_(NON_TERMINAL_JOB_STATUSES))
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if live is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"the drive already has a job in progress ({enum_value_str(live.status)})",
        )
    if not drive.present:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="the drive is not connected")
    if drive.media_status_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="the drive's ripper is offline (no heartbeat yet)",
        )
    age = datetime.now(timezone.utc) - drive.media_status_at
    if age >= _MEDIA_STATUS_FRESHNESS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"the drive's ripper is offline (last heartbeat {int(age.total_seconds())}s ago)",
        )

    # Fast-fail when the user clicks Start without loading a disc. The
    # reading is from the heartbeat that just passed the freshness check.
    if drive.media_status is not None and drive.media_status not in _MEDIA_STATUS_READY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_MEDIA_STATUS_DETAIL[drive.media_status],
        )

    if req.session_id is not None:
        sess = (await db.execute(select(Session).where(col(Session.id) == req.session_id))).scalar_one_or_none()
        if sess is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unknown session_id: {req.session_id}",
            )

    await hub.emit(
        topic=f"ripper.commands.{req.drive_id}",
        event_type="manual.trigger",
        payload={"session_id": req.session_id},
        session=db,
    )
    await db.commit()
    logger.info("manual trigger drive_id=%s session_id=%s", req.drive_id, req.session_id)
    return ManualTriggerResponse(drive_id=req.drive_id, session_id=req.session_id)


@router.patch("/{job_id}", response_model=JobView)
async def update_job(
    job_id: JobIdParam,
    req: JobUpdateRequest,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(get_hub),
    stage_runner: EpisodeStageRunner | None = Depends(get_stage_runner),
) -> Job:
    """Edit user-controlled fields on a Job + optional per-track operator edits.
    Job title/year stay behind identify/resolve; track `status` stays ripper-owned
    (not in TrackEditRequest)."""
    # Lock the job row (then its tracks) so a concurrent identity write
    # (the episode stage's apply, /identity/match) serializes with this one.
    job = (await db.execute(select(Job).where(col(Job.id) == job_id).with_for_update())).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    await apply_manual_edits(db, job, req, hub=hub, stage_runner=stage_runner)
    return job


@router.post("/{job_id}/resolve", response_model=ResolveResponse)
async def resolve(
    job_id: JobIdParam,
    req: ResolveRequest,
    _: User = Depends(require_writer),
    session: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(get_hub),
    stage_runner: EpisodeStageRunner | None = Depends(get_stage_runner),
) -> ResolveResponse:
    # Lock the job row before the identity write (lock order: job, then tracks).
    job = (await session.execute(select(Job).where(col(Job.id) == job_id).with_for_update())).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    if job.status not in RESOLVABLE_JOB_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job {job_id} is in status {enum_value_str(job.status)}, not in an identify-resolvable status",
        )
    return await resolve_identity(session, job, req, hub=hub, stage_runner=stage_runner)


@router.post("/{job_id}/identity/accept", response_model=ResolveResponse)
async def accept_identity_suggestion(
    job_id: JobIdParam,
    _: User = Depends(require_writer),
    session: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(get_hub),
    stage_runner: EpisodeStageRunner | None = Depends(get_stage_runner),
) -> ResolveResponse:
    """Confirm the confident match identify held because the media type's
    auto-apply switch was off.

    Applies the stored hit exactly as identify would have, then hands the
    job to the resolve path (provenance, fan-out, `identify.resolved`, the
    episode stage). The status is settled first: a held disc is released to
    rip when the review gate is off, or gets the gate's countdown when it is
    on; a pause keeps it held with no countdown until un-pause stamps one;
    a ripped placeholder follows resolve's promote rule. A job also held as
    previously ripped keeps that hold untouched (status, no countdown).
    """
    job = (await session.execute(select(Job).where(col(Job.id) == job_id).with_for_update())).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    suggestion = identity_suggestion_of(job.metadata_json)
    if suggestion is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"job {job_id} has no identity suggestion to accept"
        )
    if job.status not in RESOLVABLE_JOB_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job {job_id} is in status {job.status.value}, not in an identify-resolvable status",
        )
    cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    before_identity = identity_snapshot(job)
    now = datetime.now(timezone.utc)
    result = suggestion_to_result(suggestion)
    job.metadata_json = without_identity_suggestion(job.metadata_json)
    apply_identity_result(job, result, now=now)
    if previously_ripped_job_id(job.metadata_json) is not None:
        # The previously-ripped hold still wins: identifying the disc neither
        # releases it nor starts a countdown; Rip again / Discard leave it.
        pass
    elif job.status == JobStatus.AWAITING_REVIEW:
        paused = cfg is not None and bool(cfg.ripping_paused)
        if cfg is not None and cfg.hold_for_review:
            job.wait_start_time = None if paused else now
        elif paused:
            job.wait_start_time = None
        else:
            job.status = JobStatus.IDENTIFIED
    req = ResolveRequest(
        title=result.title, year=result.year, media_type=MediaType(result.kind), external_ids=external_ids_of(result)
    )
    logger.info("accept job_id=%s: %s suggestion %r applied -> %s", job.id, result.kind, result.title, job.status.value)
    return await resolve_identity(
        session, job, req, hub=hub, stage_runner=stage_runner, before_identity=before_identity
    )


@router.post("/{job_id}/transcode", response_model=ApplySessionResponse)
async def apply_session(
    job_id: JobIdParam,
    req: ApplySessionRequest,
    user: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(get_hub),
) -> ApplySessionResponse:
    job = (await db.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")

    try:
        outcome = await apply_session_internal(
            db,
            job=job,
            session_id=req.session_id,
            overwrite=req.overwrite,
            created_by_user_id=user.id,
            source="manual",
            hub=hub,
        )
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown session_id: {req.session_id}",
        ) from exc
    except TemplateValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="concurrent application detected; another session already claims one of these paths",
        ) from exc

    if outcome.skipped_reason == "collisions":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "output_path collisions detected",
                "collisions": [c.model_dump() for c in outcome.collisions],
            },
        )

    if outcome.skipped_reason == "media_mismatch":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=outcome.error_detail or "session media type is not compatible with job media type",
        )

    if outcome.skipped_reason == "transcode_disabled":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=outcome.error_detail or "transcoding is disabled",
        )

    if outcome.skipped_reason == "encoder_unavailable":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=outcome.error_detail or "no enabled device has verified this encoder",
        )

    assert outcome.application is not None
    return ApplySessionResponse(
        session_application=SessionApplicationView.model_validate(outcome.application),
        tasks=[TranscodeTaskView.model_validate(t) for t in outcome.tasks],
        collisions=[],
        idempotent=outcome.idempotent,
    )
