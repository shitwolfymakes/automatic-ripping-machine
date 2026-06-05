"""Login, logout, password-change.

`POST /api/auth/login` returns the JWT plus the `password_must_change`
flag. The UI redirects to `/change-password` while that flag is true,
and the server-side `require_jwt` dep enforces the same gate by 403'ing
on every UI endpoint except `/api/auth/password` and `/api/auth/logout`.
Logout is no-op server-side: clients drop the token themselves.
"""

import logging
from datetime import datetime, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_backend.jwt_utils import issue_access_token
from arm_common import User
from arm_common.schemas import LoginRequest, LoginResponse, PasswordChangeRequest

logger = logging.getLogger("arm_backend.routers.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

_hasher = PasswordHasher()


@router.post("/login", response_model=LoginResponse)
async def login(
    req: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> LoginResponse:
    user = (await session.execute(select(User).where(col(User.username) == req.username))).scalar_one_or_none()
    # Single generic 401 on any failure path — never tell the client which one.
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    try:
        _hasher.verify(user.password_hash, req.password)
    except VerifyMismatchError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials") from exc

    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = _hasher.hash(req.password)

    user.last_login_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(user)

    signing_key: bytes = request.app.state.signing_key
    token, expires_at = issue_access_token(user.id, user.username, signing_key)
    logger.info("login user_id=%s username=%s", user.id, user.username)
    return LoginResponse(
        access_token=token,
        expires_at=expires_at,
        password_must_change=user.password_must_change,
    )


@router.post("/logout")
async def logout() -> dict[str, bool]:
    # No server-side token blocklist in v3.0 — client drops the token.
    return {"ok": True}


@router.post("/password")
async def change_password(
    req: PasswordChangeRequest,
    user: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    try:
        _hasher.verify(user.password_hash, req.current_password)
    except VerifyMismatchError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="current password incorrect") from exc

    if req.current_password == req.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="new password must differ from current",
        )

    user.password_hash = _hasher.hash(req.new_password)
    user.password_must_change = False
    await session.commit()
    logger.info("password_changed user_id=%s", user.id)
    return {"ok": True}
