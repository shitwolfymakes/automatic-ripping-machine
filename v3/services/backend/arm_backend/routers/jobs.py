import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.db import get_session
from arm_common import Job, JobStatus
from arm_common.schemas import JobView, ResolveRequest

logger = logging.getLogger("arm_backend.routers.jobs")

# Phase 5: gate this router behind require_jwt(scopes=["jobs:resolve"]) once
# UI JWT auth lands. Today this is curl-testable for local dev only.
router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("/{job_id}/resolve", response_model=JobView)
async def resolve(
    job_id: str,
    req: ResolveRequest,
    session: AsyncSession = Depends(get_session),
) -> Job:
    job = (await session.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    if job.status != JobStatus.AWAITING_USER_ID:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job {job_id} is in status {job.status.value}, not awaiting_user_id",
        )

    job.title = req.title
    job.year = req.year
    job.metadata_json = req.metadata
    job.status = JobStatus.IDENTIFIED
    session.add(job)
    await session.commit()
    await session.refresh(job)

    logger.info("resolve job_id=%s -> identified title=%s", job.id, job.title)
    return job
