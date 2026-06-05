"""Drive listing + PATCH for `default_session_id` / `display_name` (Phase 8)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_common import Drive, Session, User
from arm_common.schemas import DriveUpdateRequest

router = APIRouter(prefix="/api/drives", tags=["drives"])


@router.get("", response_model=list[Drive])
async def list_drives(
    _: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
) -> list[Drive]:
    result = await session.execute(select(Drive).order_by(col(Drive.created_at).asc()))
    return list(result.scalars().all())


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
