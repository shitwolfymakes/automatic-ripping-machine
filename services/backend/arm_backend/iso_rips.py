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
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlmodel import col, select

from arm_backend import file_browser
from arm_backend.config import settings
from arm_backend.file_browser import PathError
from arm_backend.iso_library import library_configured
from arm_backend.job_abandon import abandon_job_transition
from arm_backend.ripper_manager import RipperManager, RipperManagerError
from arm_backend.seeders import CONFIG_SINGLETON_ID
from arm_common import (
    Config,
    Drive,
    DriveKind,
    DriveLifecycle,
    DriveSourceKind,
    DriveStatus,
    Job,
    JobStatus,
    Session,
    Track,
    TrackStatus,
)
from arm_common.enums import NON_TERMINAL_JOB_STATUSES, TERMINAL_JOB_STATUSES
from arm_common.ulid import new_id

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from arm_backend.ws.hub import WSHub

logger = logging.getLogger("arm_backend.iso_rips")

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

_EPOCH = datetime.min.replace(tzinfo=UTC)


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
    try:
        await asyncio.to_thread(manager.remove, drive.id)
    except RipperManagerError as exc:
        logger.warning("iso drive_id=%s retired but its container was not removed: %s", drive.id, exc)


async def _locked_drive(db: AsyncSession, drive_id: str) -> Drive | None:
    """Re-read one drive row `FOR UPDATE`, overwriting any cached copy, so a
    cancel and a watchdog pass on the same drive serialize and the second
    one sees the first one's committed lifecycle."""
    return (
        await db.execute(
            select(Drive).where(col(Drive.id) == drive_id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def _latest_job(db: AsyncSession, drive_id: str) -> Job | None:
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


async def sweep_virtual_drives(db: AsyncSession, manager: RipperManager, hub: WSHub) -> int:
    """One watchdog pass over the enrolled virtual drives. Returns how many it retired.

    - container running (or state unknown): nothing happens;
    - container exited or missing, latest job terminal or no job: retire;
    - container exited or missing, latest job not terminal: fail the job
      ("ISO ripper stopped unexpectedly", `rip.failed`), then retire.

    Each drive is re-read `FOR UPDATE` before it is acted on and skipped if
    it is no longer enrolled; its job is re-read too, so a job a cancel has
    just abandoned is never turned into a failure. Each retire commits on
    its own.
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
    for listed in drives:
        state, _image_current = statuses.get(listed.id, ("missing", None))
        if state not in _DEAD_STATES:
            continue
        if state == "missing" and _within_spawn_grace(listed):
            continue
        # The listing above is a snapshot: a cancel may have retired this
        # drive (and abandoned its job) since. Re-read both under a row
        # lock and act only on what is still current.
        drive = await _locked_drive(db, listed.id)
        if drive is None or drive.lifecycle != DriveLifecycle.ENROLLED:
            await db.commit()  # release the lock; nothing to do
            continue
        job = await _latest_job(db, drive.id)
        if job is not None and job.status not in TERMINAL_JOB_STATUSES:
            await _fail_job(db, hub, job)
        await retire_virtual_drive(db, manager, drive)
        logger.info("iso drive_id=%s retired (container %s)", drive.id, state)
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


# --- create / cancel (the `/api/iso` router) ---------------------------------

# Serializes `create_iso_rip`: without it, two concurrent POSTs could both
# read "cap not full" / "not a duplicate" before either commits its new row.
_create_lock = asyncio.Lock()


class IsoRipError(Exception):
    """A create/cancel failure already reduced to an HTTP status + detail."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def resolve_iso(rel: str) -> Path:
    """The library file for `rel`, relative to the ISO library.

    Rejects an absolute path, an escape outside the library (including a
    symlink that points out, per `file_browser.resolve`), and anything that
    isn't a `.iso` regular file.
    """
    if Path(rel).is_absolute():
        raise IsoRipError(400, "path must be relative to the ISO library")
    try:
        target = file_browser.resolve("ISO", rel)
    except PathError as exc:
        raise IsoRipError(400, "path is outside the ISO library") from exc
    if not target.name.endswith(".iso"):
        raise IsoRipError(400, "only .iso files can be ripped")
    if not target.is_file():
        raise IsoRipError(404, "no such ISO file")
    return target


async def _iso_cap(db: AsyncSession) -> int:
    """`Config.max_parallel_iso_rips` (default 1 if the singleton is somehow
    missing — the same default the column carries)."""
    cfg = (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None:
        return 1
    return int(cfg.max_parallel_iso_rips)


async def create_iso_rip(
    db: AsyncSession, manager: RipperManager, hub: WSHub, rel: str, session_id: str | None
) -> Drive:
    """Create and spawn a virtual drive for the ISO at `rel` (library-relative).

    Serialized by `_create_lock` so two concurrent requests can't both pass
    the duplicate/cap checks before either commits. A docker failure after
    the row is committed retires the drive instead of leaving a stuck
    "enrolled" row with no container.

    Refused (409, the manual-trigger wording) while ripping is paused: the
    ripper's identify would be refused and the drive retired with no job.
    A watchdog pass runs first, inside the lock, so a rip that finished in
    the last 30 seconds no longer counts against the cap or as a duplicate.
    """
    if not library_configured():
        raise IsoRipError(503, "the ISO library is not configured")
    async with _create_lock:
        # Off the event loop: the library is usually a network share and a stat
        # there can take seconds (minutes under load).
        target = await asyncio.to_thread(resolve_iso, rel)
        cfg = (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
        # Same rule as the ripper's identify: paused with the review hold off
        # refuses new discs, but paused with the hold on (the UI Pause toggle)
        # parks them for review, so an ISO rip starts and waits there too.
        if cfg is not None and cfg.ripping_paused and not cfg.hold_for_review:
            raise IsoRipError(409, "ripping is paused; no new jobs accepted")
        rel_norm = await asyncio.to_thread(lambda: str(target.relative_to(Path(settings.ISO_INGRESS_ROOT).resolve())))
        if session_id is not None:
            session = (await db.execute(select(Session).where(col(Session.id) == session_id))).scalar_one_or_none()
            if session is None:
                raise IsoRipError(404, "unknown session")
        await sweep_virtual_drives(db, manager, hub)
        live = list(
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
        if any(d.source_path == rel_norm for d in live):
            raise IsoRipError(409, "This ISO is already being ripped.")
        cap = await _iso_cap(db)
        if len(live) >= cap:
            raise IsoRipError(
                409,
                f"The ISO rip limit is reached ({cap} at a time). "
                "Wait for the current rip to finish or raise the limit in Settings > Ripping.",
            )
        drive_id = new_id("drv")
        drive = Drive(
            id=drive_id,
            hostname=f"iso-{drive_id[-12:].lower()}",
            kind=DriveKind.VIRTUAL,
            source_kind=DriveSourceKind.ISO,
            source_path=rel_norm,
            lifecycle=DriveLifecycle.ENROLLED,
            device_path=f"/source/{target.name}",
            display_name=target.name,
            status=DriveStatus.ONLINE,
            present=True,
            rip_params_json={"session_id": session_id} if session_id else {},
        )
        db.add(drive)
        await db.commit()
        await db.refresh(drive)
        try:
            await asyncio.to_thread(manager.ensure_running, drive)
        except RipperManagerError as exc:
            await retire_virtual_drive(db, manager, drive)  # commits
            raise IsoRipError(500, f"could not start the ISO ripper: {exc}") from exc
        return drive


async def cancel_iso_rip(db: AsyncSession, manager: RipperManager, hub: WSHub, drive_id: str) -> None:
    """Cancel an in-progress ISO rip: abandon its job (if any, and still
    non-terminal) exactly like `routers/jobs.py` `abandon_job`, then retire
    the virtual drive. The drive row is locked first, so a watchdog pass on
    the same drive waits for this commit and then sees it retired."""
    drive = await _locked_drive(db, drive_id)
    if drive is None:
        raise IsoRipError(404, f"unknown drive_id: {drive_id}")
    if drive.kind != DriveKind.VIRTUAL or drive.lifecycle != DriveLifecycle.ENROLLED:
        raise IsoRipError(409, f"cannot cancel: drive_id={drive_id} is not an active ISO rip")
    job = await _latest_job(db, drive_id)
    if job is not None and job.status in NON_TERMINAL_JOB_STATUSES:
        await abandon_job_transition(db, hub, job)
    # Commits the abandon + retire together, then removes the container.
    await retire_virtual_drive(db, manager, drive)
