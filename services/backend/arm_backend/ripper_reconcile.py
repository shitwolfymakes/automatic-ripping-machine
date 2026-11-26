"""The boot-time reconcile of the enrolled drives' ripper containers, with each
drive's outcome stored on its row."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from sqlmodel import col, select

from arm_backend.ripper_manager import ReconcileSummary, RipperManager, RipperManagerError
from arm_backend.virtual_drive_lifecycle import sweep_virtual_drives
from arm_common import Drive, DriveLifecycle, DriveStatus, Job, JobStatus

if TYPE_CHECKING:
    from arm_backend.ws.hub import WSHub

logger = logging.getLogger(__name__)


async def reconcile_enrolled_rippers(
    manager: RipperManager, session_factory: Any, *, hub: WSHub
) -> ReconcileSummary | None:
    """Lifespan hook: reconcile containers against the `enrolled` rows and
    persist per-drive outcomes in `last_error` (cleared on success). Returns
    None — after logging — when the daemon itself cannot be listed; boot
    must not fail because docker is down.

    The virtual-drive sweep runs FIRST: a finished ISO rip's drive
    is retired before the enrolled list is loaded, so its container is never
    recreated and the ISO never ripped twice. `hub` carries the sweep's
    `rip.failed` for a job whose ripper died while the backend was down."""
    async with session_factory() as db:
        await sweep_virtual_drives(db, manager, hub)
        enrolled = list(
            (await db.execute(select(Drive).where(col(Drive.lifecycle) == DriveLifecycle.ENROLLED))).scalars().all()
        )
        ripping = (await db.execute(select(Job).where(col(Job.status) == JobStatus.RIPPING))).scalars().all()
        busy = frozenset(j.drive_id for j in ripping if j.drive_id)
        try:
            summary = await asyncio.to_thread(manager.reconcile, enrolled, busy=busy)
        except RipperManagerError as exc:
            logger.error("ripper reconcile skipped: %s", exc)
            return None
        for drive in enrolled:
            if drive.id in summary.failed:
                drive.last_error = summary.failed[drive.id]
            elif drive.status is not DriveStatus.ERROR:
                drive.last_error = None  # a stale reason from a previous boot; ERROR rows keep theirs
            db.add(drive)
        await db.commit()
    return summary
