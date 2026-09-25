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
    Returns True on DONE, False on FAILED.

    Commits internally at two points instead of leaving the commit to the
    caller: once right after the claim (before the move), and once after
    the terminal state + events are written. The dispatcher tick's
    `SELECT ... FOR UPDATE SKIP LOCKED` holds row locks on every queued row
    it fetched; under the shipped compose layout /raw and /media are
    separate bind mounts, so the "move" is actually a full cross-mount copy
    (`os.rename` fails EXDEV, `transcode_none` falls back to copy+unlink),
    slow enough that holding those locks (and a long-open transaction) across
    it would stall a freshly spawned encode container's `/claim` call past
    its HTTP timeout. Committing the claim first ends that locking
    transaction before any blocking I/O runs.

    Because the claim is durably committed before the move, the row can be
    deleted out from under this function by a concurrent `cancel_running`
    (a different session) while the copy is in flight. Before writing the
    terminal state we re-fetch the row by id; if it's gone, we log and
    return cleanly instead of resurrecting a cancelled task.
    """
    application = (
        await db.execute(select(SessionApplication).where(col(SessionApplication.id) == task.session_application_id))
    ).scalar_one_or_none()
    job_id = application.job_id if application is not None else None
    task_id = task.id
    source_track_id = task.source_track_id
    session_application_id = task.session_application_id
    with with_log_context(job_id=job_id, track_id=source_track_id, session_application_id=session_application_id):
        track = (await db.execute(select(Track).where(col(Track.id) == source_track_id))).scalar_one_or_none()
        track_output_path = track.output_path if track is not None else None
        task_output_path = task.output_path

        task.status = TranscodeTaskStatus.IN_PROGRESS
        task.claimed_by = IN_PROCESS_CLAIMANT
        task.claim_heartbeat_at = datetime.now(UTC)
        task.attempts += 1
        # Commit the claim before the (possibly slow, cross-mount) file
        # move so the tick's FOR UPDATE row locks aren't held across
        # blocking I/O (see docstring).
        await db.commit()

        error: str | None = None
        size: int | None = None
        if track is None or not track_output_path:
            error = "source track has no output_path on disk; rip not complete or raw deleted"
        elif not task_output_path:
            error = "task has no output_path"
        else:
            final = Path(settings.MEDIA_ROOT) / task_output_path
            try:
                size = await asyncio.to_thread(transcode_none, Path(track_output_path), final)
                if settings.ARM_TRANSCODE_PUID:
                    _best_effort_chown(final, settings)
            except OSError as exc:
                error = f"{type(exc).__name__}: {exc}"[:300]

        # Re-fetch: cancel_running (a different session) may have deleted
        # this row while the move was in flight.
        fresh_task = (
            await db.execute(select(TranscodeTask).where(col(TranscodeTask.id) == task_id))
        ).scalar_one_or_none()
        if fresh_task is None:
            logger.info("passthrough task_id=%s deleted mid-move; skipping terminal update", task_id)
            return error is None

        if error is None:
            fresh_task.status = TranscodeTaskStatus.DONE
            fresh_task.progress_pct = 100
            fresh_task.last_error = None
            event_type, payload_extra = "task.completed", {"output_path": task_output_path, "size_bytes": size}
            logger.info("passthrough complete task_id=%s output=%s", task_id, task_output_path)
        else:
            fresh_task.status = TranscodeTaskStatus.FAILED
            fresh_task.last_error = error
            event_type, payload_extra = "task.failed", {"last_error": error}
            logger.error("passthrough failed task_id=%s: %s", task_id, error)
        await db.flush()

        await hub.emit(
            topic="transcode.events",
            event_type=event_type,
            payload={"task_id": task_id, "session_application_id": session_application_id, **payload_extra},
            job_id=job_id,
            track_id=source_track_id,
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
        # Commit the terminal state (+ any aggregate transition) as its own
        # transaction, separate from the claim commit above.
        await db.commit()
        return error is None


def _best_effort_chown(final: Path, settings: Settings) -> None:
    try:
        uid = int(settings.ARM_TRANSCODE_PUID)
        gid = int(settings.ARM_TRANSCODE_PGID) if settings.ARM_TRANSCODE_PGID else -1
        os.chown(final, uid, gid)
    except (OSError, ValueError) as exc:
        logger.debug("post-move chown skipped: %s", exc)
