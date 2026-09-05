"""Drive listing + PATCH for `default_session_id` / `display_name` (Phase 8)."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt, require_writer
from arm_backend.db import get_session
from arm_backend.drive_scanner import _tunables
from arm_backend.ripper_manager import RipperManager, RipperManagerError
from arm_common import Drive, DriveIdentityKind, DriveLifecycle, DriveStatus, Job, JobStatus, Session, User
from arm_common.enums import TERMINAL_JOB_STATUSES
from arm_common.models.user import ADMIN_ROLE
from arm_common.schemas import (
    DriveDiagnosticItem,
    DriveDiagnosticResponse,
    DriveCurrentJobView,
    DriveRescanResponse,
    DriveUpdateRequest,
    DriveView,
)

router = APIRouter(prefix="/api/drives", tags=["drives"])

# A drive whose last media-status update is older than this is considered
# stale (its ripper likely stopped heart-beating). Deliberately looser than the
# 90s manual-trigger pre-check window (jobs.py `_MEDIA_STATUS_FRESHNESS`): that
# gate fast-fails a rip on a momentarily-quiet drive, whereas this is an
# operator-facing health view that shouldn't flap on a single missed heartbeat.
_STALE_AFTER = timedelta(minutes=5)

_PORT_NOTE = "no by-id link — identified by port; a replug on another port creates a new drive"


def _aware(dt: datetime) -> datetime:
    """SQLite (and some drivers) hand back naive datetimes; everything here
    is compared against `datetime.now(timezone.utc)`, so treat naive as UTC —
    same convention as drive_scanner.reconcile_drives."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _current_job(jobs_for_drive: list[Job]) -> DriveCurrentJobView | None:
    active = [j for j in jobs_for_drive if j.status not in TERMINAL_JOB_STATUSES]
    if not active:
        return None
    latest = max(active, key=lambda j: j.created_at or datetime.min.replace(tzinfo=timezone.utc))
    return DriveCurrentJobView(id=latest.id, title=latest.title, status=latest.status)


def _to_view(drive: Drive, jobs_for_drive: list[Job]) -> DriveView:
    view = DriveView.model_validate(drive)
    view.current_job = _current_job(jobs_for_drive)
    return view


@router.get("", response_model=list[DriveView])
async def list_drives(
    _: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
) -> list[DriveView]:
    result = await session.execute(select(Drive).order_by(col(Drive.created_at).asc()))
    drives = list(result.scalars().all())
    # Fetch all jobs and group in Python — FakeSession cannot evaluate SQL GROUP BY.
    jobs = list((await session.execute(select(Job))).scalars().all())
    jobs_by_drive: dict[str, list[Job]] = {}
    for j in jobs:
        if j.drive_id is None:
            # Drive deleted after the fact (SET NULL) — belongs to no drive's view.
            continue
        jobs_by_drive.setdefault(j.drive_id, []).append(j)
    return [_to_view(d, jobs_by_drive.get(d.id, [])) for d in drives]


@router.get("/diagnostic", response_model=DriveDiagnosticResponse)
async def drive_diagnostic(
    request: Request,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> DriveDiagnosticResponse:
    """ "Look for issues": every drive row judged against the lifecycle model,
    plus the health of the parts that make the model work (scanner, ripper
    manager, the host's by-id mount). Never 503s — a missing subsystem is
    itself a finding."""
    drives = list((await db.execute(select(Drive).order_by(col(Drive.created_at).asc()))).scalars().all())
    now = datetime.now(timezone.utc)
    scanner = getattr(request.app.state, "drive_scanner", None)
    manager = getattr(request.app.state, "ripper_manager", None)

    items: list[DriveDiagnosticItem] = []
    for d in drives:
        notes: list[str] = []
        container: str | None = None
        if d.lifecycle is DriveLifecycle.ENROLLED:
            if d.media_status_at is None:
                notes.append("no media-status heartbeat recorded")
            elif now - _aware(d.media_status_at) > _STALE_AFTER:
                notes.append("media-status heartbeat is stale")
            if d.status is DriveStatus.OFFLINE:
                notes.append("drive is detached — reconnect it" if not d.present else "ripper heartbeat is stale")
            elif d.status is DriveStatus.ERROR:
                notes.append(f"error: {d.last_error or 'unknown'}")
            if manager is not None:
                state, current = await asyncio.to_thread(manager.container_status, d.id)
                if state == "missing":
                    container = "missing"
                    notes.append("no ripper container — restart the backend or re-enroll")
                elif state == "unknown":
                    container = "unknown"
                    notes.append("cannot inspect the ripper container")
                elif state != "running":
                    container = state
                    notes.append("ripper container is not running")
                elif current is False:
                    container = "stale-image"
                    notes.append("ripper runs an older image — it is recreated at the next backend restart while idle")
                else:
                    container = "running"
            healthy = not notes
        elif d.lifecycle is DriveLifecycle.DETECTED:
            if not d.present:
                seen = f"since {_aware(d.last_seen_at):%Y-%m-%d %H:%M} UTC" if d.last_seen_at else ""
                notes.append(f"not connected {seen}".rstrip())
            notes.append("not enrolled — enroll it on the Drives page to rip with it")
            healthy = d.present
        else:
            notes.append("ignored")
            healthy = True
        if d.identity_kind is DriveIdentityKind.PORT:
            notes.append(_PORT_NOTE)
            if d.lifecycle is DriveLifecycle.ENROLLED:
                healthy = False
        items.append(
            DriveDiagnosticItem(
                id=d.id,
                lifecycle=d.lifecycle,
                present=d.present,
                identity_kind=d.identity_kind,
                device_path=d.device_path,
                status=d.status,
                media_status=d.media_status,
                media_status_at=d.media_status_at,
                container=container,
                last_error=d.last_error,
                healthy=healthy,
                notes=notes,
            )
        )

    system: list[str] = []
    if scanner is None:
        system.append("drive scanner is not running")
    else:
        if scanner.last_error:
            system.append(f"last scan failed: {scanner.last_error}")
        interval, _prune_days = await _tunables(db)
        if scanner.last_scan_at is not None:
            age = int((now - _aware(scanner.last_scan_at)).total_seconds())
            if age > 3 * interval:
                system.append(f"last scan was {age}s ago — the scanner may be stuck")
        if not (Path(scanner.disk_root) / "by-id").is_dir():
            system.append("/host-disk/by-id is not mounted — drives cannot be identified")
    if manager is None:
        system.append("ripper manager is not running — enroll is unavailable")
    elif not manager.host_paths_set():
        system.append("ripper manager disabled: ARM_HOST_*_PATH not set")
    else:
        ok, detail = await asyncio.to_thread(manager.probe)
        if not ok:
            system.append(f"ripper manager: {detail}")
    return DriveDiagnosticResponse(drives=items, system=system)


@router.post("/rescan", response_model=DriveRescanResponse)
async def rescan_drives(
    request: Request,
    force: bool = Query(False, description="Prune detected drives that are not present right now (admin only)."),
    user: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> DriveRescanResponse:
    """Run the host drive scan now (spec §2) and report the reconciled table.
    Also keeps the pre-existing heartbeat-freshness counts so the UI's
    online/stale badge is unchanged. `force` = Force Rescan: the prune window
    is zero, so absent detected rows are removed immediately; enrolled and
    ignored rows are untouched."""
    if force and user.role != ADMIN_ROLE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="force rescan needs write access")
    scanner = getattr(request.app.state, "drive_scanner", None)
    if scanner is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="drive scanner unavailable")
    summary = await scanner.scan_once(db, prune_now=force)
    drives = list((await db.execute(select(Drive))).scalars().all())
    now = datetime.now(timezone.utc)
    online = 0
    stale = 0
    for d in drives:
        fresh = d.media_status_at is not None and (now - d.media_status_at) <= _STALE_AFTER
        if fresh and d.status == DriveStatus.ONLINE:
            online += 1
        else:
            stale += 1
    return DriveRescanResponse(
        online=online,
        stale=stale,
        detected=summary.detected,
        ignored=summary.ignored,
        enrolled=summary.enrolled,
        absent=summary.absent,
        pruned=summary.pruned,
    )


@router.patch("/{drive_id}", response_model=DriveView)
async def update_drive(
    drive_id: str,
    req: DriveUpdateRequest,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> DriveView:
    drive = (await db.execute(select(Drive).where(col(Drive.id) == drive_id))).scalar_one_or_none()
    if drive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {drive_id}")

    fields = req.model_dump(exclude_unset=True)

    if "default_session_id" in fields and fields["default_session_id"] is not None:
        target_id = fields["default_session_id"]
        target = (await db.execute(select(Session).where(col(Session.id) == target_id))).scalar_one_or_none()
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unknown session_id: {target_id}",
            )

    for key, value in fields.items():
        setattr(drive, key, value)

    db.add(drive)
    await db.commit()
    await db.refresh(drive)
    jobs = list((await db.execute(select(Job).where(col(Job.drive_id) == drive.id))).scalars().all())
    return _to_view(drive, jobs)


@router.delete("/{drive_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_drive(
    drive_id: str,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> None:
    drive = (await db.execute(select(Drive).where(col(Drive.id) == drive_id))).scalar_one_or_none()
    if drive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {drive_id}")
    if drive.lifecycle is DriveLifecycle.ENROLLED:
        # An enrolled row owns a ripper container; deleting it here would
        # silently orphan that container. unenroll (which stops/removes it)
        # is the only legal path off ENROLLED.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="unenroll the drive first")
    # Refuse to delete a drive with an in-flight (RIPPING) job — same predicate
    # the ripper boot-probe uses. A live ripper re-registers the row on its next
    # startup (hostname upsert), so this only guards the active-rip case; job
    # history is unaffected either way (jobs.drive_id is SET NULL on delete,
    # and Job.drive_serial keeps a permanent record of the physical drive —
    # see migration 0016_2_jobs_drive_serial).
    active = (
        (
            await db.execute(
                select(Job).where(col(Job.drive_id) == drive_id).where(col(Job.status) == JobStatus.RIPPING).limit(1)
            )
        )
        .scalars()
        .first()
    )
    if active is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot delete a drive with an in-flight job",
        )
    await db.delete(drive)
    await db.commit()


async def _load_drive(db: AsyncSession, drive_id: str) -> Drive:
    drive = (await db.execute(select(Drive).where(col(Drive.id) == drive_id))).scalar_one_or_none()
    if drive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {drive_id}")
    return drive


def _require_lifecycle(drive: Drive, op: str, *allowed: DriveLifecycle) -> None:
    if drive.lifecycle not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"cannot {op} a drive in lifecycle '{drive.lifecycle.value}'",
        )


async def _view_for(db: AsyncSession, drive: Drive) -> DriveView:
    jobs = list((await db.execute(select(Job).where(col(Job.drive_id) == drive.id))).scalars().all())
    return _to_view(drive, jobs)


def _manager(request: Request) -> RipperManager:
    manager: RipperManager | None = getattr(request.app.state, "ripper_manager", None)
    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ripper manager unavailable: docker socket not available",
        )
    if not manager.host_paths_set():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ripper manager disabled: ARM_HOST_*_PATH not set",
        )
    return manager


def _drive_lock(request: Request, drive_id: str) -> asyncio.Lock:
    """One `asyncio.Lock` per drive, lazily created and cached on
    `app.state` for the process lifetime. Guards enroll/unenroll against a
    concurrent request racing the same row (double-POST, or a retried
    client): the loser waits for the winner's docker call + commit to
    finish rather than clobbering it mid-flight."""
    locks: dict[str, asyncio.Lock] = request.app.state.__dict__.setdefault("drive_locks", {})
    return locks.setdefault(drive_id, asyncio.Lock())


@router.post("/{drive_id}/enroll", response_model=DriveView)
async def enroll_drive(
    drive_id: str,
    request: Request,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> DriveView:
    """detected|ignored -> enrolled (spec §1): the operator says "this is
    ARM's". Creates (or adopts) the ripper container (spec §3). A docker
    failure reverts the row and surfaces the error in `last_error` + the
    response.

    Serialized per-drive (see `_drive_lock`): a second enroll/unenroll on the
    same drive_id while this one is still running its docker call waits for
    it to finish and commit, instead of reading + clobbering a stale row."""
    async with _drive_lock(request, drive_id):
        drive = await _load_drive(db, drive_id)
        manager = _manager(request)
        _require_lifecycle(drive, "enroll", DriveLifecycle.DETECTED, DriveLifecycle.IGNORED)
        if not drive.present:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="cannot enroll a drive that is not present"
            )
        previous = drive.lifecycle
        # Flip first so the ripper's register-by-id (which requires `enrolled`)
        # cannot race the container start.
        drive.lifecycle = DriveLifecycle.ENROLLED
        drive.last_error = None
        db.add(drive)
        await db.commit()
        try:
            await asyncio.to_thread(manager.ensure_running, drive)
        except RipperManagerError as exc:
            drive.lifecycle = previous
            drive.last_error = str(exc)
            db.add(drive)
            await db.commit()
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        # The row was committed before the docker call; register may have
        # rewritten hostname/device_path meanwhile and updated_at is expired.
        await db.refresh(drive)
        return await _view_for(db, drive)


@router.post("/{drive_id}/ignore", response_model=DriveView)
async def ignore_drive(
    drive_id: str,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> DriveView:
    """detected -> ignored: "not ARM's". Persisted so the scanner never re-nags,
    and never pruned."""
    drive = await _load_drive(db, drive_id)
    _require_lifecycle(drive, "ignore", DriveLifecycle.DETECTED)
    drive.lifecycle = DriveLifecycle.IGNORED
    db.add(drive)
    await db.commit()
    await db.refresh(drive)  # updated_at is server-generated (onupdate) and expired after the flush
    return await _view_for(db, drive)


@router.post("/{drive_id}/unignore", response_model=DriveView)
async def unignore_drive(
    drive_id: str,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> DriveView:
    drive = await _load_drive(db, drive_id)
    _require_lifecycle(drive, "unignore", DriveLifecycle.IGNORED)
    drive.lifecycle = DriveLifecycle.DETECTED
    db.add(drive)
    await db.commit()
    await db.refresh(drive)  # updated_at is server-generated (onupdate) and expired after the flush
    return await _view_for(db, drive)


@router.post(
    "/{drive_id}/unenroll",
    response_model=DriveView,
    responses={204: {"description": "Drive row deleted (detected-origin drive)"}},
)
async def unenroll_drive(
    drive_id: str,
    request: Request,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> DriveView | Response:
    """enrolled -> detected (still plugged in) or gone (row deleted). Refused
    mid-rip. Stops (or removes) the ripper container (spec §3) before the
    lifecycle changes; a docker failure leaves the row `enrolled`.

    Serialized per-drive (see `_drive_lock`) for the same reason as enroll."""
    async with _drive_lock(request, drive_id):
        drive = await _load_drive(db, drive_id)
        manager = _manager(request)
        _require_lifecycle(drive, "unenroll", DriveLifecycle.ENROLLED)
        ripping = (
            (
                await db.execute(
                    select(Job)
                    .where(col(Job.drive_id) == drive_id)
                    .where(col(Job.status) == JobStatus.RIPPING)
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if ripping is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="cannot unenroll: a drive is ripping")
        try:
            await asyncio.to_thread(manager.remove, drive.id)
        except RipperManagerError as exc:
            drive.last_error = str(exc)
            db.add(drive)
            await db.commit()
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        if not drive.present:
            await db.delete(drive)
            await db.commit()
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        drive.lifecycle = DriveLifecycle.DETECTED
        db.add(drive)
        await db.commit()
        await db.refresh(drive)  # updated_at is server-generated (onupdate) and expired after the flush
        return await _view_for(db, drive)
