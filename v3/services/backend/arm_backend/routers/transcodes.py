"""Transcode-task list + cancel.

`QUEUED` tasks soft-cancel synchronously (status → FAILED with
`last_error="cancelled by user"`). `IN_PROGRESS` tasks delegate to the
dispatcher's WS-cancel-then-docker-stop flow — non-blocking; the
dispatcher emits `task.failed` over WS when the transcoder dies.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
    request: Request,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> None:
    row = (await db.execute(select(TranscodeTask).where(col(TranscodeTask.id) == task_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown transcode_task_id: {task_id}")

    if row.status == TranscodeTaskStatus.IN_PROGRESS:
        dispatcher = getattr(request.app.state, "transcode_dispatcher", None)
        if dispatcher is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="transcode dispatcher unavailable; cannot cancel a running task",
            )
        # Non-blocking: WS cancel + grace + docker-stop fallback all happen
        # off the request path. The UI sees task.failed via WS when it lands.
        asyncio.create_task(dispatcher.cancel_running(task_id))
        return

    if row.status != TranscodeTaskStatus.QUEUED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task already terminal in status={row.status.value}",
        )
    row.status = TranscodeTaskStatus.FAILED
    row.last_error = "cancelled by user"
    await db.commit()
