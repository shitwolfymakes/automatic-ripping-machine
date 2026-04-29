"""Transcode-task list + queue cancel.

Phase 6 only handles `QUEUED` cancellation; cancelling an `IN_PROGRESS`
task requires the docker-py kill flow that lands in Phase 7.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_common import TranscodeTaskStatus, User
from arm_common.models import TranscodeTask
from arm_common.schemas import TranscodeTaskView

router = APIRouter(prefix="/api/transcodes", tags=["transcodes"])


@router.get("", response_model=list[TranscodeTaskView])
async def list_transcodes(
    status_filter: TranscodeTaskStatus | None = Query(default=None, alias="status"),
    session_application_id: str | None = Query(default=None),
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> list[TranscodeTask]:
    stmt = select(TranscodeTask).order_by(col(TranscodeTask.created_at).desc())
    if status_filter is not None:
        stmt = stmt.where(col(TranscodeTask.status) == status_filter)
    if session_application_id is not None:
        stmt = stmt.where(col(TranscodeTask.session_application_id) == session_application_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_transcode(
    task_id: str,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> None:
    row = (await db.execute(select(TranscodeTask).where(col(TranscodeTask.id) == task_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown transcode_task_id: {task_id}")
    if row.status == TranscodeTaskStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="running cancel lands in Phase 7; this endpoint only cancels queued tasks",
        )
    if row.status != TranscodeTaskStatus.QUEUED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task already terminal in status={row.status.value}",
        )
    row.status = TranscodeTaskStatus.FAILED
    row.last_error = "cancelled by user"
    await db.commit()
