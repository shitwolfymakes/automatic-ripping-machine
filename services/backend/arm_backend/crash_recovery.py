"""Crash recovery.

`reset_job_for_recovery` resets a single RIPPING job's non-queued tracks
back to `queued` (incrementing `attempts`) and stamps `resumed_from_crash`
on the job. Idempotent: a track already at `queued` is left alone, so
re-running the helper neither inflates `attempts` nor double-stamps.

`sweep_in_flight_jobs` finds every job with `status='ripping'` and feeds
each through `reset_job_for_recovery`. Used both at backend startup
(lifespan hook) and on-demand from the per-job `/resume` endpoint.

A backend restart is not a rip crash: the ripper is a separate container
and keeps ripping. The startup sweep is told which drives' rippers the boot
reconcile found alive (`should_recover`) and leaves those jobs alone; a job
whose ripper is gone is the real crash and is reset. `/resume` is the
ripper itself asking, so it always resets.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_common import Job, JobStatus, TrackStatus
from arm_common.models import Track

logger = logging.getLogger("arm_backend.crash_recovery")


async def reset_job_for_recovery(db: AsyncSession, job: Job) -> int:
    """Reset one job for crash recovery. Caller commits.

    - Set `job.resumed_from_crash = True` (no-op if already true).
    - For every track on the job whose status is not QUEUED, set status
      to QUEUED and increment `attempts`. Tracks already QUEUED are left
      alone (idempotent re-runs do not inflate counters).

    Returns the number of tracks touched.
    """
    job.resumed_from_crash = True
    all_tracks = (await db.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all()
    touched = 0
    for track in all_tracks:
        if track.status == TrackStatus.QUEUED:
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


def should_recover(job: Job, live_drive_ids: frozenset[str]) -> bool:
    """Whether a RIPPING job at backend startup is a crashed rip: its drive's
    ripper container is not running (a live one is still ripping it)."""
    return job.drive_id not in live_drive_ids


async def sweep_in_flight_jobs(db_factory: Callable[[], AsyncSession], live_drive_ids: frozenset[str]) -> int:
    """Run `reset_job_for_recovery` against every RIPPING job whose ripper is
    gone (`live_drive_ids` are the drives whose ripper the boot reconcile
    adopted). Single transaction. Returns the number of jobs reset.

    Accepts a session factory rather than a live session because this is
    called from the FastAPI lifespan, before the request scope exists.
    """
    async with db_factory() as session:
        return await _sweep(session, live_drive_ids)


async def _sweep(db: AsyncSession, live_drive_ids: frozenset[str]) -> int:
    ripping = (await db.execute(select(Job).where(col(Job.status) == JobStatus.RIPPING))).scalars().all()
    jobs = [job for job in ripping if should_recover(job, live_drive_ids)]
    if not jobs:
        return 0
    for job in jobs:
        await reset_job_for_recovery(db, job)
    await db.commit()
    logger.info("crash recovery sweep: reset %d in-flight job(s)", len(jobs))
    return len(jobs)
