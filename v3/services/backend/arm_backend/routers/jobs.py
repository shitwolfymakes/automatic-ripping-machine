import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.auto_session import SessionNotFoundError, apply_session_internal
from arm_backend.db import get_session
from arm_backend.path_template import TemplateValidationError
from arm_backend.routers.logs import per_job_log_path
from arm_backend.ws import WSHub
from arm_common import (
    DiscFingerprint,
    Drive,
    DriveMediaStatus,
    Job,
    JobStatus,
    Session,
    TrackStatus,
    User,
)
from arm_common.models import Track
from arm_common.schemas import (
    AbandonJobRequest,
    ApplySessionRequest,
    ApplySessionResponse,
    BulkDeleteJobsResponse,
    DiscFingerprintView,
    JobDetailView,
    JobUpdateRequest,
    JobView,
    ManualTriggerRequest,
    ManualTriggerResponse,
    ResolveRequest,
    RipProgressSummary,
    SessionApplicationView,
    TrackView,
    TranscodeTaskView,
)

logger = logging.getLogger("arm_backend.routers.jobs")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _get_hub(request: Request) -> WSHub:
    hub: WSHub = request.app.state.ws_hub
    return hub


# Manual-trigger pre-check (drive media status). The ripper posts every
# HEARTBEAT_INTERVAL_SECONDS (currently 30s); a 90s window forgives
# heartbeats delayed by transient network blips while still catching
# tray-open/no-disc clicks made seconds after the ripper noticed.
_MEDIA_STATUS_FRESHNESS = timedelta(seconds=90)
_MEDIA_STATUS_READY: frozenset[DriveMediaStatus] = frozenset({DriveMediaStatus.LOADED, DriveMediaStatus.UNKNOWN})
_MEDIA_STATUS_DETAIL: dict[DriveMediaStatus, str] = {
    DriveMediaStatus.NO_DISC: "no disc loaded in the drive",
    DriveMediaStatus.TRAY_OPEN: "drive tray is open — close it before starting a rip",
    DriveMediaStatus.NOT_READY: "drive is busy / spinning up — try again in a moment",
    DriveMediaStatus.UNAVAILABLE: "drive device node is gone — check the host /dev mount",
}


def _summarize_rip_progress(tracks: list[Track]) -> RipProgressSummary:
    """Aggregate `tracks` (one job's worth) into a `RipProgressSummary`.

    `current_track_index` is the 1-based ordinal among tracks sorted by
    `Track.index` of the row in `IN_PROGRESS`. The dispatcher transitions
    one track at a time, so at most one is `IN_PROGRESS` per job; if more
    than one ever appeared (e.g. mid-rewrite of the dispatcher) we'd pick
    the lowest-index one as a sane default.
    """
    sorted_tracks = sorted(tracks, key=lambda t: t.index)
    done = sum(1 for t in sorted_tracks if t.status == TrackStatus.DONE)
    failed = sum(1 for t in sorted_tracks if t.status == TrackStatus.FAILED)
    current_track_id: str | None = None
    current_track_index: int | None = None
    for ordinal, t in enumerate(sorted_tracks, start=1):
        if t.status == TrackStatus.IN_PROGRESS:
            current_track_id = t.id
            current_track_index = ordinal
            break
    return RipProgressSummary(
        tracks_total=len(sorted_tracks),
        tracks_done=done,
        tracks_failed=failed,
        current_track_id=current_track_id,
        current_track_index=current_track_index,
    )


@router.get("", response_model=list[JobView])
async def list_jobs(
    _: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    drive_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[JobView]:
    stmt = select(Job).order_by(col(Job.created_at).desc()).limit(limit).offset(offset)
    if status_filter is not None:
        stmt = stmt.where(col(Job.status) == status_filter)
    if drive_id is not None:
        stmt = stmt.where(col(Job.drive_id) == drive_id)
    result = await session.execute(stmt)
    jobs = list(result.scalars().all())

    # One batched track lookup keyed on the ripping-job IDs feeds the
    # dashboard's "Track N of M" line without an N+1 fetch. Skipped
    # entirely when no job in the page is ripping (which is the common
    # case on the recent-jobs slice).
    ripping_ids = [j.id for j in jobs if j.status == JobStatus.RIPPING]
    tracks_by_job: dict[str, list[Track]] = {}
    if ripping_ids:
        track_rows = (
            (
                await session.execute(
                    select(Track)
                    .where(col(Track.job_id).in_(ripping_ids))
                    .order_by(col(Track.job_id), col(Track.index))
                )
            )
            .scalars()
            .all()
        )
        for tr in track_rows:
            tracks_by_job.setdefault(tr.job_id, []).append(tr)

    views: list[JobView] = []
    for j in jobs:
        view = JobView.model_validate(j)
        if j.status == JobStatus.RIPPING:
            view.rip_progress = _summarize_rip_progress(tracks_by_job.get(j.id, []))
        views.append(view)
    return views


@router.get("/{job_id}", response_model=JobDetailView)
async def get_job_detail(
    job_id: str,
    _: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
) -> JobDetailView:
    job = (await session.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    tracks = (
        (await session.execute(select(Track).where(col(Track.job_id) == job_id).order_by(col(Track.index))))
        .scalars()
        .all()
    )
    fingerprints = (
        (
            await session.execute(
                select(DiscFingerprint).where(col(DiscFingerprint.job_id) == job_id).order_by(col(DiscFingerprint.algo))
            )
        )
        .scalars()
        .all()
    )
    return JobDetailView(
        job=JobView.model_validate(job),
        tracks=[TrackView.model_validate(t) for t in tracks],
        fingerprints=[DiscFingerprintView.model_validate(fp) for fp in fingerprints],
    )


_NON_TERMINAL_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.CREATED,
        JobStatus.AWAITING_USER_ID,
        JobStatus.IDENTIFIED,
        JobStatus.RIPPING,
    }
)


@router.post("/{job_id}/abandon", response_model=JobView)
async def abandon_job(
    job_id: str,
    req: AbandonJobRequest | None = None,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(_get_hub),
) -> Job:
    """Move a non-terminal job to `abandoned` and tell the ripper to clean up.

    Two cases the ripper handles via the `job.abandoned` WS command:
      * AWAITING_USER_ID — the ripper is parked in `_await_resolution`;
        the waiter polls, sees the non-IDENTIFIED status, exits cleanly.
      * RIPPING — the ripper has an active scan/identify/rip pipeline. The
        WS handler cancels the asyncio task, which kills the makemkvcon
        subprocess so file handles release on `/raw/<id>/`.

    `delete_raw` is plumbed in the WS payload because only the ripper has
    `/raw` mounted; doing the rmtree here would silently no-op (and used to,
    pre-fix). Even when there's no active task, the ripper still runs the
    rmtree against any orphaned partial-rip directory.
    """
    job = (await db.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    if job.status not in _NON_TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job already in terminal status {job.status.value}",
        )

    job.status = JobStatus.ABANDONED
    db.add(job)
    await db.flush()

    delete_raw = bool(req and req.delete_raw)
    payload = {
        "job_id": job.id,
        "drive_id": job.drive_id,
        "status": job.status.value,
        "delete_raw": delete_raw,
    }
    # Tell the ripper: cancel any active rip on this drive matching the
    # job, optionally rmtree /raw/<id>/. Also wakes a parked
    # `_await_resolution` waiter (handler treats the message as a generic
    # "drive state changed; re-poll" signal).
    await hub.emit(
        topic=f"ripper.commands.{job.drive_id}",
        event_type="job.abandoned",
        payload=payload,
        job_id=job.id,
        session=db,
    )
    await hub.emit(
        topic="ripper.events",
        event_type="rip.abandoned",
        payload=payload,
        job_id=job.id,
        session=db,
    )
    await db.commit()
    await db.refresh(job)

    logger.info("abandon job_id=%s delete_raw=%s", job.id, delete_raw)
    return job


_TERMINAL_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.RIPPED,
        JobStatus.RIPPED_PARTIAL,
        JobStatus.ABANDONED,
        JobStatus.FAILED,
    }
)


async def _emit_delete_raw(hub: WSHub, db: AsyncSession, job: Job) -> None:
    """Tell the ripper that owns this job's drive to rmtree `/raw/{id}/`.
    Backend has no `/raw` mount; the WS hop is the only way to reach the
    files. If the ripper for that drive is offline, the rmtree silently
    no-ops (subscriber list is empty) — acceptable: leftover raw files
    from a destroyed drive aren't taking up space on a live drive."""
    payload = {"job_id": job.id, "drive_id": job.drive_id, "delete_raw": True}
    await hub.emit(
        topic=f"ripper.commands.{job.drive_id}",
        event_type="job.deleted",
        payload=payload,
        job_id=job.id,
        session=db,
    )


def _delete_per_job_log(job_id: str) -> None:
    """Best-effort removal of `/logs/jobs/{job_id}.log`. Logged-but-swallowed
    on any error — DB delete already succeeded by the time we reach here,
    so a stale log file is far better than aborting the user's delete."""
    path = per_job_log_path(job_id)
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("per-job log delete failed job_id=%s path=%s err=%s", job_id, path, exc)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    delete_raw: bool = Query(default=False),
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(_get_hub),
) -> None:
    """Hard-delete a Job. Tracks, fingerprints, session_applications,
    transcode_tasks, and events cascade via Postgres FK ondelete=CASCADE.

    Refuses non-terminal jobs (CREATED / AWAITING_USER_ID / IDENTIFIED /
    RIPPING) — caller must `POST /abandon` first if they want a job in
    flight gone. This keeps the active-rip cancel logic in one place.

    `delete_raw=true` also wipes `/raw/{job_id}/` on the ripper that
    owns the drive (sent over WS — only the ripper has `/raw` mounted).
    The DB delete proceeds regardless of whether the rmtree succeeds.
    """
    job = (await db.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    if job.status not in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job in non-terminal status {job.status.value}; abandon it first",
        )

    if delete_raw:
        await _emit_delete_raw(hub, db, job)

    await db.delete(job)
    await db.commit()
    _delete_per_job_log(job_id)
    logger.info("delete job_id=%s delete_raw=%s", job_id, delete_raw)


@router.delete("", response_model=BulkDeleteJobsResponse)
async def delete_all_jobs(
    delete_raw: bool = Query(default=False),
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(_get_hub),
) -> BulkDeleteJobsResponse:
    """Hard-delete every job in a terminal status. Non-terminal jobs are
    skipped and reported in `skipped_non_terminal` so the caller can
    abandon-then-retry them.

    `delete_raw=true` emits one `job.deleted` WS command per job to its
    drive's ripper before the row is removed. Each rmtree is independent;
    a failure on one ripper doesn't block deletes for the others.
    """
    rows = (await db.execute(select(Job))).scalars().all()

    deleted_ids: list[str] = []
    skipped: list[str] = []
    for job in rows:
        if job.status not in _TERMINAL_STATUSES:
            skipped.append(job.id)
            continue
        if delete_raw:
            await _emit_delete_raw(hub, db, job)
        await db.delete(job)
        deleted_ids.append(job.id)

    await db.commit()
    for jid in deleted_ids:
        _delete_per_job_log(jid)
    logger.info("delete-all jobs deleted=%d skipped=%d delete_raw=%s", len(deleted_ids), len(skipped), delete_raw)
    return BulkDeleteJobsResponse(deleted_ids=deleted_ids, skipped_non_terminal=skipped)


@router.post("/manual", response_model=ManualTriggerResponse, status_code=status.HTTP_202_ACCEPTED)
async def manual_trigger(
    req: ManualTriggerRequest,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(_get_hub),
) -> ManualTriggerResponse:
    """Kick the ripper to run a job on a drive that already has a disc in
    the tray. The ripper handles the WS command, scans the disc, and
    threads `pending_session_id` through identify so the resulting Job's
    metadata carries it. `rip-complete` then auto-applies that session.
    """
    drive = (await db.execute(select(Drive).where(col(Drive.id) == req.drive_id))).scalar_one_or_none()
    if drive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {req.drive_id}")

    in_flight = (
        await db.execute(
            select(Job).where(col(Job.drive_id) == req.drive_id).where(col(Job.status) == JobStatus.RIPPING)
        )
    ).first()
    if in_flight is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"drive {req.drive_id} already has an in-flight RIPPING job",
        )

    # Fast-fail when the user clicks Start without loading a disc.
    # Heartbeat-fed; we only honour readings that arrived within the
    # freshness window (a stale row is equivalent to "we don't know" —
    # let the request through and let identify do the talking).
    if drive.media_status_at is not None and drive.media_status is not None:
        age = datetime.now(timezone.utc) - drive.media_status_at
        if age < _MEDIA_STATUS_FRESHNESS and drive.media_status not in _MEDIA_STATUS_READY:
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
    job_id: str,
    req: JobUpdateRequest,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> Job:
    """Edit user-controlled fields on a Job. Currently `poster_url_manual`
    only — title/year are owned by the identify/resolve flow.
    """
    job = (await db.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")

    fields = req.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(job, key, value)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


@router.post("/{job_id}/resolve", response_model=JobView)
async def resolve(
    job_id: str,
    req: ResolveRequest,
    _: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(_get_hub),
) -> Job:
    job = (await session.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    if job.status != JobStatus.AWAITING_USER_ID:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job {job_id} is in status {job.status.value}, not awaiting_user_id",
        )

    # Preserve the persisted scan_result so rip-start can still find it after resolve overwrites metadata.
    preserved_scan = (job.metadata_json or {}).get("scan_result")
    new_metadata = dict(req.metadata)
    if preserved_scan is not None and "scan_result" not in new_metadata:
        new_metadata["scan_result"] = preserved_scan

    job.title = req.title
    job.year = req.year
    job.metadata_json = new_metadata
    job.status = JobStatus.IDENTIFIED
    session.add(job)
    await session.commit()
    await session.refresh(job)

    logger.info("resolve job_id=%s -> identified title=%s", job.id, job.title)

    payload = {
        "job_id": job.id,
        "drive_id": job.drive_id,
        "title": job.title,
        "year": job.year,
    }
    await hub.emit(
        topic=f"ripper.commands.{job.drive_id}",
        event_type="identify.resolved",
        payload=payload,
        job_id=job.id,
        session=session,
    )
    await hub.emit(
        topic="ripper.events",
        event_type="rip.identify_resolved",
        payload=payload,
        job_id=job.id,
        session=session,
    )
    await session.commit()

    return job


@router.post("/{job_id}/transcode", response_model=ApplySessionResponse)
async def apply_session(
    job_id: str,
    req: ApplySessionRequest,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(_get_hub),
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
            created_by_user_id=None,
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

    assert outcome.application is not None
    return ApplySessionResponse(
        session_application=SessionApplicationView.model_validate(outcome.application),
        tasks=[TranscodeTaskView.model_validate(t) for t in outcome.tasks],
        collisions=[],
        idempotent=outcome.idempotent,
    )
