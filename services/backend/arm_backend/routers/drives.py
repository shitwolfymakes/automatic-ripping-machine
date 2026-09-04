"""Drive listing + PATCH for `default_session_id` / `display_name` (Phase 8)."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt, require_writer
from arm_backend.db import get_session
from arm_common import Drive, DriveLifecycle, DriveStatus, Job, JobStatus, Session, User
from arm_common.enums import TERMINAL_JOB_STATUSES
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
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> DriveDiagnosticResponse:
    drives = list((await db.execute(select(Drive).order_by(col(Drive.created_at).asc()))).scalars().all())
    now = datetime.now(timezone.utc)
    items: list[DriveDiagnosticItem] = []
    for d in drives:
        notes: list[str] = []
        healthy = True
        if d.media_status_at is None:
            healthy = False
            notes.append("no media-status heartbeat recorded")
        elif now - d.media_status_at > _STALE_AFTER:
            healthy = False
            notes.append("media-status heartbeat is stale")
        if d.status != DriveStatus.ONLINE:
            healthy = False
            notes.append(f"drive status is {d.status.value}")
        items.append(
            DriveDiagnosticItem(
                id=d.id,
                media_status=d.media_status,
                media_status_at=d.media_status_at,
                healthy=healthy,
                notes=notes,
            )
        )
    return DriveDiagnosticResponse(drives=items)


@router.post("/rescan", response_model=DriveRescanResponse)
async def rescan_drives(
    request: Request,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> DriveRescanResponse:
    """Run the host drive scan now (spec §2) and report the reconciled table.
    Also keeps the pre-existing heartbeat-freshness counts so the UI's
    online/stale badge is unchanged."""
    scanner = getattr(request.app.state, "drive_scanner", None)
    if scanner is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="drive scanner unavailable")
    summary = await scanner.scan_once(db)
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
    jobs = [j for j in (await db.execute(select(Job))).scalars().all() if j.drive_id == drive.id]
    return _to_view(drive, jobs)


@router.post("/{drive_id}/enroll", response_model=DriveView)
async def enroll_drive(
    drive_id: str,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> DriveView:
    """detected|ignored -> enrolled (spec §1). The operator says "this is ARM's".
    Plan 3 hooks the ripper manager here to create the container."""
    drive = await _load_drive(db, drive_id)
    _require_lifecycle(drive, "enroll", DriveLifecycle.DETECTED, DriveLifecycle.IGNORED)
    if not drive.present:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="cannot enroll a drive that is not present")
    drive.lifecycle = DriveLifecycle.ENROLLED
    drive.last_error = None
    db.add(drive)
    await db.commit()
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
    return await _view_for(db, drive)


@router.post("/{drive_id}/unenroll", response_model=DriveView)
async def unenroll_drive(
    drive_id: str,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> DriveView | Response:
    """enrolled -> detected (still plugged in) or gone (row deleted). Refused
    mid-rip. Plan 3 hooks the ripper manager here to stop the container."""
    drive = await _load_drive(db, drive_id)
    _require_lifecycle(drive, "unenroll", DriveLifecycle.ENROLLED)
    ripping = [
        j
        for j in (await db.execute(select(Job).where(col(Job.drive_id) == drive_id))).scalars().all()
        if j.status == JobStatus.RIPPING
    ]
    if ripping:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="cannot unenroll: a drive is ripping")
    if not drive.present:
        await db.delete(drive)
        await db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    drive.lifecycle = DriveLifecycle.DETECTED
    db.add(drive)
    await db.commit()
    return await _view_for(db, drive)
