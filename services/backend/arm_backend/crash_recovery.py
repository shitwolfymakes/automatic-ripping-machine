"""Crash recovery.

`reset_job_for_recovery` resets a single RIPPING job's unsettled tracks
back to `queued` (incrementing `attempts`) and stamps `resumed_from_crash`
on the job. A `done` track whose file is still on disk at its recorded size
stays `done`: the resumed rip skips it instead of ripping it again.
Idempotent: a track already at `queued` is left alone, so re-running the
helper neither inflates `attempts` nor double-stamps.

`sweep_in_flight_jobs` finds every job with `status='ripping'` and feeds
each through `reset_job_for_recovery`. Used both at backend startup
(lifespan hook) and on-demand from the per-job `/resume` endpoint.

Race note: if only the backend crashed and the ripper is still mid-rip,
the sweep will reset that ripper's tracks to `queued`. The ripper's next
in-flight `PATCH /tracks/{id}` flips them back to `in_progress` with one
extra `attempts++`. Cosmetic only — the rip still completes normally.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_common import Job, JobStatus, TrackStatus
from arm_common.models import Track

logger = logging.getLogger("arm_backend.crash_recovery")


def _finished_file_intact(track: Track) -> bool:
    """Whether a DONE track's file is on disk at the size the rip recorded.

    MakeMKV writes a title's final size only when it closes the file, so a
    matching size tells a finished file from one a crash cut short. Runs in a
    thread: the raw folder may be on NFS, where a stat can block.
    """
    if track.output_path is None or track.size_bytes is None:
        return False
    try:
        return os.stat(track.output_path).st_size == track.size_bytes
    except OSError:
        return False


async def reset_job_for_recovery(db: AsyncSession, job: Job) -> int:
    """Reset one job for crash recovery. Caller commits.

    - Set `job.resumed_from_crash = True` (no-op if already true).
    - For every track on the job that is not QUEUED or SKIPPED (never read, so nothing to redo), and is not a DONE
      track whose file is intact, set status to QUEUED and increment
      `attempts`. Tracks already QUEUED are left alone (idempotent re-runs
      do not inflate counters).

    Returns the number of tracks touched.
    """
    job.resumed_from_crash = True
    all_tracks = (await db.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all()
    touched = 0
    for track in all_tracks:
        if track.status in (TrackStatus.QUEUED, TrackStatus.SKIPPED):
            continue
        if track.status == TrackStatus.DONE and await asyncio.to_thread(_finished_file_intact, track):
            continue
        track.status = TrackStatus.QUEUED
        track.attempts = (track.attempts or 0) + 1
        touched += 1
    if touched:
        logger.info(
            "crash recovery: job_id=%s reset %d track(s) to queued",
            job.id,
            touched,
        )
    return touched


async def sweep_in_flight_jobs(db_factory: Callable[[], AsyncSession]) -> int:
    """Run `reset_job_for_recovery` against every RIPPING job. Single
    transaction. Returns the number of jobs swept.

    Accepts a session factory rather than a live session because this is
    called from the FastAPI lifespan, before the request scope exists.
    """
    async with db_factory() as session:
        return await _sweep(session)


async def _sweep(db: AsyncSession) -> int:
    jobs = (await db.execute(select(Job).where(col(Job.status) == JobStatus.RIPPING))).scalars().all()
    if not jobs:
        return 0
    for job in jobs:
        await reset_job_for_recovery(db, job)
    await db.commit()
    logger.info("crash recovery sweep: reset %d in-flight job(s)", len(jobs))
    return len(jobs)
