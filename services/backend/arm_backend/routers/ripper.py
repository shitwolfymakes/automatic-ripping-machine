import logging
from collections.abc import Callable, Sequence
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend import iso_prepare
from arm_backend.auth import (
    require_drive_owner_by_job,
    require_drive_owner_by_track,
    require_service_token,
)
from arm_backend.session_drain import after_rip, cancel_parked_applications
from arm_backend.crash_recovery import reset_job_for_recovery
from arm_backend.db import get_session
from arm_backend.metadata import MetadataDispatcher
from arm_backend.identify_flow import DiscAlreadyRippedError, IdentifyFlow, RippingPausedError, UnknownDriveError
from arm_backend.rip_preset_resolution import (
    RipPresetUnavailable,
    load_routed_session,
    min_length_override_from_session,
    rip_preset_id_from_session,
)
from arm_backend.constants import CONFIG_SINGLETON_ID
from arm_backend.identity.episode_stage import is_tv_candidate
from arm_backend.identity.pipeline import resolve_job
from arm_backend.identity.proposals import record_preset
from arm_backend.identity.stage_runner import EpisodeStageRunner
from arm_backend.routers._deps import get_hub, get_stage_runner
from arm_backend.track_selection import DiscBackupNeedsBluray, select_tracks
from arm_backend.ws import WSHub
from arm_common import (
    Config,
    Drive,
    DriveLifecycle,
    DriveMediaStatus,
    DriveMode,
    DriveStatus,
    Job,
    JobStatus,
    MakemkvKeyState,
    RipPreset,
    TrackStatus,
)
from arm_common.enums import NON_TERMINAL_JOB_STATUSES, DriveKind, DriveSourceKind
from arm_common.models import Track
from arm_common.models._columns import enum_value_str
from arm_common.schemas import (
    DriveDevicePathUpdateRequest,
    IsoPrepareReport,
    flag_is_set,
    identity_suggestion_of,
    previously_ripped_job_id,
    HeldJobView,
    IdentifyRequest,
    JobCompleteRequest,
    JobView,
    KeydbStatusReport,
    MakemkvKeyStatusReport,
    RegisterRequest,
    RipperConfigView,
    RipperHeartbeatRequest,
    RipStartResponse,
    ScanResult,
    SdfStatusReport,
    TrackUpdateRequest,
    TrackView,
)

logger = logging.getLogger("arm_backend.routers.ripper")

router = APIRouter(prefix="/api/ripper", tags=["ripper"])

ISO_NO_TITLES = (
    "MakeMKV found no titles in this ISO, even after unpacking it. "
    'To keep a copy of the image anyway, rip it again with the "ISO: Full-disc dump" session.'
)
FOLDER_NO_TITLES = "MakeMKV found no titles in this disc folder. Check that its BDMV or VIDEO_TS tree is complete."


async def _virtual_source_drive(db: AsyncSession, job: Job) -> Drive | None:
    """The job's drive when it is a virtual one (an ISO or disc-folder rip)."""
    if job.drive_id is None:
        return None
    drive = (await db.execute(select(Drive).where(col(Drive.id) == job.drive_id))).scalar_one_or_none()
    return drive if drive is not None and drive.kind == DriveKind.VIRTUAL else None


async def _fail_titleless_source(db: AsyncSession, hub: WSHub, job: Job, reason: str) -> None:
    job.status = JobStatus.FAILED
    job.ripped_at = datetime.now(timezone.utc)
    db.add(job)
    await cancel_parked_applications(db, job)
    await hub.emit(
        topic="ripper.events",
        event_type="rip.failed",
        payload={
            "job_id": job.id,
            "drive_id": job.drive_id,
            "status": job.status.value,
            "tracks_done": 0,
            "tracks_failed": 0,
            "tracks_total": 0,
            "reason": reason,
        },
        job_id=job.id,
        session=db,
    )
    await db.commit()
    logger.warning("rip-start job_id=%s failed: %s", job.id, reason)


def _rip_preset_or_http(exc: RipPresetUnavailable) -> HTTPException:
    code = (
        status.HTTP_422_UNPROCESSABLE_CONTENT if exc.reason == "no_default" else status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    return HTTPException(status_code=code, detail=exc.detail)


def _get_dispatcher(request: Request) -> MetadataDispatcher:
    dispatcher: MetadataDispatcher = request.app.state.dispatcher
    return dispatcher


@router.get("/config", response_model=RipperConfigView, dependencies=[Depends(require_service_token)])
async def get_ripper_config(
    drive_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> RipperConfigView:
    """Subset of the global Config the ripper reads on each disc insert to
    decide whether to fire its scan/identify/rip pipeline. Cheap enough to
    poll per-insert; avoids the WS-event invalidation dance for a single
    boolean.

    `drive_id` resolves auto-rip per drive: a non-null Drive.drive_mode
    overrides the global Config.auto_rip_on_insert default; NULL follows it
    Rippers that omit it get the global value.
    """
    cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="config singleton missing")
    auto_rip = bool(cfg.auto_rip_on_insert)
    if drive_id is not None:
        drive = (await session.execute(select(Drive).where(col(Drive.id) == drive_id))).scalar_one_or_none()
        if drive is not None and drive.drive_mode is not None:
            auto_rip = drive.drive_mode == DriveMode.AUTO
    return RipperConfigView(
        auto_rip_on_insert=auto_rip,
        makemkv_key=cfg.makemkv_key,
        community_keydb_enabled=bool(cfg.community_keydb_enabled),
        makemkv_sdf_enabled=bool(cfg.makemkv_sdf_enabled),
        ripping_paused=bool(cfg.ripping_paused),
        manual_wait_seconds=int(cfg.manual_wait_seconds) if cfg.manual_wait_seconds is not None else 60,
    )


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
    # The disc a notice was about has left the tray: the open tray an eject
    # leaves has closed empty. Only that change clears it. A slot-loading drive
    # has no open tray and reads "no disc" the moment it ejects, so its notice
    # stays until the next disc is identified.
    if drive.media_status == DriveMediaStatus.TRAY_OPEN and req.media_status is DriveMediaStatus.NO_DISC:
        drive.notice = None
    drive.media_status = req.media_status
    drive.media_status_at = now
    drive.last_seen_at = now
    # For an enrolled drive the ripper is authoritative on presence.
    # DETACHED = the node has no hardware behind it right now. ERROR (identity
    # mismatch) is an operator problem and is never auto-cleared.
    if req.media_status is DriveMediaStatus.DETACHED:
        drive.present = False
        if drive.status is not DriveStatus.ERROR:
            drive.status = DriveStatus.OFFLINE
    else:
        drive.present = True
        if drive.status is DriveStatus.OFFLINE:
            drive.status = DriveStatus.ONLINE
    session.add(drive)
    await session.commit()


@router.post(
    "/iso-prepare",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_service_token)],
)
async def iso_prepare_report(
    req: IsoPrepareReport, request: Request, session: AsyncSession = Depends(get_session)
) -> None:
    """An ISO ripper's phase before its job exists (scanning, extracting with
    progress). Kept in memory (`iso_prepare`) and pushed to the dashboard
    through a non-persisted `ripper.events` event, which wakes its refresh."""
    drive = (await session.execute(select(Drive).where(col(Drive.id) == req.drive_id))).scalar_one_or_none()
    if drive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {req.drive_id}")
    view = iso_prepare.record(req)
    await get_hub(request).emit(
        topic="ripper.events", event_type="iso.preparing", payload=view.model_dump(mode="json"), persist=False
    )


@router.get("/drives/{drive_id}", response_model=Drive, dependencies=[Depends(require_service_token)])
async def get_drive(drive_id: str, session: AsyncSession = Depends(get_session)) -> Drive:
    """This ripper's own row. Port-identity rippers read `device_path` from
    it while their drive is absent — the scanner keeps that current by port
    and the ripper cannot see a renumbering by itself without a
    by-id link. Returns the table model: the ripper validates it as `Drive`."""
    drive = (await session.execute(select(Drive).where(col(Drive.id) == drive_id))).scalar_one_or_none()
    if drive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {drive_id}")
    return drive


@router.patch(
    "/drives/{drive_id}/device-path",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_service_token)],
)
async def update_device_path(
    drive_id: str, req: DriveDevicePathUpdateRequest, session: AsyncSession = Depends(get_session)
) -> None:
    """Ripper → backend on a node move (replug under a new srN), so the UI
    never shows a stale node. Identity is untouched — only where it lives."""
    drive = (await session.execute(select(Drive).where(col(Drive.id) == drive_id))).scalar_one_or_none()
    if drive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {drive_id}")
    drive.device_path = req.device_path
    session.add(drive)
    await session.commit()


def _valid_from_state(state: MakemkvKeyState) -> bool | None:
    if state == MakemkvKeyState.VALID:
        return True
    if state == MakemkvKeyState.PROBE_FAILED:
        return None
    return False


@router.post(
    "/makemkv-key-status",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_service_token)],
)
async def makemkv_key_status(
    req: MakemkvKeyStatusReport,
    session: AsyncSession = Depends(get_session),
) -> None:
    """A ripper reports its disc-free makemkv probe outcome. Global fact —
    written to the Config singleton (last writer wins across multiple rippers,
    by design). the key check, preflight and config view read it back."""
    cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="config singleton missing")
    cfg.makemkv_key_state = req.state.value
    cfg.makemkv_key_valid = _valid_from_state(req.state)
    cfg.makemkv_key_checked_at = datetime.now(timezone.utc)
    cfg.makemkv_key_checked_by_drive_id = req.drive_id
    session.add(cfg)
    await session.commit()


@router.post(
    "/keydb-status",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_service_token)],
)
async def keydb_status(
    req: KeydbStatusReport,
    session: AsyncSession = Depends(get_session),
) -> None:
    """A ripper reports its community-keydb fetch outcome. Global fact —
    written to the Config singleton (last writer wins across rippers, by
    design). /api/system/preflight reads it back. `age_days` is accepted for
    symmetry with the ripper's status line but not persisted (no column for
    it); only state + vuk_count are durable."""
    cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="config singleton missing")
    cfg.community_keydb_state = req.state.value
    cfg.community_keydb_vuk_count = req.vuk_count
    cfg.community_keydb_checked_at = datetime.now(timezone.utc)
    session.add(cfg)
    await session.commit()


@router.post(
    "/sdf-status",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_service_token)],
)
async def sdf_status(
    req: SdfStatusReport,
    session: AsyncSession = Depends(get_session),
) -> None:
    """A ripper reports its MakeMKV SDF fetch outcome. Global fact — written
    to the Config singleton (last writer wins across rippers). preflight reads
    it back. `age_days` is accepted for symmetry with the status line but not
    persisted (no column)."""
    cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="config singleton missing")
    cfg.makemkv_sdf_state = req.state.value
    cfg.makemkv_sdf_checked_at = datetime.now(timezone.utc)
    session.add(cfg)
    await session.commit()


@router.post("/register", response_model=Drive, dependencies=[Depends(require_service_token)])
async def register(req: RegisterRequest, session: AsyncSession = Depends(get_session)) -> Drive:
    """A ripper container announcing itself for the row the backend spawned
    it for (ARM_DRIVE_ID). Keyed on the id — hostname is written as the
    ownership token every X-ARM-Hostname check compares, never used to look
    the row up. Identity is checked, never rewritten: a by-id mismatch means
    the container is bound to a different physical drive than the row, so
    the row goes ERROR and the container is left running for diagnosis."""
    drive = (await session.execute(select(Drive).where(col(Drive.id) == req.drive_id))).scalar_one_or_none()
    if drive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {req.drive_id}")
    if drive.lifecycle is not DriveLifecycle.ENROLLED:
        detail = f"drive is not enrolled (lifecycle '{drive.lifecycle.value}')"
        logger.warning("register refused drive_id=%s: %s", drive.id, detail)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if drive.by_id_name and drive.by_id_name != req.by_id_name:
        # The row has a by-id binding — the ripper must report the same one.
        # None on the ripper's side counts as different: a
        # port-identity container registering against a by-id-bound row is
        # exactly the identity mismatch this check exists to catch.
        if req.by_id_name is None:
            detail = (
                f"identity mismatch: row is bound to {drive.by_id_name} but the ripper has no by-id binding — "
                "unenroll and re-enroll to recreate the container"
            )
        else:
            detail = f"identity mismatch: row is bound to {drive.by_id_name} but the ripper resolved {req.by_id_name}"
        logger.error("register refused drive_id=%s: %s", drive.id, detail)
        drive.status = DriveStatus.ERROR
        drive.last_error = detail
        session.add(drive)
        await session.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    drive.hostname = req.hostname
    drive.device_path = req.device_path
    drive.status = DriveStatus.ONLINE
    drive.present = True
    drive.last_seen_at = datetime.now(timezone.utc)
    drive.last_error = None
    session.add(drive)
    await session.commit()
    # updated_at is server-generated (onupdate) and expired after the flush;
    # the ripper validates the body as Drive, which requires it.
    await session.refresh(drive)
    logger.info("ripper registered drive_id=%s hostname=%s device=%s", drive.id, req.hostname, req.device_path)
    return drive


# The 409 detail identify answers when on_previously_ripped=reject turns a disc
# away; the ripper ejects on it.
PREVIOUSLY_RIPPED_REASON = "previously_ripped"


@router.post("/identify", response_model=Job, dependencies=[Depends(require_service_token)])
async def identify(
    req: IdentifyRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    dispatcher: MetadataDispatcher = Depends(_get_dispatcher),
    hub: WSHub = Depends(get_hub),
    stage_runner: EpisodeStageRunner | None = Depends(get_stage_runner),
) -> Job:
    flow = IdentifyFlow(
        req=req,
        thediscdb_store=getattr(request.app.state, "thediscdb", None),
        session=session,
        dispatcher=dispatcher,
        hub=hub,
        stage_runner=stage_runner,
    )
    try:
        return await flow.run()
    except UnknownDriveError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {exc.drive_id}") from exc
    except RippingPausedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ripping is paused; no new jobs accepted",
        ) from exc
    except DiscAlreadyRippedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"reason": PREVIOUSLY_RIPPED_REASON, "job_id": exc.previous_job_id},
        ) from exc


@router.get("/jobs/{job_id}", response_model=JobView, dependencies=[Depends(require_service_token)])
async def get_job(job_id: str, session: AsyncSession = Depends(get_session)) -> Job:
    job = (await session.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    return job


async def _routed_rip_choice(session: AsyncSession, job: Job) -> tuple[str, int | None]:
    # Resolve the routed session ONCE for this request — the preset choice and
    # the min-length override both derive from the same `sess`, so there is one
    # Session SELECT and one warning on a missing routed row.
    sess = await load_routed_session(session, job)
    try:
        preset_id = rip_preset_id_from_session(sess, job.disc_type)
    except RipPresetUnavailable as exc:
        raise _rip_preset_or_http(exc) from exc
    min_length_seconds = min_length_override_from_session(sess)
    return preset_id, min_length_seconds


async def _job_tracks(session: AsyncSession, job_id: str) -> Sequence[Track]:
    return (
        (await session.execute(select(Track).where(col(Track.job_id) == job_id).order_by(col(Track.index))))
        .scalars()
        .all()
    )


def _rip_start_response(
    job: Job, preset_id: str, tracks: Sequence[Track], min_length_seconds: int | None
) -> RipStartResponse:
    return RipStartResponse(
        job_id=job.id,
        rip_preset_id=preset_id,
        tracks=[TrackView.model_validate(t) for t in tracks],
        min_length_seconds=min_length_seconds,
    )


async def _ensure_ripping(session: AsyncSession, job: Job) -> None:
    # Tracks already exist (crash-resume, or the timed review gate persisted
    # them at identify and the operator's Start already moved the job to
    # RIPPING). Ensure the RIPPING transition happened (setting RIPPING/started_at),
    # or a pre-persisted-tracks job would never transition and the rip never
    # completes. Tolerate already-RIPPING (Start did it); transition if not.
    if job.status != JobStatus.RIPPING:
        job.status = JobStatus.RIPPING
        if job.started_at is None:
            job.started_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(job)


def _require_startable(job: Job) -> None:
    # IDENTIFIED is the normal pre-rip state; AWAITING_REVIEW reaches here only
    # when the timed review gate auto-started (countdown elapsed) a held disc
    # whose scan yielded NO persistable titles — _persist_review_tracks then
    # added nothing, so `existing` above was empty. Fall through and select
    # tracks now, exactly as for a never-parked disc; without this the disc
    # 409s and the ripper (4xx = non-retryable) abandons it permanently.
    if job.status not in (JobStatus.IDENTIFIED, JobStatus.AWAITING_REVIEW):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job not in identified state: status={enum_value_str(job.status)}",
        )


def _scan_of(job: Job) -> ScanResult:
    scan_dict = (job.metadata_json or {}).get("scan_result")
    if not scan_dict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="job missing scan_result in metadata_json",
        )
    return ScanResult.model_validate(scan_dict)


async def _load_rip_preset(session: AsyncSession, preset_id: str) -> RipPreset:
    preset = (await session.execute(select(RipPreset).where(col(RipPreset.id) == preset_id))).scalar_one_or_none()
    if preset is None:
        raise _rip_preset_or_http(RipPresetUnavailable("not_seeded", f"built-in rip preset {preset_id} not seeded"))
    return preset


async def _select_or_fail(
    session: AsyncSession, hub: WSHub, job: Job, scan: ScanResult, preset: RipPreset
) -> list[Track]:
    # A whole-disc preset (ISO dump, FOLDER backup) gives its one track
    # whatever the scan found, so it never lands in the no-titles handling
    # below; a FOLDER preset on anything but a Blu-ray is refused here.
    try:
        new_tracks = select_tracks(job.id, scan, preset)
    except DiscBackupNeedsBluray as exc:
        # Fail the job with the reason on its event: the ripper gives up on a
        # 4xx, and the job would otherwise sit IDENTIFIED with nothing to say why.
        await _fail_titleless_source(session, hub, job, str(exc))
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    virtual = None if new_tracks or scan.titles else await _virtual_source_drive(session, job)
    if virtual is not None:
        # MakeMKV found nothing in the image (not even once it was unpacked,
        # arm_ripper.iso_extract) or in the disc folder. Fail it like a disc with no titles, with
        # the reason on the job's event; never switch it to a full-disc dump
        # behind the operator's back (that filed the .iso where a movie was
        # expected). The ripper then exits and the watchdog retires the drive.
        reason = FOLDER_NO_TITLES if virtual.source_kind == DriveSourceKind.FOLDER else ISO_NO_TITLES
        await _fail_titleless_source(session, hub, job, reason)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=reason)
    if not new_tracks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="track selection produced zero tracks",
        )
    return new_tracks


async def _begin_rip(session: AsyncSession, job: Job, new_tracks: list[Track]) -> None:
    session.add_all(new_tracks)
    await session.flush()
    record_preset(job, new_tracks, now=datetime.now(timezone.utc))
    await resolve_job(session, job)
    job.status = JobStatus.RIPPING
    job.started_at = datetime.now(timezone.utc)
    await session.commit()


async def _emit_rip_started(session: AsyncSession, hub: WSHub, job: Job, preset_id: str, track_count: int) -> None:
    await hub.emit(
        topic="ripper.events",
        event_type="rip.started",
        payload={
            "job_id": job.id,
            "drive_id": job.drive_id,
            "rip_preset_id": preset_id,
            "track_count": track_count,
        },
        job_id=job.id,
        session=session,
    )
    await session.commit()


@router.post("/jobs/{job_id}/rip-start", response_model=RipStartResponse)
async def rip_start(
    job: Job = Depends(require_drive_owner_by_job),
    session: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(get_hub),
    stage_runner: EpisodeStageRunner | None = Depends(get_stage_runner),
) -> RipStartResponse:
    preset_id, min_length_seconds = await _routed_rip_choice(session, job)

    existing = await _job_tracks(session, job.id)
    if existing:
        await _ensure_ripping(session, job)
        return _rip_start_response(job, preset_id, existing, min_length_seconds)

    _require_startable(job)
    scan = _scan_of(job)
    preset = await _load_rip_preset(session, preset_id)
    new_tracks = await _select_or_fail(session, hub, job, scan, preset)
    await _begin_rip(session, job, new_tracks)

    refreshed = await _job_tracks(session, job.id)
    logger.info(
        "rip-start job_id=%s preset=%s tracks=%d",
        job.id,
        preset_id,
        len(refreshed),
    )

    await _emit_rip_started(session, hub, job, preset_id, len(refreshed))

    # Without the review hold, identify creates no Track rows, so the
    # stage it scheduled saw nothing to match. The tracks appear here.
    if stage_runner is not None and is_tv_candidate(job, new_tracks):
        stage_runner.schedule(job.id)

    return _rip_start_response(job, preset_id, refreshed, min_length_seconds)


@router.post("/jobs/{job_id}/resume", response_model=RipStartResponse)
async def resume(
    job: Job = Depends(require_drive_owner_by_job),
    session: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(get_hub),
) -> RipStartResponse:
    """Per-job crash-recovery reset for the 'only ripper crashed'
    case. Idempotent: re-running on an already-reset job is a no-op.
    Returns the same shape as `rip-start` so the ripper's existing flow
    continues unchanged.
    """
    if job.status != JobStatus.RIPPING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job not in ripping state: status={job.status.value}",
        )

    # One routed-session resolution for this request (see _routed_rip_choice).
    preset_id, min_length_seconds = await _routed_rip_choice(session, job)

    await reset_job_for_recovery(session, job)
    await session.commit()

    refreshed = await _job_tracks(session, job.id)
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

    return _rip_start_response(job, preset_id, refreshed, min_length_seconds)


@router.get(
    "/drives/{drive_id}/in-flight-job",
    response_model=JobView,
    dependencies=[Depends(require_service_token)],
)
async def get_in_flight_job(drive_id: str, session: AsyncSession = Depends(get_session)) -> Job:
    """Boot-probe lookup. Returns the single RIPPING job assigned
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


@router.get(
    "/drives/{drive_id}/current-job",
    response_model=JobView,
    dependencies=[Depends(require_service_token)],
)
async def get_current_job(drive_id: str, session: AsyncSession = Depends(get_session)) -> Job:
    """The drive's single non-terminal job, if any (any pre-rip status OR
    ripping). Lets an idle ripper re-acquire a disc whose resolution landed after
    the in-memory wait timed out. 404 when the drive is unknown or no live job."""
    drive = (await session.execute(select(Drive).where(col(Drive.id) == drive_id))).scalar_one_or_none()
    if drive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {drive_id}")
    rows = (
        (
            await session.execute(
                select(Job)
                .where(col(Job.drive_id) == drive_id)
                .where(col(Job.status).in_(tuple(NON_TERMINAL_JOB_STATUSES)))
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no current job on this drive")
    if len(rows) > 1:
        logger.error("data-model violation: %d non-terminal jobs on drive_id=%s; returning first", len(rows), drive_id)
    return rows[0]


@router.get(
    "/drives/{drive_id}/held-job",
    response_model=HeldJobView,
    dependencies=[Depends(require_service_token)],
)
async def get_held_job(drive_id: str, session: AsyncSession = Depends(get_session)) -> HeldJobView:
    """Boot-probe lookup for a disc held in AWAITING_REVIEW (timed review gate).

    Returns the held job plus `paused` (true when the disc should survive a ripper
    reboot as a hold: global `ripping_paused`, or the per-job `manual_pause` set by
    review-pause). The ripper uses `paused` to choose re-park vs. abandon on restart.
    404 when the drive is unknown or no held job
    exists. Distinct from `/in-flight-job` (RIPPING-only) so the two recovery
    paths stay separate.
    """
    drive = (await session.execute(select(Drive).where(col(Drive.id) == drive_id))).scalar_one_or_none()
    if drive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {drive_id}")
    rows = (
        (
            await session.execute(
                select(Job).where(col(Job.drive_id) == drive_id).where(col(Job.status) == JobStatus.AWAITING_REVIEW)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no held job on this drive")
    if len(rows) > 1:
        logger.error(
            "data-model violation: %d AWAITING_REVIEW jobs on drive_id=%s; returning first",
            len(rows),
            drive_id,
        )
    cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    # paused = the hold survives a reboot: global ripping_paused OR this disc's
    # per-job manual_pause. Either means the operator deliberately held it.
    global_paused = bool(cfg.ripping_paused) if cfg is not None else False
    # A previously-ripped hold, a held suggestion or a guessed episode
    # placement waits for the operator however it got there.
    view = JobView.model_validate(rows[0])
    paused = (
        global_paused
        or bool(rows[0].manual_pause)
        or previously_ripped_job_id(rows[0].metadata_json) is not None
        or identity_suggestion_of(rows[0].metadata_json) is not None
        or view.episodes_unsure
    )
    return HeldJobView(job=view, paused=paused)


@router.post(
    "/jobs/{job_id}/recovery-abandon",
    response_model=JobView,
    dependencies=[Depends(require_service_token)],
)
async def recovery_abandon(
    job_id: str,
    session: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(get_hub),
) -> Job:
    """Service-token abandon for ripper reboot recovery (timed review gate).

    A held disc that was only COUNTING DOWN (not paused) when the ripper restarted
    is abandoned here so the drive frees; the seated disc then re-fires the
    ripper's InsertDetector and re-enters review with a fresh countdown. Only
    AWAITING_REVIEW is abandonable via this path (the operator-facing
    `/jobs/{id}/abandon` covers the rest); no WS job.abandoned is emitted because
    the ripper is the caller and has no active task to cancel.
    """
    job = (await session.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    if job.status != JobStatus.AWAITING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"recovery-abandon only valid for awaiting_review, got {enum_value_str(job.status)}",
        )
    job.status = JobStatus.ABANDONED
    session.add(job)
    await cancel_parked_applications(session, job)
    await session.flush()
    await hub.emit(
        topic="ripper.events",
        event_type="rip.abandoned",
        payload={"job_id": job.id, "drive_id": job.drive_id, "status": job.status.value},
        job_id=job.id,
        session=session,
    )
    return job


def _start_track(track: Track, req: TrackUpdateRequest) -> None:
    track.attempts += 1


def _finish_track(track: Track, req: TrackUpdateRequest) -> None:
    if req.output_path is not None:
        track.output_path = req.output_path
    if req.size_bytes is not None:
        track.size_bytes = req.size_bytes
    if req.sha256 is not None:
        track.sha256 = req.sha256
    if req.duration_seconds is not None:
        track.duration_seconds = req.duration_seconds


def _fail_track(track: Track, req: TrackUpdateRequest) -> None:
    if req.last_error is not None:
        track.last_error = req.last_error


# Target status -> (the one status it may be reached from, how to apply the request to the track).
_TRACK_TRANSITIONS: dict[TrackStatus, tuple[TrackStatus, Callable[[Track, TrackUpdateRequest], None]]] = {
    TrackStatus.IN_PROGRESS: (TrackStatus.QUEUED, _start_track),
    TrackStatus.DONE: (TrackStatus.IN_PROGRESS, _finish_track),
    TrackStatus.FAILED: (TrackStatus.IN_PROGRESS, _fail_track),
}


def _require_transition(current: TrackStatus, allowed_from: TrackStatus, target: TrackStatus) -> None:
    if current != allowed_from:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"cannot move {current.value} -> {target.value}",
        )


async def _emit_track_event(session: AsyncSession, hub: WSHub, track: Track, new_status: TrackStatus) -> None:
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


@router.patch("/tracks/{track_id}", response_model=TrackView)
async def update_track(
    req: TrackUpdateRequest,
    track: Track = Depends(require_drive_owner_by_track),
    session: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(get_hub),
) -> TrackView:
    new_status = req.status
    rule = _TRACK_TRANSITIONS.get(new_status)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"target status {new_status.value} not allowed via PATCH",
        )
    allowed_from, apply = rule
    _require_transition(track.status, allowed_from, new_status)
    apply(track, req)

    track.status = new_status
    await session.commit()
    await session.refresh(track)
    await _emit_track_event(session, hub, track, new_status)

    return TrackView.model_validate(track)


@router.post("/jobs/{job_id}/rip-complete", response_model=JobView)
async def rip_complete(
    _: JobCompleteRequest,
    job: Job = Depends(require_drive_owner_by_job),
    session: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(get_hub),
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
        # Nothing was ripped, so nothing will ever drain a parked application.
        await cancel_parked_applications(session, job)
    elif failed == 0:
        # A placeholder rip (identify missed, block_on_miss=false) parks at
        # RIPPED_AWAITING_IDENTIFY: transcode is gated on identity, so the
        # after-rip hooks wait for resolve
        # (see docs/developers/architecture/02, placeholder rips). A PARTIAL
        # unidentified rip stays RIPPED_PARTIAL — the enum
        # has no partial+unidentified value and losing partiality would hide
        # failed tracks; it remains resolvable (PRESERVE) either way.
        if flag_is_set(job.metadata_json, "unidentified"):
            job.status = JobStatus.RIPPED_AWAITING_IDENTIFY
        else:
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
        JobStatus.RIPPED_AWAITING_IDENTIFY: "rip.completed",
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

    # The unidentified-flag gate covers both ripped outcomes, not just RIPPED:
    # a RIPPED_PARTIAL placeholder (identify missed, block_on_miss=false) must
    # not reach after_rip, or transcodes would fan out with paths built from
    # the raw volume label under the wrong identity. Status handling is
    # unchanged (partial stays RIPPED_PARTIAL either way); only after_rip is
    # gated, and a parked application still drains once resolve runs.
    if job.status in (JobStatus.RIPPED, JobStatus.RIPPED_PARTIAL) and not flag_is_set(
        job.metadata_json, "unidentified"
    ):
        # Rip done, identity known: drain parked applications (an explicit
        # operator choice wins over the drive default), then auto-apply.
        # RIPPED_AWAITING_IDENTIFY deliberately skips this — transcode is
        # gated on identity; resolve runs the same hook when it runs.
        await after_rip(session, job, hub)

    return JobView.model_validate(job)
