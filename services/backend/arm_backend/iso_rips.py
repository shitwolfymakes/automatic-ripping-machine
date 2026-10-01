"""Rip from ISO: the virtual-drive lifecycle (spec 6.2).

A virtual drive is created `enrolled` with a one-shot ripper container
(restart policy "no") and becomes `retired` once that rip ends. The ripper
just exits; this module's watchdog owns the cleanup. `sweep_virtual_drives`
runs every 30 seconds as a lifespan task and once at boot, before
`reconcile_enrolled_rippers` loads the enrolled list, so a finished ISO rip is
never respawned.

The pure library helpers live in `iso_library` (no cycle with
`ripper_manager`). The `/api/iso` router adds create and cancel here.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlmodel import col, select

from arm_backend.ripper_manager import RipperManager, RipperManagerError
from arm_common import Drive, DriveKind, DriveLifecycle, DriveStatus, Job, JobStatus, Track, TrackStatus
from arm_common.enums import TERMINAL_JOB_STATUSES

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from arm_backend.ws.hub import WSHub

logger = logging.getLogger("arm_backend.iso_rips")

STOPPED_UNEXPECTEDLY = "ISO ripper stopped unexpectedly"
WATCHDOG_INTERVAL_SECONDS = 30.0

# Docker states that mean the one-shot ripper is gone. Anything else
# ("running", "paused", "created", "restarting", "removing") is left alone,
# and so is "unknown" (docker unreachable): retiring on a guess would fail a
# live rip.
_DEAD_STATES = frozenset({"exited", "dead", "missing"})

_EPOCH = datetime.min.replace(tzinfo=UTC)


async def retire_virtual_drive(db: AsyncSession, manager: RipperManager, drive: Drive) -> None:
    """Mark the drive retired (offline, not present) and remove its container.
    The caller commits. A docker failure is logged, not raised: once the row
    is retired its container belongs to no enrolled drive, so the next
    reconcile removes it as an orphan."""
    drive.lifecycle = DriveLifecycle.RETIRED
    drive.status = DriveStatus.OFFLINE
    drive.present = False
    db.add(drive)
    try:
        await asyncio.to_thread(manager.remove, drive.id)
    except RipperManagerError as exc:
        logger.warning("iso drive_id=%s retired but its container was not removed: %s", drive.id, exc)


async def _fail_job(db: AsyncSession, hub: WSHub, job: Job) -> None:
    """Mark an unfinished job failed and emit the usual `rip.failed`, with the
    payload `rip_complete` sends plus the reason. Job has no reason column;
    the reason lives in the persisted event's payload."""
    tracks = (await db.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all()
    job.status = JobStatus.FAILED
    db.add(job)
    await hub.emit(
        topic="ripper.events",
        event_type="rip.failed",
        payload={
            "job_id": job.id,
            "drive_id": job.drive_id,
            "status": job.status.value,
            "tracks_done": sum(1 for t in tracks if t.status == TrackStatus.DONE),
            "tracks_failed": sum(1 for t in tracks if t.status == TrackStatus.FAILED),
            "tracks_total": len(tracks),
            "reason": STOPPED_UNEXPECTEDLY,
        },
        job_id=job.id,
        session=db,
    )
    logger.warning("iso job_id=%s drive_id=%s failed: %s", job.id, job.drive_id, STOPPED_UNEXPECTEDLY)


async def sweep_virtual_drives(db: AsyncSession, manager: RipperManager, hub: WSHub) -> int:
    """One watchdog pass over the enrolled virtual drives. Returns how many it retired.

    - container running (or state unknown): nothing happens;
    - container exited or missing, latest job terminal or no job: retire;
    - container exited or missing, latest job not terminal: fail the job
      ("ISO ripper stopped unexpectedly", `rip.failed`), then retire.
    """
    drives = list(
        (
            await db.execute(
                select(Drive).where(
                    col(Drive.kind) == DriveKind.VIRTUAL, col(Drive.lifecycle) == DriveLifecycle.ENROLLED
                )
            )
        )
        .scalars()
        .all()
    )
    if not drives:
        return 0
    statuses = await asyncio.to_thread(manager.container_statuses, [d.id for d in drives])
    retired = 0
    for drive in drives:
        state, _image_current = statuses.get(drive.id, ("missing", None))
        if state not in _DEAD_STATES:
            continue
        jobs = (await db.execute(select(Job).where(col(Job.drive_id) == drive.id))).scalars().all()
        # Latest job, picked in Python (a virtual drive normally has exactly one).
        job = max(jobs, key=lambda j: j.created_at or _EPOCH, default=None)
        if job is not None and job.status not in TERMINAL_JOB_STATUSES:
            await _fail_job(db, hub, job)
        await retire_virtual_drive(db, manager, drive)
        logger.info("iso drive_id=%s retired (container %s)", drive.id, state)
        retired += 1
    await db.commit()
    return retired


async def run_virtual_drive_watchdog(
    session_factory: Any, manager: RipperManager, hub: WSHub, *, interval: float = WATCHDOG_INTERVAL_SECONDS
) -> None:
    """Lifespan task: sweep every `interval` seconds until cancelled. A failed
    pass is logged and the loop carries on; cancellation propagates."""
    while True:
        try:
            async with session_factory() as db:
                await sweep_virtual_drives(db, manager, hub)
        except Exception:
            logger.exception("iso watchdog: sweep failed")
        await asyncio.sleep(interval)
