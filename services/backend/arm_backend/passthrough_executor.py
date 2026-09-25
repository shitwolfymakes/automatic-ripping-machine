"""In-process passthrough execution (TranscodeTool.NONE / no-preset tasks).

Passthrough is a file move, not an encode, so the backend performs it
itself instead of spawning a transcoder container (no-transcode-mode spec).
The task lifecycle mirrors the container path exactly, so the transcodes UI
and session rollups cannot tell the difference. The blocking move runs in a
thread; a large cross-mount copy must not stall the event loop.

NFS note: writes happen as the BACKEND's uid. The deployment doc requires
the backend PUID to have write access to /media; when ARM_TRANSCODE_PUID is
set we chown best-effort after the move (a root-squashed export makes that
a harmless no-op).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.config import Settings
from arm_common import (
    SessionApplication,
    Track,
    TranscodeTask,
    TranscodeTaskStatus,
    with_log_context,
)
from arm_common.fileops import transcode_none

if TYPE_CHECKING:
    from arm_backend.ws.hub import WSHub

logger = logging.getLogger("arm_backend.passthrough_executor")

IN_PROCESS_CLAIMANT = "backend-inprocess"


async def execute_passthrough_task(db: AsyncSession, task: TranscodeTask, hub: "WSHub", settings: Settings) -> bool:
    """Run one QUEUED passthrough task to completion in-process.

    Mirrors the container path's lifecycle exactly (claim fields,
    task.completed / task.failed WS events, application aggregation).
    Returns True on DONE, False on FAILED. Caller commits.
    """
    application = (
        await db.execute(select(SessionApplication).where(col(SessionApplication.id) == task.session_application_id))
    ).scalar_one_or_none()
    job_id = application.job_id if application is not None else None
    with with_log_context(
        job_id=job_id, track_id=task.source_track_id, session_application_id=task.session_application_id
    ):
        track = (await db.execute(select(Track).where(col(Track.id) == task.source_track_id))).scalar_one_or_none()

        task.status = TranscodeTaskStatus.IN_PROGRESS
        task.claimed_by = IN_PROCESS_CLAIMANT
        task.claim_heartbeat_at = datetime.now(UTC)
        task.attempts += 1
        await db.flush()

        error: str | None = None
        size: int | None = None
        if track is None or not track.output_path:
            error = "source track has no output_path on disk; rip not complete or raw deleted"
        elif not task.output_path:
            error = "task has no output_path"
        else:
            final = Path(settings.MEDIA_ROOT) / task.output_path
            try:
                size = await asyncio.to_thread(transcode_none, Path(track.output_path), final)
                if settings.ARM_TRANSCODE_PUID:
                    _best_effort_chown(final, settings)
            except OSError as exc:
                error = f"{type(exc).__name__}: {exc}"[:300]

        if error is None:
            task.status = TranscodeTaskStatus.DONE
            task.progress_pct = 100
            task.last_error = None
            event_type, payload_extra = "task.completed", {"output_path": task.output_path, "size_bytes": size}
            logger.info("passthrough complete task_id=%s output=%s", task.id, task.output_path)
        else:
            task.status = TranscodeTaskStatus.FAILED
            task.last_error = error
            event_type, payload_extra = "task.failed", {"last_error": error}
            logger.error("passthrough failed task_id=%s: %s", task.id, error)
        await db.flush()

        await hub.emit(
            topic="transcode.events",
            event_type=event_type,
            payload={"task_id": task.id, "session_application_id": task.session_application_id, **payload_extra},
            job_id=job_id,
            track_id=task.source_track_id,
            session=db,
        )
        if application is not None:
            from arm_backend.transcode_apply import aggregate_session_application  # noqa: PLC0415 - matches dispatcher's lazy import

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
        return error is None


def _best_effort_chown(final: Path, settings: Settings) -> None:
    try:
        uid = int(settings.ARM_TRANSCODE_PUID)
        gid = int(settings.ARM_TRANSCODE_PGID) if settings.ARM_TRANSCODE_PGID else -1
        os.chown(final, uid, gid)
    except (OSError, ValueError) as exc:
        logger.debug("post-move chown skipped: %s", exc)
