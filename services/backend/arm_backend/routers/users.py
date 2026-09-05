"""Fixed-account user management: list the two accounts, toggle/set-password
for the guest. Deliberately no create/delete/role-change — the admin+guest
model is fixed (spec 2026-07-12-basic-user-management-design)."""

import logging

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_writer
from arm_backend.db import get_session
from arm_common.models.user import ADMIN_ROLE, User
from arm_common.schemas import UserDisabledRequest, UserPasswordSetRequest, UserView

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/users", tags=["users"])
_hasher = PasswordHasher()


def _to_view(u: User) -> UserView:
    return UserView(id=u.id, username=u.username, role=u.role, disabled=u.disabled, last_login_at=u.last_login_at)


async def _get_target(user_id: str, session: AsyncSession) -> User:
    user = (await session.execute(select(User).where(col(User.id) == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown user")
    if user.role == ADMIN_ROLE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="the admin account cannot be managed here")
    return user


@router.get("", response_model=list[UserView])
async def list_users(_: User = Depends(require_writer), session: AsyncSession = Depends(get_session)) -> list[UserView]:
    users = (await session.execute(select(User).order_by(col(User.username)))).scalars().all()
    return [_to_view(u) for u in users]


@router.patch("/{user_id}", response_model=UserView)
async def set_disabled(
    user_id: str,
    req: UserDisabledRequest,
    _: User = Depends(require_writer),
    session: AsyncSession = Depends(get_session),
) -> UserView:
    user = await _get_target(user_id, session)
    user.disabled = req.disabled
    await session.commit()
    await session.refresh(user)
    logger.info("user %s disabled=%s", user.username, user.disabled)
    return _to_view(user)


@router.post("/{user_id}/password")
async def set_password(
    user_id: str,
    req: UserPasswordSetRequest,
    _: User = Depends(require_writer),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    user = await _get_target(user_id, session)
    user.password_hash = _hasher.hash(req.new_password)
    user.password_must_change = False
    await session.commit()
    logger.info("password set for user %s", user.username)
    return {"ok": True}
