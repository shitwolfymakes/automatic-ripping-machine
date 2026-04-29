"""UI-side drive listing. Read-only in Phase 5."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_common import Drive, User

router = APIRouter(prefix="/api/drives", tags=["drives"])


@router.get("", response_model=list[Drive])
async def list_drives(
    _: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
) -> list[Drive]:
    result = await session.execute(select(Drive).order_by(col(Drive.created_at).asc()))
    return list(result.scalars().all())
