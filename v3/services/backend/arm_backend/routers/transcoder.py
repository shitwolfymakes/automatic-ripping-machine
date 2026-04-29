"""Transcoder ↔ Backend REST endpoints (Phase 7).

Five endpoints per `03-protocol.md § Transcode container ↔ Backend`:
- `POST /register` — bootstrap; transcoder receives the task, session, preset,
  source track, and the `raw_input_path` it should read from.
- `POST /tasks/{task_id}/claim` — atomic CAS to `in_progress`. First claim
  on a session_application also flips the application to RUNNING and emits
  `session.started`.
- `PATCH /tasks/{task_id}/heartbeat` — `claim_heartbeat_at` + `progress_pct`.
  The transcoder also publishes `transcode.progress.{task_id}` over WS at
  ~1 Hz; the REST heartbeat is the durable surface the stale-claim sweep
  reads.
- `PATCH /tasks/{task_id}/complete` — `done`. Aggregator runs.
- `PATCH /tasks/{task_id}/fail` — `failed` + `last_error`. Aggregator runs.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_service_token
from arm_backend.db import get_session
from arm_backend.transcode_apply import aggregate_session_application
from arm_backend.ws import WSHub
from arm_common import (
    Session,
    SessionApplication,
    SessionApplicationStatus,
    TranscodePreset,
    TranscodeTask,
    TranscodeTaskStatus,
)
from arm_common.models import Track
from arm_common.schemas import (
    ClaimTaskResponse,
    CompleteTaskRequest,
    FailTaskRequest,
    HeartbeatRequest,
    RegisterTranscoderRequest,
    RegisterTranscoderResponse,
    SessionView,
    TrackView,
    TranscodePresetView,
    TranscodeTaskView,
)

logger = logging.getLogger("arm_backend.routers.transcoder")

router = APIRouter(prefix="/api/transcoder", tags=["transcoder"], dependencies=[Depends(require_service_token)])


def _get_hub(request: Request) -> WSHub:
    hub: WSHub = request.app.state.ws_hub
    return hub


async def _load_task(db: AsyncSession, task_id: str) -> TranscodeTask:
    row = (await db.execute(select(TranscodeTask).where(col(TranscodeTask.id) == task_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown transcode_task_id: {task_id}")
    return row


def _require_owner(task: TranscodeTask, hostname: str | None) -> None:
    if not hostname:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing X-ARM-Hostname header")
    if task.claimed_by != hostname:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"task is not claimed by {hostname} (claimed_by={task.claimed_by})",
        )


@router.post("/register", response_model=RegisterTranscoderResponse)
async def register(
    req: RegisterTranscoderRequest,
    db: AsyncSession = Depends(get_session),
) -> RegisterTranscoderResponse:
    task = await _load_task(db, req.task_id)
    if task.status not in (TranscodeTaskStatus.QUEUED, TranscodeTaskStatus.IN_PROGRESS):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task is in terminal status={task.status.value}",
        )
    if (
        task.claimed_by is not None
        and task.claimed_by != req.hostname
        and task.status == TranscodeTaskStatus.IN_PROGRESS
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task is claimed by a different host: {task.claimed_by}",
        )

    application = (
        await db.execute(select(SessionApplication).where(col(SessionApplication.id) == task.session_application_id))
    ).scalar_one()
    sess = (await db.execute(select(Session).where(col(Session.id) == application.session_id))).scalar_one()
    transcode_preset: TranscodePreset | None = None
    if sess.transcode_preset_id is not None:
        transcode_preset = (
            await db.execute(select(TranscodePreset).where(col(TranscodePreset.id) == sess.transcode_preset_id))
        ).scalar_one_or_none()
    track = (await db.execute(select(Track).where(col(Track.id) == task.source_track_id))).scalar_one()

    if not track.output_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"source track {track.id} has no output_path on disk; rip not yet complete",
        )

    media_root = request_media_root()
    return RegisterTranscoderResponse(
        task=TranscodeTaskView.model_validate(task),
        session=SessionView.model_validate(sess),
        transcode_preset=TranscodePresetView.model_validate(transcode_preset) if transcode_preset is not None else None,
        source_track=TrackView.model_validate(track),
        raw_input_path=track.output_path,
        media_root=media_root,
    )


def request_media_root() -> str:
    # Imported lazily so test settings don't have to be hot-loaded just to import the router.
    from arm_backend.config import settings

    return settings.MEDIA_ROOT


@router.post("/tasks/{task_id}/claim", response_model=ClaimTaskResponse)
async def claim(
    task_id: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    x_arm_hostname: str | None = Header(default=None),
    hub: WSHub = Depends(_get_hub),
) -> ClaimTaskResponse:
    if not x_arm_hostname:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing X-ARM-Hostname header")

    task = await _load_task(db, task_id)
    if task.status == TranscodeTaskStatus.IN_PROGRESS and task.claimed_by == x_arm_hostname:
        # Idempotent re-claim by the same host — return the row unchanged.
        return ClaimTaskResponse(task=TranscodeTaskView.model_validate(task))
    if task.status != TranscodeTaskStatus.QUEUED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task is in status={task.status.value}, not queued",
        )

    # The dispatcher's `FOR UPDATE SKIP LOCKED` spawn loop guarantees one
    # container per row, so the race window here is small. The natural-key
    # idempotency check above (same hostname + IN_PROGRESS) absorbs the
    # case where the transcoder restarts and re-claims its own task.
    now = datetime.now(UTC)
    task.status = TranscodeTaskStatus.IN_PROGRESS
    task.claimed_by = x_arm_hostname
    task.claim_heartbeat_at = now
    task.attempts = (task.attempts or 0) + 1
    task.progress_pct = 0
    await db.flush()

    application = (
        await db.execute(select(SessionApplication).where(col(SessionApplication.id) == task.session_application_id))
    ).scalar_one()
    if application.status == SessionApplicationStatus.QUEUED:
        application.status = SessionApplicationStatus.RUNNING
        await db.flush()
        await hub.emit(
            topic="transcode.events",
            event_type="session.started",
            payload={
                "session_application_id": application.id,
                "session_id": application.session_id,
                "job_id": application.job_id,
            },
            job_id=application.job_id,
            session=db,
        )

    await hub.emit(
        topic="transcode.events",
        event_type="task.started",
        payload={
            "task_id": task.id,
            "session_application_id": task.session_application_id,
            "claimed_by": task.claimed_by,
            "attempts": task.attempts,
        },
        job_id=application.job_id,
        track_id=task.source_track_id,
        session=db,
    )
    await db.commit()
    await db.refresh(task)
    logger.info("transcode claim task_id=%s host=%s attempts=%d", task.id, task.claimed_by, task.attempts)
    return ClaimTaskResponse(task=TranscodeTaskView.model_validate(task))


@router.patch("/tasks/{task_id}/heartbeat", response_model=TranscodeTaskView)
async def heartbeat(
    task_id: str,
    req: HeartbeatRequest,
    db: AsyncSession = Depends(get_session),
    x_arm_hostname: str | None = Header(default=None),
) -> TranscodeTask:
    task = await _load_task(db, task_id)
    _require_owner(task, x_arm_hostname)
    if task.status != TranscodeTaskStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task is in status={task.status.value}, not in_progress",
        )
    task.claim_heartbeat_at = datetime.now(UTC)
    task.progress_pct = req.progress_pct
    await db.commit()
    await db.refresh(task)
    return task


@router.patch("/tasks/{task_id}/complete", response_model=TranscodeTaskView)
async def complete(
    task_id: str,
    req: CompleteTaskRequest,
    db: AsyncSession = Depends(get_session),
    x_arm_hostname: str | None = Header(default=None),
    hub: WSHub = Depends(_get_hub),
) -> TranscodeTask:
    task = await _load_task(db, task_id)
    _require_owner(task, x_arm_hostname)
    if task.status != TranscodeTaskStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task is in status={task.status.value}, not in_progress",
        )
    task.status = TranscodeTaskStatus.DONE
    task.progress_pct = 100
    task.output_path = req.output_path
    task.last_error = None
    await db.flush()

    application = (
        await db.execute(select(SessionApplication).where(col(SessionApplication.id) == task.session_application_id))
    ).scalar_one()
    job_id = application.job_id

    await hub.emit(
        topic="transcode.events",
        event_type="task.completed",
        payload={
            "task_id": task.id,
            "session_application_id": task.session_application_id,
            "output_path": task.output_path,
            "size_bytes": req.size_bytes,
            "duration_seconds": req.duration_seconds,
            "sha256": req.sha256,
        },
        job_id=job_id,
        track_id=task.source_track_id,
        session=db,
    )

    outcome = await aggregate_session_application(db, application)
    if outcome.event_type is not None:
        await hub.emit(
            topic="transcode.events",
            event_type=outcome.event_type,
            payload={
                "session_application_id": application.id,
                "session_id": application.session_id,
                "job_id": application.job_id,
                "status": application.status.value,
            },
            job_id=job_id,
            session=db,
        )
    await db.commit()
    await db.refresh(task)
    logger.info("transcode complete task_id=%s output=%s", task.id, task.output_path)
    return task


@router.patch("/tasks/{task_id}/fail", response_model=TranscodeTaskView)
async def fail(
    task_id: str,
    req: FailTaskRequest,
    db: AsyncSession = Depends(get_session),
    x_arm_hostname: str | None = Header(default=None),
    hub: WSHub = Depends(_get_hub),
) -> TranscodeTask:
    task = await _load_task(db, task_id)
    _require_owner(task, x_arm_hostname)
    if task.status != TranscodeTaskStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"task is in status={task.status.value}, not in_progress",
        )
    task.status = TranscodeTaskStatus.FAILED
    task.last_error = req.last_error
    await db.flush()

    application = (
        await db.execute(select(SessionApplication).where(col(SessionApplication.id) == task.session_application_id))
    ).scalar_one()
    job_id = application.job_id

    await hub.emit(
        topic="transcode.events",
        event_type="task.failed",
        payload={
            "task_id": task.id,
            "session_application_id": task.session_application_id,
            "last_error": task.last_error,
        },
        job_id=job_id,
        track_id=task.source_track_id,
        session=db,
    )

    outcome = await aggregate_session_application(db, application)
    if outcome.event_type is not None:
        await hub.emit(
            topic="transcode.events",
            event_type=outcome.event_type,
            payload={
                "session_application_id": application.id,
                "session_id": application.session_id,
                "job_id": application.job_id,
                "status": application.status.value,
            },
            job_id=job_id,
            session=db,
        )
    await db.commit()
    await db.refresh(task)
    logger.warning("transcode fail task_id=%s last_error=%s", task.id, task.last_error)
    return task
