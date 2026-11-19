"""Rip from ISO: the virtual-drive lifecycle.

A virtual drive is created `enrolled` with a one-shot ripper container
(restart policy "no") and becomes `retired` once that rip ends. The ripper
just exits; this module's watchdog owns the cleanup. `sweep_virtual_drives`
runs every 30 seconds as a lifespan task and once at boot, before
`reconcile_enrolled_rippers` loads the enrolled list, so a finished ISO rip is
never respawned. A rip parked at a review gate is the one exception: its
ripper only heartbeats, so when a backend restart (or anything else) takes the
container away the watchdog starts it again and the ripper re-identifies
into the same job (`disc_dedupe` reuses a pre-rip job on the same drive),
within a crash-loop window and a budget of starts per hour.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlmodel import col, select

from arm_backend import iso_prepare
from arm_backend.session_drain import cancel_parked_applications
from arm_backend.config import settings
from arm_backend.ripper_manager import RipperManager, RipperManagerError
from arm_common import (
    Drive,
    DriveKind,
    DriveLifecycle,
    DriveStatus,
    Job,
    JobStatus,
    Track,
    TrackStatus,
)
from arm_common.enums import PRE_RIP_JOB_STATUSES, TERMINAL_JOB_STATUSES

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from arm_backend.ws.hub import WSHub

logger = logging.getLogger(__name__)

STOPPED_UNEXPECTEDLY = "ISO ripper stopped unexpectedly"
WATCHDOG_INTERVAL_SECONDS = 30.0

# A freshly-created virtual drive: `POST /api/iso/rips` commits the row
# before `ensure_running` creates its container, so a watchdog tick that
# lands in that window sees "missing" and must not retire a brand-new drive.
# Only "missing" gets this grace — "exited"/"dead" mean a container existed
# and is really gone, which is a real completion at any age.
SPAWN_GRACE_SECONDS = 120

# Docker states that mean the one-shot ripper is gone. Anything else
# ("running", "paused", "created", "restarting", "removing") is left alone,
# and so is "unknown" (docker unreachable): retiring on a guess would fail a
# live rip.
_DEAD_STATES = frozenset({"exited", "dead", "missing"})
# When each virtual drive's parked ripper was started again (monotonic
# seconds, oldest first). A ripper that dies again within this window never
# got going: it is crash-looping and is failed like any other dead rip. One
# that ran longer before dying was stopped by something else (a backend
# restart, even one a few minutes after the last) and is started again. The
# sweep runs every 30 seconds, so a container that crashes on start is seen
# well inside the window.
CRASH_LOOP_WINDOW_SECONDS = 90
# A ripper that dies reproducibly later than the window (a slow scan that then
# crashes) is crash-looping too: past this many starts within the budget
# window, the job is failed. Backend rollouts a few minutes apart stay under it.
RESPAWN_BUDGET = 3
RESPAWN_BUDGET_WINDOW_SECONDS = 3600
_respawned: dict[str, list[float]] = {}

_EPOCH = datetime.min.replace(tzinfo=UTC)

# Where an ISO ripper unpacks an image MakeMKV could not open directly
# (`arm_ripper.iso_extract.EXTRACT_ROOT`, one dir per drive id), under RAW_ROOT.
EXTRACT_DIRNAME = ".iso-extract"


def _mark_retired(db: AsyncSession, drive: Drive) -> None:
    drive.lifecycle = DriveLifecycle.RETIRED
    drive.status = DriveStatus.OFFLINE
    drive.present = False
    db.add(drive)


async def retire_virtual_drive(db: AsyncSession, manager: RipperManager, drive: Drive) -> None:
    """Mark the drive retired (offline, not present), COMMIT, and only then
    remove its container. The commit carries whatever the caller staged in
    the same transaction (an abandoned or failed job) and releases the row
    lock the caller took, so a docker stop that takes its full timeout never
    holds the transaction open: a watchdog pass that runs meanwhile sees the
    drive retired and leaves it alone. A docker failure is logged, not
    raised: once the row is retired its container belongs to no enrolled
    drive, so the next reconcile removes it as an orphan."""
    _mark_retired(db, drive)
    await db.commit()
    iso_prepare.clear(drive.id)
    try:
        await asyncio.to_thread(manager.remove, drive.id)
    except RipperManagerError as exc:
        logger.warning("iso drive_id=%s retired but its container was not removed: %s", drive.id, exc)
    # The ripper removes its own extraction when its pipeline ends; this is the
    # backstop for one stopped first (a cancel, a crash). Drive ids are ULIDs,
    # so the path can't climb out of the extract root.
    await asyncio.to_thread(shutil.rmtree, Path(settings.RAW_ROOT) / EXTRACT_DIRNAME / drive.id, True)


async def locked_drive(db: AsyncSession, drive_id: str) -> Drive | None:
    """Re-read one drive row `FOR UPDATE`, overwriting any cached copy, so a
    cancel and a watchdog pass on the same drive serialize and the second
    one sees the first one's committed lifecycle."""
    return (
        await db.execute(
            select(Drive).where(col(Drive.id) == drive_id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def latest_job(db: AsyncSession, drive_id: str) -> Job | None:
    """The drive's latest job, re-read fresh and locked (a virtual drive
    normally has exactly one; picked in Python)."""
    jobs = (
        (
            await db.execute(
                select(Job)
                .where(col(Job.drive_id) == drive_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    return max(jobs, key=lambda j: j.created_at or _EPOCH, default=None)


async def _fail_job(db: AsyncSession, hub: WSHub, job: Job) -> None:
    """Mark an unfinished job failed and emit the usual `rip.failed`, with the
    payload `rip_complete` sends plus the reason. Job has no reason column;
    the reason lives in the persisted event's payload."""
    tracks = (await db.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all()
    job.status = JobStatus.FAILED
    job.ripped_at = datetime.now(UTC)
    db.add(job)
    # The drain that would fill a parked application never runs now.
    await cancel_parked_applications(db, job)
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


def _within_spawn_grace(drive: Drive) -> bool:
    """True while `drive.created_at` is less than `SPAWN_GRACE_SECONDS` old.
    A drive with no `created_at` (never expected outside a hand-built test
    row) gets no grace — nothing to measure the window from."""
    if drive.created_at is None:
        return False
    created_at = drive.created_at if drive.created_at.tzinfo is not None else drive.created_at.replace(tzinfo=UTC)
    return (datetime.now(UTC) - created_at).total_seconds() < SPAWN_GRACE_SECONDS


async def _respawn_parked(manager: RipperManager, drive: Drive, job: Job) -> bool:
    """Start the ripper of a drive whose job is parked before the rip, unless it
    was started again less than `CRASH_LOOP_WINDOW_SECONDS` ago or has used its
    `RESPAWN_BUDGET` starts in the last `RESPAWN_BUDGET_WINDOW_SECONDS`. False
    when it is crash-looping or the manager could not start it; the caller then
    fails the job as for any dead rip."""
    now = time.monotonic()
    starts = [t for t in _respawned.get(drive.id, []) if now - t < RESPAWN_BUDGET_WINDOW_SECONDS]
    _respawned[drive.id] = starts
    if starts and now - starts[-1] < CRASH_LOOP_WINDOW_SECONDS:
        return False
    if len(starts) >= RESPAWN_BUDGET:
        logger.warning("iso drive_id=%s ripper started %d times within the hour; failing", drive.id, len(starts))
        return False
    try:
        await asyncio.to_thread(manager.ensure_running, drive)
    except RipperManagerError as exc:
        logger.warning("iso drive_id=%s ripper could not be started again for job_id=%s: %s", drive.id, job.id, exc)
        return False
    starts.append(time.monotonic())
    logger.info("iso drive_id=%s ripper started again for parked job_id=%s (%s)", drive.id, job.id, job.status.value)
    return True


async def enrolled_virtual_drives(db: AsyncSession) -> list[Drive]:
    """The virtual drives still enrolled: one per ISO rip in flight."""
    return list(
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


def _is_dead(state: str, drive: Drive) -> bool:
    """True when the drive's ripper is gone for good: exited, dead, or
    missing once the spawn grace has passed."""
    if state not in _DEAD_STATES:
        return False
    return not (state == "missing" and _within_spawn_grace(drive))


async def _sweep_one(db: AsyncSession, manager: RipperManager, hub: WSHub, listed: Drive, state: str) -> bool:
    """Act on one virtual drive whose ripper is dead: start a parked rip's
    ripper again, or fail its unfinished job and retire the drive. True when
    the drive was retired."""
    # The caller's container listing is a snapshot: a cancel may have retired this
    # drive (and abandoned its job) since. Re-read both under a row
    # lock and act only on what is still current.
    drive = await locked_drive(db, listed.id)
    if drive is None or drive.lifecycle != DriveLifecycle.ENROLLED:
        await db.commit()  # release the lock; nothing to do
        return False
    job = await latest_job(db, drive.id)
    if job is not None and job.status in PRE_RIP_JOB_STATUSES and await _respawn_parked(manager, drive, job):
        await db.commit()  # release the lock; the drive stays enrolled
        return False
    if job is not None and job.status not in TERMINAL_JOB_STATUSES:
        await _fail_job(db, hub, job)
    await retire_virtual_drive(db, manager, drive)
    logger.info("iso drive_id=%s retired (container %s)", drive.id, state)
    return True


async def sweep_virtual_drives(db: AsyncSession, manager: RipperManager, hub: WSHub) -> int:
    """One watchdog pass over the enrolled virtual drives. Returns how many it retired.

    - container running (or state unknown): nothing happens;
    - container exited or missing, latest job terminal or no job: retire;
    - container exited or missing, latest job parked before the rip (a review
      gate), not started again within the crash-loop window and under the
      hourly budget: start the ripper again and leave the drive enrolled; it
      re-identifies into the same job;
    - container exited or missing, latest job not terminal otherwise (ripping,
      or parked and crash-looping): fail the job ("ISO ripper stopped
      unexpectedly", `rip.failed`), then retire.

    Each drive is re-read `FOR UPDATE` before it is acted on and skipped if
    it is no longer enrolled; its job is re-read too, so a job a cancel has
    just abandoned is never turned into a failure. Each retire commits on
    its own.
    """
    drives = await enrolled_virtual_drives(db)
    if not drives:
        return 0
    statuses = await asyncio.to_thread(manager.container_statuses, [d.id for d in drives])
    retired = 0
    for listed in drives:
        state, _image_current = statuses.get(listed.id, ("missing", None))
        if _is_dead(state, listed) and await _sweep_one(db, manager, hub, listed, state):
            retired += 1
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
