"""Transcode-task list + delete.

`DELETE /api/transcodes/{id}` is a true delete: the row vanishes from
the DB whatever its prior state. For `IN_PROGRESS` we first kick off
`cancel_running` (WS cancel + grace + docker-stop fallback) so the
spawned container actually dies; the dispatcher's tail then deletes
the row instead of marking it FAILED. For other states the delete is
synchronous. In every case we emit `task.deleted` over WS so the UI
removes the row immediately.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_common import SessionApplication, TranscodeTaskStatus, User
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
async def delete_transcode(
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
                detail="transcode dispatcher unavailable; cannot stop a running task",
            )
        # Non-blocking. cancel_running's tail deletes the row + emits
        # task.deleted; we return 204 right away so the UI updates fast.
        asyncio.create_task(dispatcher.cancel_running(task_id))
        return

    # QUEUED or terminal (DONE/FAILED): delete synchronously and emit.
    application = (
        await db.execute(select(SessionApplication).where(col(SessionApplication.id) == row.session_application_id))
    ).scalar_one_or_none()
    job_id = application.job_id if application is not None else None
    track_id = row.source_track_id
    application_id = row.session_application_id

    await db.delete(row)

    hub = getattr(request.app.state, "ws_hub", None)
    if hub is not None:
        await hub.emit(
            topic="transcode.events",
            event_type="task.deleted",
            payload={"task_id": task_id, "session_application_id": application_id},
            job_id=job_id,
            track_id=track_id,
            session=db,
        )
    await db.commit()
