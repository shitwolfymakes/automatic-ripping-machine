"""In-process passthrough execution (TranscodeTool.NONE / no-preset tasks).

Passthrough is a file move, not an encode, so the backend performs it
itself instead of spawning a transcoder container.
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
import contextlib
from collections.abc import Callable
import logging
import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.config import Settings
from arm_common import (
    SessionApplication,
    SessionApplicationStatus,
    Track,
    TrackKind,
    TranscodeTask,
    TranscodeTaskStatus,
    with_log_context,
)
from arm_common.fileops import CopyCancelled, move_tree, transcode_none, tree_size

if TYPE_CHECKING:
    from arm_backend.ws.hub import WSHub

logger = logging.getLogger("arm_backend.passthrough_executor")

# The in-process claim's heartbeat is stamped once here and never
# refreshed afterward (unlike a container transcoder, which heartbeats
# repeatedly over its run). That's safe only because `sweep_stale_claims`
# runs on the same coroutine, in the same process, as `spawn_pending` (a
# single dispatcher, no worker pool): the claim is never "stale" from the
# sweep's point of view during the (synchronous, from the sweep's
# perspective) window this function is running. If a second sweeper or a
# multi-replica backend is ever introduced, it must either exclude
# `IN_PROCESS_CLAIMANT` rows from staleness sweeping or this function must
# start refreshing the heartbeat periodically during the move.
IN_PROCESS_CLAIMANT = "backend-inprocess"

# task_id -> cancel event for the move running now. There is no container
# to stop, so `cancel_running` sets the event and the copy stops at its
# next chunk.
_cancel_events: dict[str, threading.Event] = {}


# How often a running copy's progress is written to the task row (the
# durable surface the Transcoder page reads) and published over WS.
PROGRESS_INTERVAL_SECONDS = 2.0


class _CopyProgress:
    """Bytes copied so far; written by the worker thread only.

    `sizer` gives the total on the first copied bytes: a same-filesystem
    move is a rename that copies nothing, so it never walks the tree."""

    def __init__(self, sizer: Callable[[], int] | None = None) -> None:
        self.total = 0
        self.done = 0
        self._sizer = sizer

    def add(self, n: int) -> None:
        if self._sizer is not None:
            self.total = self._sizer()
            self._sizer = None
        self.done += n


def request_cancel(task_id: str) -> bool:
    """Stop an in-flight in-process move. False when none is running."""
    event = _cancel_events.get(task_id)
    if event is None:
        return False
    event.set()
    return True


class _PassthroughRun:
    """One passthrough task's in-process run, from the claim to its terminal state."""

    # `run` sets these while claiming; they come from the re-selected row.
    _application: SessionApplication | None
    _job_id: str | None
    _source_track_id: str
    _session_application_id: str
    _track: Track | None
    _track_output_path: str | None
    _task_output_path: str | None

    def __init__(self, db: AsyncSession, task: TranscodeTask, hub: "WSHub", settings: Settings) -> None:
        self._db = db
        self._task = task
        self._hub = hub
        self._settings = settings
        self._task_id = task.id

    async def run(self) -> bool | None:
        """Run the task; see `execute_passthrough_task`."""
        current = await self._lock_if_claimable()
        if current is None:
            return None
        self._task = current

        await self._load_application()
        self._source_track_id = self._task.source_track_id
        self._session_application_id = self._task.session_application_id
        with with_log_context(
            job_id=self._job_id, track_id=self._source_track_id, session_application_id=self._session_application_id
        ):
            await self._load_track()
            self._task_output_path = self._task.output_path

            await self._write_claim()
            # Same claim-time side effects as the container path's
            # POST /tasks/{id}/claim: flip the application QUEUED -> RUNNING
            # (session.started) and announce the task (task.started), so the
            # transcodes UI and the session rollup see an identical lifecycle.
            await self._start_application()
            await self._announce_task_started()
            # Commit the claim before the (possibly slow, cross-mount) file
            # move so the tick's FOR UPDATE row locks aren't held across
            # blocking I/O (see docstring).
            await self._db.commit()

            size, error = await self._move_or_reject()

            return await self._finish(size, error)

    async def _lock_if_claimable(self) -> TranscodeTask | None:
        """Re-select the task row locked; None when it is gone or no longer QUEUED."""
        # `populate_existing=True` is required in addition to `with_for_update()`:
        # if `task` (or another reference to the same row) is already in this
        # session's identity map and ISN'T expired, a plain re-select would
        # silently return the cached, possibly-stale object without overwriting
        # its attributes from this query's result -- exactly the gap that let a
        # concurrent writer's committed status change go unnoticed.
        current = (
            await self._db.execute(
                select(TranscodeTask)
                .where(col(TranscodeTask.id) == self._task_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if current is None or current.status != TranscodeTaskStatus.QUEUED:
            logger.debug(
                "passthrough task_id=%s no longer claimable (gone or status changed); skipping",
                self._task_id,
            )
            return None
        return current

    async def _load_application(self) -> None:
        """Load the task's session application and its job id."""
        self._application = (
            await self._db.execute(
                select(SessionApplication).where(col(SessionApplication.id) == self._task.session_application_id)
            )
        ).scalar_one_or_none()
        self._job_id = self._application.job_id if self._application is not None else None

    async def _load_track(self) -> None:
        """Load the source track and its output path."""
        self._track = (
            await self._db.execute(select(Track).where(col(Track.id) == self._source_track_id))
        ).scalar_one_or_none()
        self._track_output_path = self._track.output_path if self._track is not None else None

    async def _write_claim(self) -> None:
        """Stamp the claim fields on the task and flush."""
        self._task.status = TranscodeTaskStatus.IN_PROGRESS
        self._task.claimed_by = IN_PROCESS_CLAIMANT
        self._task.claim_heartbeat_at = self._task.started_at = datetime.now(UTC)
        self._task.attempts = (self._task.attempts or 0) + 1
        self._task.progress_pct = 0
        await self._db.flush()

    async def _start_application(self) -> None:
        """Flip a QUEUED application to RUNNING and emit session.started."""
        if self._application is not None and self._application.status == SessionApplicationStatus.QUEUED:
            self._application.status = SessionApplicationStatus.RUNNING
            await self._db.flush()
            await self._hub.emit(
                topic="transcode.events",
                event_type="session.started",
                payload={
                    "session_application_id": self._application.id,
                    "session_id": self._application.session_id,
                    "job_id": self._application.job_id,
                },
                job_id=self._job_id,
                session=self._db,
            )

    async def _announce_task_started(self) -> None:
        """Emit task.started for the claimed task."""
        await self._hub.emit(
            topic="transcode.events",
            event_type="task.started",
            payload={
                "task_id": self._task_id,
                "session_application_id": self._session_application_id,
                "claimed_by": self._task.claimed_by,
                "attempts": self._task.attempts,
            },
            job_id=self._job_id,
            track_id=self._source_track_id,
            session=self._db,
        )

    async def _move_or_reject(self) -> tuple[int | None, str | None]:
        """Move the file, or reject a task with no source or output path; returns (size, error)."""
        track = self._track
        if track is None or not self._track_output_path:
            return None, "source track has no output_path on disk; rip not complete or raw deleted"
        if not self._task_output_path:
            return None, "task has no output_path"
        return await self._move(
            track, Path(self._track_output_path), Path(self._settings.MEDIA_ROOT) / self._task_output_path
        )

    async def _move(self, track: Track, source: Path, final: Path) -> tuple[int | None, str | None]:
        """Move `source` to `final` in a worker thread with progress publishing; returns (size, error)."""
        error: str | None = None
        size: int | None = None
        is_folder = track.kind == TrackKind.DISC_BACKUP
        mover = move_tree if is_folder else transcode_none
        cancel = _cancel_events[self._task_id] = threading.Event()
        progress = _CopyProgress(sizer=(lambda: tree_size(source)) if is_folder else None)
        stop_publisher = asyncio.Event()
        publisher = asyncio.ensure_future(
            _publish_progress(
                self._db,
                self._hub,
                self._task_id,
                self._job_id,
                self._source_track_id,
                progress,
                stop_publisher,
            )
        )
        try:
            # Move and chown together in the worker thread: a backup
            # tree's chown walks every file, too much for the event loop.
            size = await asyncio.to_thread(
                _move_and_chown, mover, source, final, self._settings, is_folder, cancel, progress
            )
        except CopyCancelled:
            error = "cancelled"
            logger.info("passthrough task_id=%s cancelled mid-copy; source kept", self._task_id)
        except OSError as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]
        finally:
            _cancel_events.pop(self._task_id, None)
            await self._stop_publisher(publisher, stop_publisher)
        return size, error

    async def _stop_publisher(self, publisher: asyncio.Future[None], stop: asyncio.Event) -> None:
        """Stop the progress publisher and wait for it, logging rather than raising its failure."""
        # Stop the publisher before this coroutine uses `db` again. It
        # checks the event between writes, so a commit is never cut
        # off part way; and nothing it raises replaces the move's result.
        stop.set()
        try:
            await publisher
        except Exception:
            logger.exception("passthrough progress publisher failed task_id=%s", self._task_id)

    async def _finish(self, size: int | None, error: str | None) -> bool:
        """Write the terminal state and its events, commit, and return whether the task succeeded."""
        fresh_task = await self._refetch_task()
        await self._reload_application()
        if fresh_task is None:
            logger.info("passthrough task_id=%s deleted mid-move; skipping terminal update", self._task_id)
            return error is None

        event_type, payload_extra = await self._record_terminal(fresh_task, size, error)
        await self._announce_terminal(event_type, payload_extra)
        if self._application is not None:
            from arm_backend.transcode_apply import (  # noqa: PLC0415 - matches dispatcher's lazy import
                settle_session_application,
            )

            await settle_session_application(self._db, self._hub, self._application)
        # Commit the terminal state (+ any aggregate transition) as its own
        # transaction, separate from the claim commit above.
        await self._db.commit()
        return error is None

    async def _refetch_task(self) -> TranscodeTask | None:
        """Re-select the task row, None when a concurrent cancel deleted it."""
        # Re-fetch: cancel_running (a different session) may have deleted
        # this row while the move was in flight. `populate_existing=True`
        # for the same reason as the claim re-select above -- force a
        # refresh from the current row rather than silently reusing
        # whatever this identity-mapped object already had cached.
        return (
            await self._db.execute(
                select(TranscodeTask)
                .where(col(TranscodeTask.id) == self._task_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

    async def _reload_application(self) -> None:
        """Reload the session application after the move, when there is one."""
        if self._application is not None:
            # The progress publisher committed (or rolled back) on this
            # session while the move ran; reload before the aggregate reads it.
            self._application = (
                await self._db.execute(
                    select(SessionApplication)
                    .where(col(SessionApplication.id) == self._session_application_id)
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()

    async def _record_terminal(
        self, fresh_task: TranscodeTask, size: int | None, error: str | None
    ) -> tuple[str, dict[str, Any]]:
        """Mark the task DONE or FAILED and flush; returns the event type and its extra payload."""
        if error is None:
            fresh_task.status = TranscodeTaskStatus.DONE
            fresh_task.progress_pct = 100
            fresh_task.last_error = None
            event_type, payload_extra = (
                "task.completed",
                {"output_path": self._task_output_path, "size_bytes": size},
            )
            logger.info("passthrough complete task_id=%s output=%s", self._task_id, self._task_output_path)
        else:
            fresh_task.status = TranscodeTaskStatus.FAILED
            fresh_task.last_error = error
            event_type, payload_extra = "task.failed", {"last_error": error}
            logger.error("passthrough failed task_id=%s: %s", self._task_id, error)
        await self._db.flush()
        return event_type, payload_extra

    async def _announce_terminal(self, event_type: str, payload_extra: dict[str, Any]) -> None:
        """Emit the task's terminal event."""
        await self._hub.emit(
            topic="transcode.events",
            event_type=event_type,
            payload={
                "task_id": self._task_id,
                "session_application_id": self._session_application_id,
                **payload_extra,
            },
            job_id=self._job_id,
            track_id=self._source_track_id,
            session=self._db,
        )


async def execute_passthrough_task(
    db: AsyncSession, task: TranscodeTask, hub: "WSHub", settings: Settings
) -> bool | None:
    """Run one QUEUED passthrough task to completion in-process.

    Mirrors the container path's lifecycle exactly (claim fields,
    application QUEUED -> RUNNING, session.started / task.started /
    task.completed / task.failed WS events, application aggregation).
    Returns True on DONE, False on FAILED, or None if the task could not be
    claimed at all (see below), not an error, just a lost race.

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

    Because the tick's initial select may have grabbed this row minutes
    earlier (an earlier task's move can run long) and ANY earlier
    passthrough task's claim commit releases every lock that transaction
    held (COMMIT is transaction-scoped, not row-scoped), not just its
    own row's; a concurrent writer (`DELETE /api/transcodes/{id}`, an
    `overwrite` eviction, a job-delete cascade) can remove or repurpose
    this row before we get to it. Re-select it by id, locked, and bail out
    cleanly if it's gone or no longer QUEUED instead of attempting a claim
    UPDATE against a row that isn't there (which raises
    `sqlalchemy.orm.exc.StaleDataError`).

    Because the claim is durably committed before the move, the row can
    also be deleted out from under this function by a concurrent
    `cancel_running` while the copy itself is in flight. Before writing the
    terminal state we re-fetch the row by id again; if it's gone, we log and
    return cleanly instead of resurrecting a cancelled task.
    """
    return await _PassthroughRun(db, task, hub, settings).run()


async def _publish_progress(
    db: AsyncSession,
    hub: "WSHub",
    task_id: str,
    job_id: str | None,
    track_id: str | None,
    progress: _CopyProgress,
    stop: asyncio.Event,
) -> None:
    """While a copy runs, until `stop` is set, heartbeat `progress_pct` onto the row and publish
    `transcode.progress.{task_id}`, as a container transcoder does.

    A Core UPDATE rather than an ORM write: `cancel_running` may delete the
    row at any moment, and an UPDATE of a missing row is a no-op where an
    ORM flush would raise and force a rollback."""
    started = time.monotonic()
    last_pct = -1
    while True:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), PROGRESS_INTERVAL_SECONDS)
        if stop.is_set():
            return
        if progress.total <= 0:
            continue
        pct = min(99, progress.done * 100 // progress.total)
        if pct == last_pct:
            continue
        last_pct = pct
        rate = progress.done / max(time.monotonic() - started, 1e-6)
        eta = int((progress.total - progress.done) / rate) if rate > 0 else None
        try:
            await db.execute(
                update(TranscodeTask)
                .where(col(TranscodeTask.id) == task_id, col(TranscodeTask.status) == TranscodeTaskStatus.IN_PROGRESS)
                .values(progress_pct=pct, claim_heartbeat_at=datetime.now(UTC))
            )
            await db.commit()
        except Exception as exc:
            # Telemetry only: the copy carries on, unreported. The rollback
            # expires the caller's objects, which it reloads after the move.
            logger.warning("passthrough progress write failed task_id=%s: %s; no further progress", task_id, exc)
            await db.rollback()
            return
        try:
            await hub.emit(
                topic=f"transcode.progress.{task_id}",
                event_type="transcode.progress",
                payload={"task_id": task_id, "progress_pct": pct, "eta_seconds": eta, "current_pass": None},
                persist=False,
                job_id=job_id,
                track_id=track_id,
            )
        except Exception as exc:
            logger.warning("passthrough progress publish failed task_id=%s: %s", task_id, exc)


def _move_and_chown(
    mover: Callable[..., int],
    source: Path,
    final: Path,
    settings: Settings,
    is_folder: bool,
    cancel: threading.Event,
    progress: _CopyProgress,
) -> int:
    if not is_folder:
        progress.total = source.stat().st_size
    size = mover(source, final, cancel=cancel, on_bytes=progress.add)
    if settings.ARM_TRANSCODE_PUID:
        _best_effort_chown(final, settings, tree=is_folder)
    return size


def _best_effort_chown(final: Path, settings: Settings, *, tree: bool = False) -> None:
    try:
        uid = int(settings.ARM_TRANSCODE_PUID)
        gid = int(settings.ARM_TRANSCODE_PGID) if settings.ARM_TRANSCODE_PGID else -1
        paths = [final, *final.rglob("*")] if tree else [final]
        for path in paths:
            os.chown(path, uid, gid)
    except (OSError, ValueError) as exc:
        logger.debug("post-move chown skipped: %s", exc)
