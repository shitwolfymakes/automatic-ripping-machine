"""Drive listing + PATCH for `default_session_id` / `display_name` (Phase 8)."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_common import Drive, DriveStatus, Job, JobStatus, Session, User
from arm_common.schemas import DriveDiagnosticItem, DriveDiagnosticResponse, DriveRescanResponse, DriveUpdateRequest

router = APIRouter(prefix="/api/drives", tags=["drives"])

# A drive whose last media-status update is older than this is considered
# stale (its ripper likely stopped heart-beating). Deliberately looser than the
# 90s manual-trigger pre-check window (jobs.py `_MEDIA_STATUS_FRESHNESS`): that
# gate fast-fails a rip on a momentarily-quiet drive, whereas this is an
# operator-facing health view that shouldn't flap on a single missed heartbeat.
_STALE_AFTER = timedelta(minutes=5)


@router.get("", response_model=list[Drive])
async def list_drives(
    _: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
) -> list[Drive]:
    result = await session.execute(select(Drive).order_by(col(Drive.created_at).asc()))
    return list(result.scalars().all())


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
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> DriveRescanResponse:
    """Reconcile drive freshness from heartbeats. Backend-side only: the
    ripper owns hardware re-enumeration; this surfaces which registered drives
    are live vs stale based on their last media-status update.

    Kept as POST (not GET) even though it currently only reads: a real rescan
    triggers ripper-side hardware re-enumeration (a non-idempotent side effect),
    which a follow-up will add behind this same verb."""
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
    return DriveRescanResponse(online=online, stale=stale)


@router.patch("/{drive_id}", response_model=Drive)
async def update_drive(
    drive_id: str,
    req: DriveUpdateRequest,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> Drive:
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
    return drive


@router.delete("/{drive_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_drive(
    drive_id: str,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> None:
    drive = (await db.execute(select(Drive).where(col(Drive.id) == drive_id))).scalar_one_or_none()
    if drive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {drive_id}")
    # Refuse to delete a drive with an in-flight (RIPPING) job — same predicate
    # the ripper boot-probe uses. A live ripper re-registers the row on its next
    # startup (hostname upsert), so this only guards the active-rip case.
    active = (
        (await db.execute(select(Job).where(col(Job.drive_id) == drive_id).where(col(Job.status) == JobStatus.RIPPING)))
        .scalars()
        .all()
    )
    if active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot delete a drive with an in-flight job",
        )
    await db.delete(drive)
    await db.commit()
