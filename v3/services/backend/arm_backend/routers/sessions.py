"""UI-side session listing. Read-only in Phase 5; CRUD lands in Phase 6."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_common import Session, User

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=list[Session])
async def list_sessions(
    _: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
) -> list[Session]:
    result = await session.execute(select(Session).order_by(col(Session.name).asc()))
    return list(result.scalars().all())
