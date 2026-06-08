import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import (
    require_drive_owner_by_job,
    require_drive_owner_by_track,
    require_service_token,
)
from arm_backend.auto_session import maybe_auto_apply_session
from arm_backend.crash_recovery import reset_job_for_recovery
from arm_backend.db import get_session
from arm_backend.metadata import MetadataDispatcher
from arm_backend.metadata.base import extract_poster_url
from arm_backend.metadata.dispatcher import DISPATCH_TIMEOUT_SECONDS
from arm_backend.seeders import CONFIG_SINGLETON_ID
from arm_backend.track_selection import select_tracks
from arm_backend.ws import WSHub
from arm_common import (
    Config,
    DiscFingerprint,
    DiscType,
    Drive,
    DriveStatus,
    Job,
    JobStatus,
    RipPreset,
    Session,
    TrackStatus,
)
from arm_common.models import Track
from arm_common.schemas import (
    IdentifyRequest,
    JobCompleteRequest,
    JobView,
    RegisterRequest,
    RipperConfigView,
    RipperHeartbeatRequest,
    RipStartResponse,
    ScanResult,
    TrackUpdateRequest,
    TrackView,
)

logger = logging.getLogger("arm_backend.routers.ripper")

router = APIRouter(prefix="/api/ripper", tags=["ripper"])

_DEFAULT_RIP_PRESET_BY_DISC_TYPE: dict[DiscType, str] = {
    DiscType.DVD: "rpr_builtin_movie_archive",
    DiscType.BLURAY: "rpr_builtin_movie_archive",
    DiscType.CD: "rpr_builtin_music_standard",
    DiscType.DATA: "rpr_builtin_data_copy",
}


async def _resolve_min_length_override(db: AsyncSession, job: Job) -> int | None:
    """Look up `Session.overrides_json["min_length_seconds"]` for a job
    that has a pending_session_id, returning None when no override
    applies. The ripper falls back to its host-side
    `ARM_MIN_LENGTH_SECONDS` baseline when this is None.

    Auto-rip-on-insert jobs typically don't have a pending_session_id
    until rip-complete (`maybe_auto_apply_session` fires after the rip)
    so they always use the baseline; manual-trigger jobs that selected
    a session up front get their override here.
    """
    md = job.metadata_json or {}
    sess_id = md.get("pending_session_id")
    if not isinstance(sess_id, str):
        return None
    sess = (await db.execute(select(Session).where(col(Session.id) == sess_id))).scalar_one_or_none()
    if sess is None or not sess.overrides_json:
        return None
    raw = sess.overrides_json.get("min_length_seconds")
    if isinstance(raw, bool):  # bool is an int subclass — reject explicitly
        return None
    if isinstance(raw, int) and raw >= 0:
        return raw
    return None


def _get_dispatcher(request: Request) -> MetadataDispatcher:
    dispatcher: MetadataDispatcher = request.app.state.dispatcher
    return dispatcher


def _get_hub(request: Request) -> WSHub:
    hub: WSHub = request.app.state.ws_hub
    return hub


@router.get("/config", response_model=RipperConfigView, dependencies=[Depends(require_service_token)])
async def get_ripper_config(session: AsyncSession = Depends(get_session)) -> RipperConfigView:
    """Subset of the global Config the ripper reads on each disc insert to
    decide whether to fire its scan/identify/rip pipeline. Cheap enough to
    poll per-insert; avoids the WS-event invalidation dance for a single
    boolean.
    """
    cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="config singleton missing")
    return RipperConfigView(auto_rip_on_insert=cfg.auto_rip_on_insert)


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_service_token)])
async def heartbeat(req: RipperHeartbeatRequest, session: AsyncSession = Depends(get_session)) -> None:
    """Each ripper posts here every HEARTBEAT_INTERVAL_SECONDS with the
    current CDROM_DRIVE_STATUS reading. The manual-trigger endpoint
    reads `media_status` + `media_status_at` to refuse clicks made
    against an empty / open tray, instead of letting identify land an
    empty scan_result.

    `last_seen_at` is bumped on every call so the drive's online state
    is implicitly refreshed too — no separate liveness ping needed."""
    drive = (await session.execute(select(Drive).where(col(Drive.id) == req.drive_id))).scalar_one_or_none()
    if drive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {req.drive_id}")
    now = datetime.now(timezone.utc)
    drive.media_status = req.media_status
    drive.media_status_at = now
    drive.last_seen_at = now
    session.add(drive)
    await session.commit()


@router.post("/register", response_model=Drive, dependencies=[Depends(require_service_token)])
async def register(req: RegisterRequest, session: AsyncSession = Depends(get_session)) -> Drive:
    stmt = (
        pg_insert(Drive)
        .values(
            hostname=req.hostname,
            device_path=req.device_path,
            status=DriveStatus.ONLINE.value,
        )
        .on_conflict_do_update(
            index_elements=[col(Drive.hostname)],
            set_={
                "device_path": req.device_path,
                "status": DriveStatus.ONLINE.value,
            },
        )
        .returning(col(Drive.id))
    )
    result = await session.execute(stmt)
    drive_id = result.scalar_one()
    await session.commit()

    drive = (await session.execute(select(Drive).where(col(Drive.id) == drive_id))).scalar_one()
    return drive


@router.post("/identify", response_model=Job, dependencies=[Depends(require_service_token)])
async def identify(
    req: IdentifyRequest,
    session: AsyncSession = Depends(get_session),
    dispatcher: MetadataDispatcher = Depends(_get_dispatcher),
    hub: WSHub = Depends(_get_hub),
) -> Job:
    drive = (await session.execute(select(Drive).where(col(Drive.id) == req.drive_id))).scalar_one_or_none()
    if drive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {req.drive_id}")

    cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one()

    scan = req.scan_result
    job = Job(
        drive_id=req.drive_id,
        disc_type=scan.disc_type,
        status=JobStatus.CREATED,
    )
    session.add(job)
    await session.flush()

    # Persist every fingerprint the ripper computed. The (job_id, algo)
    # unique constraint plus per-scan dedup means re-runs of identify on
    # the same disc are idempotent.
    seen_algos: set[str] = set()
    for fp in scan.fingerprints:
        if not fp.algo or not fp.value:
            continue
        algo = fp.algo.lower()
        if algo in seen_algos:
            continue
        seen_algos.add(algo)
        session.add(DiscFingerprint(job_id=job.id, algo=algo, value=fp.value))
    await session.flush()

    try:
        result = await asyncio.wait_for(
            dispatcher.identify(scan, cfg),
            timeout=DISPATCH_TIMEOUT_SECONDS,
        )
        timed_out = False
    except asyncio.TimeoutError:
        logger.info("identify dispatch_timeout job_id=%s", job.id)
        result = None
        timed_out = True

    if result is not None:
        job.title = result.title
        job.year = result.year
        job.poster_url = extract_poster_url(result)
        job.metadata_json = result.payload
        job.status = JobStatus.IDENTIFIED
    else:
        diagnostic: dict[str, object] = {}
        if timed_out:
            diagnostic["dispatch_timeout"] = True
        if cfg.block_on_miss:
            job.status = JobStatus.AWAITING_USER_ID
            job.title = scan.volume_label
            if diagnostic:
                job.metadata_json = diagnostic
        else:
            job.status = JobStatus.IDENTIFIED
            job.title = scan.volume_label
            job.metadata_json = {"unidentified": True, **diagnostic}

    job.metadata_json = {
        **(job.metadata_json or {}),
        "scan_result": scan.model_dump(mode="json"),
    }
    if req.pending_session_id is not None:
        job.metadata_json = {
            **(job.metadata_json or {}),
            "pending_session_id": req.pending_session_id,
        }

    await session.commit()
    await session.refresh(job)
    logger.info("identify job_id=%s status=%s title=%s", job.id, job.status.value, job.title)

    if job.status == JobStatus.AWAITING_USER_ID:
        await hub.emit(
            topic="ripper.events",
            event_type="rip.needs_user_input",
            payload={
                "job_id": job.id,
                "drive_id": job.drive_id,
                "volume_label": scan.volume_label,
                "disc_type": job.disc_type.value,
            },
            job_id=job.id,
            session=session,
        )
        await session.commit()
    return job


@router.get("/jobs/{job_id}", response_model=JobView, dependencies=[Depends(require_service_token)])
async def get_job(job_id: str, session: AsyncSession = Depends(get_session)) -> Job:
    job = (await session.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    return job


@router.post("/jobs/{job_id}/rip-start", response_model=RipStartResponse)
async def rip_start(
    job: Job = Depends(require_drive_owner_by_job),
    session: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(_get_hub),
) -> RipStartResponse:
    preset_id = _DEFAULT_RIP_PRESET_BY_DISC_TYPE.get(job.disc_type)
    if preset_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"no default rip preset for disc_type={job.disc_type.value}",
        )

    existing = (
        (await session.execute(select(Track).where(col(Track.job_id) == job.id).order_by(col(Track.index))))
        .scalars()
        .all()
    )
    if existing:
        return RipStartResponse(
            job_id=job.id,
            rip_preset_id=preset_id,
            tracks=[TrackView.model_validate(t) for t in existing],
            min_length_seconds=await _resolve_min_length_override(session, job),
        )

    if job.status != JobStatus.IDENTIFIED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job not in identified state: status={job.status.value}",
        )

    scan_dict = (job.metadata_json or {}).get("scan_result")
    if not scan_dict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="job missing scan_result in metadata_json",
        )
    scan = ScanResult.model_validate(scan_dict)

    preset = (await session.execute(select(RipPreset).where(col(RipPreset.id) == preset_id))).scalar_one_or_none()
    if preset is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"built-in rip preset {preset_id} not seeded",
        )

    new_tracks = select_tracks(job.id, scan, preset)
    if not new_tracks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="track selection produced zero tracks",
        )

    session.add_all(new_tracks)
    job.status = JobStatus.RIPPING
    job.started_at = datetime.now(timezone.utc)
    await session.commit()

    refreshed = (
        (await session.execute(select(Track).where(col(Track.job_id) == job.id).order_by(col(Track.index))))
        .scalars()
        .all()
    )
    logger.info(
        "rip-start job_id=%s preset=%s tracks=%d",
        job.id,
        preset_id,
        len(refreshed),
    )

    await hub.emit(
        topic="ripper.events",
        event_type="rip.started",
        payload={
            "job_id": job.id,
            "drive_id": job.drive_id,
            "rip_preset_id": preset_id,
            "track_count": len(refreshed),
        },
        job_id=job.id,
        session=session,
    )
    await session.commit()

    return RipStartResponse(
        job_id=job.id,
        rip_preset_id=preset_id,
        tracks=[TrackView.model_validate(t) for t in refreshed],
        min_length_seconds=await _resolve_min_length_override(session, job),
    )


@router.post("/jobs/{job_id}/resume", response_model=RipStartResponse)
async def resume(
    job: Job = Depends(require_drive_owner_by_job),
    session: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(_get_hub),
) -> RipStartResponse:
    """Phase 9 — per-job crash-recovery reset for the 'only ripper crashed'
    case. Idempotent: re-running on an already-reset job is a no-op.
    Returns the same shape as `rip-start` so the ripper's existing flow
    continues unchanged.
    """
    if job.status != JobStatus.RIPPING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job not in ripping state: status={job.status.value}",
        )

    preset_id = _DEFAULT_RIP_PRESET_BY_DISC_TYPE.get(job.disc_type)
    if preset_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"no default rip preset for disc_type={job.disc_type.value}",
        )

    await reset_job_for_recovery(session, job)
    await session.commit()

    refreshed = (
        (await session.execute(select(Track).where(col(Track.job_id) == job.id).order_by(col(Track.index))))
        .scalars()
        .all()
    )
    logger.info("rip-resume job_id=%s tracks=%d", job.id, len(refreshed))

    await hub.emit(
        topic="ripper.events",
        event_type="rip.resumed",
        payload={
            "job_id": job.id,
            "drive_id": job.drive_id,
            "track_count": len(refreshed),
            "resumed_from_crash": True,
        },
        job_id=job.id,
        session=session,
    )
    await session.commit()

    return RipStartResponse(
        job_id=job.id,
        rip_preset_id=preset_id,
        tracks=[TrackView.model_validate(t) for t in refreshed],
        min_length_seconds=await _resolve_min_length_override(session, job),
    )


@router.get(
    "/drives/{drive_id}/in-flight-job",
    response_model=JobView,
    dependencies=[Depends(require_service_token)],
)
async def get_in_flight_job(drive_id: str, session: AsyncSession = Depends(get_session)) -> Job:
    """Phase 9 — boot-probe lookup. Returns the single RIPPING job assigned
    to this drive, if any. 404 if the drive is unknown or no in-flight job
    exists. Multiple matches (data-model violation) log + return the first.
    """
    drive = (await session.execute(select(Drive).where(col(Drive.id) == drive_id))).scalar_one_or_none()
    if drive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {drive_id}")
    rows = (
        (
            await session.execute(
                select(Job).where(col(Job.drive_id) == drive_id).where(col(Job.status) == JobStatus.RIPPING)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no in-flight job on this drive")
    if len(rows) > 1:
        logger.error(
            "data-model violation: %d RIPPING jobs on drive_id=%s; returning first",
            len(rows),
            drive_id,
        )
    return rows[0]


@router.patch("/tracks/{track_id}", response_model=TrackView)
async def update_track(
    req: TrackUpdateRequest,
    track: Track = Depends(require_drive_owner_by_track),
    session: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(_get_hub),
) -> TrackView:
    new_status = req.status
    current = track.status

    if new_status == TrackStatus.IN_PROGRESS:
        if current != TrackStatus.QUEUED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"cannot move {current.value} -> in_progress",
            )
        track.attempts += 1
    elif new_status == TrackStatus.DONE:
        if current != TrackStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"cannot move {current.value} -> done",
            )
        if req.output_path is not None:
            track.output_path = req.output_path
        if req.size_bytes is not None:
            track.size_bytes = req.size_bytes
        if req.sha256 is not None:
            track.sha256 = req.sha256
        if req.duration_seconds is not None:
            track.duration_seconds = req.duration_seconds
    elif new_status == TrackStatus.FAILED:
        if current != TrackStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"cannot move {current.value} -> failed",
            )
        if req.last_error is not None:
            track.last_error = req.last_error
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"target status {new_status.value} not allowed via PATCH",
        )

    track.status = new_status
    await session.commit()
    await session.refresh(track)

    if new_status == TrackStatus.DONE:
        await hub.emit(
            topic="ripper.events",
            event_type="track.completed",
            payload={
                "track_id": track.id,
                "job_id": track.job_id,
                "output_path": track.output_path,
                "size_bytes": track.size_bytes,
                "duration_seconds": track.duration_seconds,
            },
            job_id=track.job_id,
            track_id=track.id,
            session=session,
        )
        await session.commit()
    elif new_status == TrackStatus.FAILED:
        await hub.emit(
            topic="ripper.events",
            event_type="track.failed",
            payload={
                "track_id": track.id,
                "job_id": track.job_id,
                "last_error": track.last_error,
            },
            job_id=track.job_id,
            track_id=track.id,
            session=session,
        )
        await session.commit()

    return TrackView.model_validate(track)


@router.post("/jobs/{job_id}/rip-complete", response_model=JobView)
async def rip_complete(
    _: JobCompleteRequest,
    job: Job = Depends(require_drive_owner_by_job),
    session: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(_get_hub),
) -> JobView:
    if job.status != JobStatus.RIPPING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job not in ripping state: status={job.status.value}",
        )

    tracks = (await session.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all()

    done = sum(1 for t in tracks if t.status == TrackStatus.DONE)
    failed = sum(1 for t in tracks if t.status == TrackStatus.FAILED)
    total = len(tracks)

    if total == 0 or done == 0:
        job.status = JobStatus.FAILED
    elif failed == 0:
        job.status = JobStatus.RIPPED
    else:
        job.status = JobStatus.RIPPED_PARTIAL

    job.ripped_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(job)
    logger.info(
        "rip-complete job_id=%s status=%s done=%d failed=%d total=%d",
        job.id,
        job.status.value,
        done,
        failed,
        total,
    )

    event_type = {
        JobStatus.RIPPED: "rip.completed",
        JobStatus.RIPPED_PARTIAL: "rip.partial",
        JobStatus.FAILED: "rip.failed",
    }.get(job.status, "rip.completed")
    await hub.emit(
        topic="ripper.events",
        event_type=event_type,
        payload={
            "job_id": job.id,
            "drive_id": job.drive_id,
            "status": job.status.value,
            "tracks_done": done,
            "tracks_failed": failed,
            "tracks_total": total,
        },
        job_id=job.id,
        session=session,
    )
    await session.commit()

    if job.status in (JobStatus.RIPPED, JobStatus.RIPPED_PARTIAL):
        await maybe_auto_apply_session(session, job, hub)

    return JobView.model_validate(job)
