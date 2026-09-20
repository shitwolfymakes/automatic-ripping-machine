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
import io
import zipfile
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt, require_writer
from arm_backend.config import settings
from arm_backend.db import get_session
from arm_backend.routers.logs import LOG_DIR
from arm_common import Gpu, GpuStatus, SessionApplication, TranscodeTaskStatus, User
from arm_common.models import TranscodeTask
from arm_common.schemas import TranscodeStatsView, TranscodeTaskView, TranscodeWorkerView

router = APIRouter(prefix="/api/transcodes", tags=["transcodes"])


def _transcode_log_path(task_id: str) -> Path:
    # The dispatcher names each task's container log by the last 12 chars of the
    # task id (ARM_SERVICE_NAME = arm-transcode-<id[-12:]>; see
    # transcode_dispatcher._spawn_container). LOG_DIR is read at call time so
    # tests can monkeypatch it.
    return LOG_DIR / f"arm-transcode-{task_id[-12:]}.log"


async def _require_task(db: AsyncSession, task_id: str) -> TranscodeTask:
    row = (await db.execute(select(TranscodeTask).where(col(TranscodeTask.id) == task_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown transcode_task_id: {task_id}")
    return row


@router.get("", response_model=list[TranscodeTaskView])
async def list_transcodes(
    status_filter: TranscodeTaskStatus | None = Query(default=None, alias="status"),
    session_application_id: str | None = Query(default=None),
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> list[TranscodeTaskView]:
    stmt = select(TranscodeTask).order_by(col(TranscodeTask.created_at).desc())
    if status_filter is not None:
        stmt = stmt.where(col(TranscodeTask.status) == status_filter)
    if session_application_id is not None:
        stmt = stmt.where(col(TranscodeTask.session_application_id) == session_application_id)
    tasks = list((await db.execute(stmt)).scalars().all())

    # Resolve each task's job_id via its SessionApplication (single-table select,
    # FakeSession-safe — no JOIN).
    sa_ids = {t.session_application_id for t in tasks}
    job_by_sa: dict[str, str] = {}
    if sa_ids:
        sas = list(
            (await db.execute(select(SessionApplication).where(col(SessionApplication.id).in_(tuple(sa_ids)))))
            .scalars()
            .all()
        )
        job_by_sa = {sa.id: sa.job_id for sa in sas}

    def _view(t: TranscodeTask) -> TranscodeTaskView:
        tv = TranscodeTaskView.model_validate(t)
        tv.job_id = job_by_sa.get(t.session_application_id)
        return tv

    return [_view(t) for t in tasks]


@router.get("/stats", response_model=TranscodeStatsView)
async def transcode_stats(
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> TranscodeStatsView:
    tasks = list((await db.execute(select(TranscodeTask))).scalars().all())
    by_status: dict[str, int] = {}
    for t in tasks:
        key = t.status.value if hasattr(t.status, "value") else str(t.status)
        by_status[key] = by_status.get(key, 0) + 1
    gpus = list((await db.execute(select(Gpu))).scalars().all())
    gpus_available = len([g for g in gpus if g.status == GpuStatus.AVAILABLE])
    return TranscodeStatsView(
        tasks_by_status=by_status,
        total_tasks=len(tasks),
        gpus_total=len(gpus),
        gpus_available=gpus_available,
        max_parallel=settings.MAX_PARALLEL_TRANSCODES,
    )


@router.get("/workers", response_model=list[TranscodeWorkerView])
async def transcode_workers(
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> list[TranscodeWorkerView]:
    in_progress = list(
        (await db.execute(select(TranscodeTask).where(col(TranscodeTask.status) == TranscodeTaskStatus.IN_PROGRESS)))
        .scalars()
        .all()
    )
    gpus = list((await db.execute(select(Gpu))).scalars().all())
    gpu_by_task = {g.claimed_by_task_id: g.id for g in gpus if g.claimed_by_task_id is not None}
    return [
        TranscodeWorkerView(
            task_id=t.id,
            claimed_by=t.claimed_by,
            progress_pct=t.progress_pct,
            claim_heartbeat_at=t.claim_heartbeat_at,
            gpu_id=gpu_by_task.get(t.id),
            source_track_id=t.source_track_id,
            output_path=t.output_path,
        )
        for t in in_progress
    ]


@router.post("/{task_id}/retry", response_model=TranscodeTaskView)
async def retry_transcode(
    task_id: str,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> TranscodeTask:
    row = await _require_task(db, task_id)
    if row.status != TranscodeTaskStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"only FAILED tasks can be retried; task is {row.status.value}",
        )
    row.status = TranscodeTaskStatus.QUEUED
    row.progress_pct = 0
    row.last_error = None
    row.claimed_by = None
    row.claim_heartbeat_at = None
    # attempts intentionally preserved (audit trail); the dispatcher's QUEUED
    # spawn loop picks the task up on its next tick — no dispatcher change here.
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/{task_id}/log.zip")
async def download_transcode_log_zip(
    task_id: str,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> Response:
    await _require_task(db, task_id)
    path = _transcode_log_path(task_id)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no transcoder log for task {task_id}")
    lines: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            lines.append(line)
            if len(lines) >= settings.ARM_LOG_PER_FILE_HARD_CAP:
                break
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(path.name, "".join(lines))
    body = buf.getvalue()
    return Response(
        content=body,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="arm-transcode-{task_id[-12:]}.zip"',
            "Content-Length": str(len(body)),
        },
    )


@router.get("/{task_id}/log")
async def stream_transcode_log(
    task_id: str,
    limit: int | None = Query(default=None, ge=0),
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    await _require_task(db, task_id)
    path = _transcode_log_path(task_id)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no transcoder log for task {task_id}")
    eff_limit = settings.ARM_LOG_PER_FILE_DEFAULT if limit is None else limit
    cap = max(0, min(eff_limit, settings.ARM_LOG_PER_FILE_HARD_CAP))

    def gen() -> Iterator[bytes]:
        yielded = 0
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                out = line if line.endswith("\n") else line + "\n"
                yield out.encode("utf-8")
                yielded += 1
                if yielded >= cap:
                    return

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transcode(
    task_id: str,
    request: Request,
    _: User = Depends(require_writer),
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
