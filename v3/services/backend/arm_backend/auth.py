from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.config import settings
from arm_backend.db import get_session
from arm_common import Drive, Job
from arm_common.models import Track


async def require_service_token(authorization: str | None = Header(default=None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.ARM_SERVICE_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid service token")


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
