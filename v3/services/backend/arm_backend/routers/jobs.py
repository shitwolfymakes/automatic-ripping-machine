import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.auto_session import SessionNotFoundError, apply_session_internal
from arm_backend.db import get_session
from arm_backend.path_template import TemplateValidationError
from arm_backend.ws import WSHub
from arm_common import (
    Drive,
    Job,
    JobStatus,
    Session,
    User,
)
from arm_common.models import Track
from arm_common.schemas import (
    AbandonJobRequest,
    ApplySessionRequest,
    ApplySessionResponse,
    JobDetailView,
    JobView,
    ManualTriggerRequest,
    ManualTriggerResponse,
    ResolveRequest,
    SessionApplicationView,
    TrackView,
    TranscodeTaskView,
)

logger = logging.getLogger("arm_backend.routers.jobs")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _get_hub(request: Request) -> WSHub:
    hub: WSHub = request.app.state.ws_hub
    return hub


@router.get("", response_model=list[JobView])
async def list_jobs(
    _: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    drive_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[Job]:
    stmt = select(Job).order_by(col(Job.created_at).desc()).limit(limit).offset(offset)
    if status_filter is not None:
        stmt = stmt.where(col(Job.status) == status_filter)
    if drive_id is not None:
        stmt = stmt.where(col(Job.drive_id) == drive_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


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
    return JobDetailView(
        job=JobView.model_validate(job),
        tracks=[TrackView.model_validate(t) for t in tracks],
    )


_NON_TERMINAL_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.CREATED,
        JobStatus.AWAITING_USER_ID,
        JobStatus.IDENTIFIED,
        JobStatus.RIPPING,
    }
)

# Backend mounts the same `./raw` host volume as the ripper at `/raw`, so
# we can wipe a job's partial-rip directory directly. Path is computed
# rather than constant so tests can monkeypatch.
RAW_ROOT = Path("/raw")


@router.post("/{job_id}/abandon", response_model=JobView)
async def abandon_job(
    job_id: str,
    req: AbandonJobRequest | None = None,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(_get_hub),
) -> Job:
    """Move a non-terminal job to `abandoned`. Used to clear a job parked at
    `awaiting_user_id` (or any other in-flight state) so the drive's
    single-flight lock releases and a fresh manual rip can run.

    Wakes any ripper waiter (`_await_resolution`) by emitting
    `identify.resolved` on the drive's commands topic; the waiter polls,
    sees the non-IDENTIFIED status, and exits the pipeline cleanly.
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

    payload = {"job_id": job.id, "drive_id": job.drive_id, "status": job.status.value}
    # Wake any in-process waiter (handle_disc_inserted parked at
    # _await_resolution); reuse the existing event type since the waiter's
    # decision branches on the post-poll job status, not the event name.
    await hub.emit(
        topic=f"ripper.commands.{job.drive_id}",
        event_type="identify.resolved",
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

    delete_raw = bool(req and req.delete_raw)
    if delete_raw:
        target = RAW_ROOT / job.id
        try:
            shutil.rmtree(target, ignore_errors=False)
            logger.info("abandon job_id=%s deleted raw dir=%s", job.id, target)
        except FileNotFoundError:
            logger.info("abandon job_id=%s raw dir already absent (path=%s)", job.id, target)
        except OSError as exc:
            # Status change already committed; surface the cleanup miss but
            # don't roll the job back to a non-terminal state.
            logger.warning("abandon job_id=%s raw-dir cleanup failed (path=%s): %s", job.id, target, exc)

    logger.info("abandon job_id=%s delete_raw=%s", job.id, delete_raw)
    return job


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
