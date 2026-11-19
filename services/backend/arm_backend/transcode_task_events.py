"""Job-log events for a transcode task's milestones, shared by container and in-process passthrough tasks.

Message builders and emitters are pure; the `announce_*` coroutines load the task's job and tracks first.
`log_safely` keeps a logging failure from undoing the request or run that reached the milestone.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Literal, NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.track_labels import TrackLabel, track_label
from arm_backend.transcode_queue import resolve_preset_for_task
from arm_common import Job, SessionApplication, Track, TranscodeTask, TranscodeTaskStatus
from arm_common.log_format import human_size, quarter_crossed
from arm_common.logging import log_event, with_log_context

logger = logging.getLogger("arm_backend.transcode_task_events")

GpuWaitState = Literal["waiting", "resumed"]


def _track_ref(label: TrackLabel | None) -> str:
    """`track 1/19`; `an unknown track` when the task's source track is not among the job's tracks."""
    return f"track {label.index}/{label.total}" if label is not None else "an unknown track"


def _shown_output(output: str) -> str:
    """The output's file name, behind `.../` when it sits in a folder."""
    name = PurePosixPath(output).name
    return output if name == output else f".../{name}"


def transcode_started_message(label: TrackLabel | None, preset: str | None) -> str:
    """`transcoding track 1/19 to FLAC`; a task without a preset copies the file as it is."""
    if preset is None:
        return f"copying {_track_ref(label)} as is (no transcode preset)"
    return f"transcoding {_track_ref(label)} to {preset}"


def transcode_progress_message(label: TrackLabel | None, percent: int) -> str:
    """`track 1/19: 50%`."""
    return f"{_track_ref(label)}: {percent}%"


def transcode_completed_message(label: TrackLabel | None, output: str, size_bytes: int | None) -> str:
    """`track 1/19 transcoded: .../01 - Title - flac.flac (31.1 MB)`."""
    return f"{_track_ref(label)} transcoded: {_shown_output(output)} ({human_size(size_bytes)})"


def transcode_failed_message(label: TrackLabel | None, error: str) -> str:
    """`track 1/19 transcode failed: <error>`."""
    return f"{_track_ref(label)} transcode failed: {error}"


def gpu_wait_message(state: GpuWaitState, encoder: str | None, track: str | None) -> str:
    """`transcode waiting for a GPU encoder (any_h265): track 3/6`, or `no longer waiting` when it resumes."""
    verb = "waiting" if state == "waiting" else "no longer waiting"
    which = f" ({encoder})" if encoder else ""
    where = f": {track}" if track else ""
    return f"transcode {verb} for a GPU encoder{which}{where}"


def _label(task: TranscodeTask, job: Job, tracks: Sequence[Track]) -> TrackLabel | None:
    """The task's source track label, or None when that track is not among `tracks`."""
    track = next((t for t in tracks if t.id == task.source_track_id), None)
    return track_label(job, track, tracks) if track is not None else None


def _task_context(task: TranscodeTask, job: Job) -> AbstractContextManager[None]:
    return with_log_context(
        job_id=job.id, track_id=task.source_track_id, session_application_id=task.session_application_id
    )


def log_transcode_started(task: TranscodeTask, job: Job, tracks: Sequence[Track], *, preset: str | None = None) -> None:
    label = _label(task, job, tracks)
    with _task_context(task, job):
        log_event(
            logger,
            "transcode.started",
            transcode_started_message(label, preset),
            task_id=task.id,
            track_index=label.index if label is not None else None,
            track_total=label.total if label is not None else None,
            preset=preset,
        )


def log_transcode_progress(
    task: TranscodeTask, job: Job, tracks: Sequence[Track], previous_pct: int, current_pct: int
) -> None:
    """Log the highest quarter (25/50/75/100) the task crossed since `previous_pct`, if any."""
    percent = quarter_crossed(previous_pct, current_pct)
    if percent is None:
        return
    label = _label(task, job, tracks)
    with _task_context(task, job):
        log_event(
            logger, "transcode.progress", transcode_progress_message(label, percent), task_id=task.id, percent=percent
        )


def log_transcode_completed(
    task: TranscodeTask,
    job: Job,
    tracks: Sequence[Track],
    output: str,
    size_bytes: int | None,
    elapsed_seconds: float | None,
) -> None:
    label = _label(task, job, tracks)
    with _task_context(task, job):
        log_event(
            logger,
            "transcode.completed",
            transcode_completed_message(label, output, size_bytes),
            task_id=task.id,
            output=output,
            size_bytes=size_bytes,
            elapsed_seconds=elapsed_seconds,
        )


def log_transcode_failed(task: TranscodeTask, job: Job, tracks: Sequence[Track], error: str) -> None:
    label = _label(task, job, tracks)
    with _task_context(task, job):
        log_event(
            logger,
            "transcode.failed",
            transcode_failed_message(label, error),
            level=logging.ERROR,
            task_id=task.id,
            error=error,
        )


async def _subject(db: AsyncSession, task: TranscodeTask) -> tuple[Job, list[Track]] | None:
    """The task's job and all of its tracks, or None when its application or job is gone."""
    application = (
        await db.execute(select(SessionApplication).where(col(SessionApplication.id) == task.session_application_id))
    ).scalar_one_or_none()
    if application is None:
        return None
    job = (await db.execute(select(Job).where(col(Job.id) == application.job_id))).scalar_one_or_none()
    if job is None:
        return None
    tracks = (await db.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all()
    return job, list(tracks)


def _elapsed_since_claim(task: TranscodeTask) -> float | None:
    if task.started_at is None:
        return None
    return (datetime.now(UTC) - task.started_at).total_seconds()


async def announce_started(db: AsyncSession, task: TranscodeTask) -> None:
    """Log `transcode.started` for a just-claimed task, naming its session's preset."""
    subject = await _subject(db, task)
    if subject is None:
        return
    preset = await resolve_preset_for_task(db, task)
    log_transcode_started(task, *subject, preset=preset.name if preset is not None else None)


async def announce_progress(db: AsyncSession, task: TranscodeTask, previous_pct: int, current_pct: int) -> None:
    """Log `transcode.progress` when the update crossed a quarter; reads nothing otherwise."""
    if quarter_crossed(previous_pct, current_pct) is None:
        return
    subject = await _subject(db, task)
    if subject is None:
        return
    log_transcode_progress(task, *subject, previous_pct, current_pct)


async def announce_completed(db: AsyncSession, task: TranscodeTask, output: str, size_bytes: int | None) -> None:
    """Log `transcode.completed`, timed from the task's claim."""
    subject = await _subject(db, task)
    if subject is None:
        return
    log_transcode_completed(task, *subject, output, size_bytes, _elapsed_since_claim(task))


async def announce_failed(db: AsyncSession, task: TranscodeTask, error: str) -> None:
    """Log `transcode.failed`."""
    subject = await _subject(db, task)
    if subject is None:
        return
    log_transcode_failed(task, *subject, error)


async def log_safely(event: str, work: Awaitable[None]) -> None:
    """Await a milestone log; a Python-level failure in it is logged, never raised into the caller.

    It does not undo a database error inside `work`: on a session that work leaves needing a
    rollback, so callers run it after their commit where they can.
    """
    try:
        await work
    except Exception:
        logger.exception("could not log the %s milestone", event)


class _GpuWait(NamedTuple):
    """What a GPU-wait line says and the job it belongs to, kept so the resume line matches it."""

    job_id: str | None
    track_id: str
    session_application_id: str
    track: str | None
    encoder: str | None
    reason: str | None


class GpuWaitLog:
    """The tasks currently logged as waiting for a GPU, so a wait logs once when it starts and once when it ends.

    In memory only: after a backend restart a task still waiting logs one fresh `waiting` line.
    """

    def __init__(self) -> None:
        self._waiting: dict[str, _GpuWait] = {}
        # Spawned tasks their transcoder has not claimed yet: still QUEUED, and the next
        # pass finds their GPU busy (claimed by the task itself), which is not a new wait.
        self._spawned: set[str] = set()

    async def waiting(self, db: AsyncSession, task: TranscodeTask, encoder: str | None, reason: str | None) -> None:
        """Log `transcode.waiting` (state `waiting`) the first time `task` queues for a GPU."""
        if task.id in self._waiting or task.id in self._spawned:
            return
        subject = await _subject(db, task)
        label = _label(task, *subject) if subject is not None else None
        wait = _GpuWait(
            job_id=subject[0].id if subject is not None else None,
            track_id=task.source_track_id,
            session_application_id=task.session_application_id,
            track=_track_ref(label) if label is not None else None,
            encoder=encoder,
            reason=reason,
        )
        self._waiting[task.id] = wait
        _log_gpu_wait(task.id, wait, "waiting")

    def resumed(self, task_id: str) -> None:
        """Log `transcode.waiting` (state `resumed`) when a logged wait ends; nothing for a task not waiting."""
        wait = self._waiting.pop(task_id, None)
        if wait is not None:
            _log_gpu_wait(task_id, wait, "resumed")

    def spawned(self, task_id: str) -> None:
        """Note a spawned task, so it is not logged as waiting again before its transcoder claims it."""
        self._spawned.add(task_id)

    async def settle(self, db: AsyncSession) -> None:
        """End the logged wait of every task no longer queued (cancelled, deleted or failed elsewhere),
        and forget spawned tasks that have left the queue."""
        watched = set(self._waiting) | self._spawned
        if not watched:
            return
        rows = await db.execute(
            select(TranscodeTask).where(
                col(TranscodeTask.id).in_(list(watched)), col(TranscodeTask.status) == TranscodeTaskStatus.QUEUED
            )
        )
        queued = {task.id for task in rows.scalars().all()}
        self._spawned &= queued
        for task_id in [waiting_id for waiting_id in self._waiting if waiting_id not in queued]:
            self.resumed(task_id)


def _log_gpu_wait(task_id: str, wait: _GpuWait, state: GpuWaitState) -> None:
    with with_log_context(
        job_id=wait.job_id, track_id=wait.track_id, session_application_id=wait.session_application_id
    ):
        log_event(
            logger,
            "transcode.waiting",
            gpu_wait_message(state, wait.encoder, wait.track),
            task_id=task_id,
            encoder=wait.encoder,
            reason=wait.reason,
            state=state,
        )
