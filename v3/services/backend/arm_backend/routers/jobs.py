import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.config import settings
from arm_backend.db import get_session
from arm_backend.path_template import TemplateValidationError
from arm_backend.transcode_apply import compute_outputs, find_collisions
from arm_backend.ws import WSHub
from arm_common import (
    Job,
    JobStatus,
    RipPreset,
    Session,
    SessionApplication,
    SessionApplicationStatus,
    TranscodePreset,
    TranscodeTask,
    TranscodeTaskStatus,
    User,
)
from arm_common.models import Track
from arm_common.schemas import (
    ApplySessionRequest,
    ApplySessionResponse,
    JobDetailView,
    JobView,
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


_APPLY_OK_STATUSES: frozenset[JobStatus] = frozenset({JobStatus.IDENTIFIED, JobStatus.RIPPED, JobStatus.RIPPED_PARTIAL})


async def _load_tasks(db: AsyncSession, session_application_id: str) -> list[TranscodeTask]:
    rows = (
        (
            await db.execute(
                select(TranscodeTask)
                .where(col(TranscodeTask.session_application_id) == session_application_id)
                .order_by(col(TranscodeTask.created_at).asc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


@router.post("/{job_id}/transcode", response_model=ApplySessionResponse)
async def apply_session(
    job_id: str,
    req: ApplySessionRequest,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> ApplySessionResponse:
    job = (await db.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")

    sess = (await db.execute(select(Session).where(col(Session.id) == req.session_id))).scalar_one_or_none()
    if sess is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown session_id: {req.session_id}",
        )

    # Idempotency: same (session, job) → return the existing application.
    existing = (
        await db.execute(
            select(SessionApplication)
            .where(col(SessionApplication.session_id) == req.session_id)
            .where(col(SessionApplication.job_id) == job_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        tasks = await _load_tasks(db, existing.id)
        return ApplySessionResponse(
            session_application=SessionApplicationView.model_validate(existing),
            tasks=[TranscodeTaskView.model_validate(t) for t in tasks],
            collisions=[],
            idempotent=True,
        )

    # `awaiting_user_id` → park as `waiting_identify` with no tasks.
    if job.status == JobStatus.AWAITING_USER_ID:
        application = SessionApplication(
            session_id=req.session_id,
            job_id=job_id,
            status=SessionApplicationStatus.WAITING_IDENTIFY,
            overwrite=False,
            created_by_user_id=None,
        )
        db.add(application)
        await db.commit()
        await db.refresh(application)
        return ApplySessionResponse(
            session_application=SessionApplicationView.model_validate(application),
            tasks=[],
            collisions=[],
            idempotent=False,
        )

    if job.status not in _APPLY_OK_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job is in status {job.status.value}; cannot apply a session",
        )

    rip_preset = (
        await db.execute(select(RipPreset).where(col(RipPreset.id) == sess.rip_preset_id))
    ).scalar_one_or_none()
    if rip_preset is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"session references missing rip_preset_id={sess.rip_preset_id}",
        )
    transcode_preset: TranscodePreset | None = None
    if sess.transcode_preset_id is not None:
        transcode_preset = (
            await db.execute(select(TranscodePreset).where(col(TranscodePreset.id) == sess.transcode_preset_id))
        ).scalar_one_or_none()
        if transcode_preset is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"session references missing transcode_preset_id={sess.transcode_preset_id}",
            )

    tracks = list(
        (await db.execute(select(Track).where(col(Track.job_id) == job_id).order_by(col(Track.index)))).scalars().all()
    )

    try:
        resolved = compute_outputs(job, tracks, sess, transcode_preset)
    except TemplateValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    paths = [r.output_path for r in resolved]
    media_root = Path(settings.MEDIA_ROOT)
    collisions = await find_collisions(db, paths, media_root)
    if collisions and not req.overwrite:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "output_path collisions detected", "collisions": [c.model_dump() for c in collisions]},
        )

    application = SessionApplication(
        session_id=req.session_id,
        job_id=job_id,
        status=SessionApplicationStatus.QUEUED,
        overwrite=req.overwrite,
        created_by_user_id=None,
    )
    db.add(application)
    await db.flush()

    new_tasks = [
        TranscodeTask(
            session_application_id=application.id,
            source_track_id=r.track_id,
            status=TranscodeTaskStatus.QUEUED,
            output_path=r.output_path,
            attempts=0,
            progress_pct=0,
        )
        for r in resolved
    ]
    db.add_all(new_tasks)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="concurrent application detected; another session already claims one of these paths",
        ) from exc

    await db.refresh(application)
    for task in new_tasks:
        await db.refresh(task)

    logger.info(
        "apply session_id=%s job_id=%s tasks=%d overwrite=%s",
        req.session_id,
        job_id,
        len(new_tasks),
        req.overwrite,
    )

    return ApplySessionResponse(
        session_application=SessionApplicationView.model_validate(application),
        tasks=[TranscodeTaskView.model_validate(t) for t in new_tasks],
        collisions=[],
        idempotent=False,
    )
