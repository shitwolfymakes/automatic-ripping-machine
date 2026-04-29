"""REST authentication and authorization deps.

Two principal types co-exist on the same `Authorization: Bearer ...` header:

* Service token — shared `ARM_SERVICE_TOKEN` from `.env`. Used by ripper /
  transcoder containers. Routes that require it use `Depends(require_service_token)`.
* UI JWT — HS256, signed with `config.session_signing_key`, issued by
  `POST /api/auth/login`. Used by the browser SPA. Routes that require it
  use `Depends(require_jwt)`.

The two are mutually exclusive: `require_jwt` rejects values that match
the service token, and `require_service_token` rejects values that look
like a JWT (3 dot-separated segments). This enforces the
"UI endpoints reject service token, ripper endpoints reject UI JWT" rule
from [05-cross-cutting.md § Authorization rules](../../../docs/arch/05-cross-cutting.md#authorization-rules).
"""

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.config import settings
from arm_backend.db import get_session
from arm_backend.jwt_utils import verify_access_token
from arm_common import Drive, Job, User
from arm_common.models import Track


def check_service_token(token: str) -> bool:
    """Constant-time-ish service-token compare. Used by both the REST dep and the WS auth path."""
    return bool(token) and token == settings.ARM_SERVICE_TOKEN


def looks_like_jwt(token: str) -> bool:
    """A signed JWT has exactly two `.` separators (header.payload.sig)."""
    return bool(token) and token.count(".") == 2


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    return authorization.removeprefix("Bearer ").strip()


async def require_service_token(authorization: str | None = Header(default=None)) -> None:
    token = _extract_bearer(authorization)
    if looks_like_jwt(token):
        # A JWT-shaped token reaching a ripper/transcoder endpoint is the
        # explicit "UI JWT used in service path" case; reject deterministically.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="service endpoint requires service token, not UI JWT",
        )
    if not check_service_token(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid service token")


# Routes that a `password_must_change=true` user is still allowed to hit.
# Path-prefix match against `request.url.path`.
_MUST_CHANGE_WHITELIST: tuple[str, ...] = (
    "/api/auth/password",
    "/api/auth/logout",
)


async def require_jwt(
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    token = _extract_bearer(authorization)
    if not looks_like_jwt(token):
        # Service-token presented to a UI endpoint.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="UI endpoint requires user JWT, not service token",
        )
    signing_key: bytes | None = getattr(request.app.state, "signing_key", None)
    if signing_key is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="signing key not initialized",
        )
    try:
        payload = verify_access_token(token, signing_key)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid jwt: {exc}") from exc

    user_id = payload.get("sub")
    if not isinstance(user_id, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="jwt missing sub")
    user = (await session.execute(select(User).where(col(User.id) == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unknown user")

    if user.password_must_change and not _path_in_whitelist(request.url.path):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="password change required",
        )
    return user


def _path_in_whitelist(path: str) -> bool:
    return any(path.startswith(p) for p in _MUST_CHANGE_WHITELIST)


async def _verify_drive_owner(session: AsyncSession, drive_id: str, hostname_header: str | None) -> None:
    if not hostname_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing X-ARM-Hostname header",
        )
    drive = (await session.execute(select(Drive).where(col(Drive.id) == drive_id))).scalar_one_or_none()
    if drive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {drive_id}")
    if drive.hostname != hostname_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="hostname does not own this drive",
        )


async def require_drive_owner_by_job(
    job_id: str,
    _: None = Depends(require_service_token),
    x_arm_hostname: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Job:
    job = (await session.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    await _verify_drive_owner(session, job.drive_id, x_arm_hostname)
    return job


async def require_drive_owner_by_track(
    track_id: str,
    _: None = Depends(require_service_token),
    x_arm_hostname: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Track:
    track = (await session.execute(select(Track).where(col(Track.id) == track_id))).scalar_one_or_none()
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown track_id: {track_id}")
    job = (await session.execute(select(Job).where(col(Job.id) == track.job_id))).scalar_one()
    await _verify_drive_owner(session, job.drive_id, x_arm_hostname)
    return track
