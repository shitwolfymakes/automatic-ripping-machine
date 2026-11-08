"""Rip from ISO: create and cancel an ISO rip, for the `/api/iso` router.

The watchdog that retires a virtual drive once its rip ends lives in
`virtual_drive_lifecycle`. The pure library helpers live in `iso_library`
(no cycle with `ripper_manager`).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from sqlmodel import col, select

from arm_backend import disc_folders, file_browser, iso_image
from arm_backend.config import settings
from arm_backend.file_browser import PathError
from arm_backend.iso_library import library_configured
from arm_backend.job_abandon import abandon_job_transition
from arm_backend.ripper_manager import RipperManager, RipperManagerError
from arm_backend.constants import CONFIG_SINGLETON_ID
from arm_backend.virtual_drive_lifecycle import (
    enrolled_virtual_drives,
    latest_job,
    locked_drive,
    retire_virtual_drive,
    sweep_virtual_drives,
)
from arm_common import (
    Config,
    Drive,
    DriveKind,
    DriveLifecycle,
    DriveSourceKind,
    DriveStatus,
    Session,
)
from arm_common.enums import NON_TERMINAL_JOB_STATUSES
from arm_common.ulid import new_id

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from arm_backend.ws.hub import WSHub


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


def resolve_source(rel: str) -> tuple[Path, DriveSourceKind]:
    """The library source for `rel` (relative to the ISO library) and its kind:
    an `.iso` regular file, or a disc folder (BDMV / VIDEO_TS at its root).

    Rejects an absolute path, an escape outside the library (including a
    symlink that points out, per `file_browser.resolve`), and anything else.
    """
    if Path(rel).is_absolute():
        raise IsoRipError(400, "path must be relative to the ISO library")
    try:
        target = file_browser.resolve("ISO", rel)
    except PathError as exc:
        raise IsoRipError(400, "path is outside the ISO library") from exc
    if target.is_dir():
        if disc_folders.disc_type(target) is None:
            raise IsoRipError(400, "only .iso files or disc folders (with BDMV or VIDEO_TS) can be ripped")
        return target, DriveSourceKind.FOLDER
    if not target.name.endswith(".iso"):
        raise IsoRipError(400, "only .iso files or disc folders (with BDMV or VIDEO_TS) can be ripped")
    if not target.is_file():
        raise IsoRipError(404, "no such ISO file")
    return target, DriveSourceKind.ISO


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
    """Create and spawn a virtual drive for the ISO or disc folder at `rel`
    (library-relative).

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
        target, source_kind = await asyncio.to_thread(resolve_source, rel)
        if source_kind is DriveSourceKind.ISO:
            # A copy that stopped partway can never rip whole: say so now, not
            # after a long unpack and a titleless scan.
            cut = await asyncio.to_thread(iso_image.truncation, target)
            if cut is not None:
                raise IsoRipError(422, cut.message())
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
        live = await enrolled_virtual_drives(db)
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
            source_kind=source_kind,
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
    drive = await locked_drive(db, drive_id)
    if drive is None:
        raise IsoRipError(404, f"unknown drive_id: {drive_id}")
    if drive.kind != DriveKind.VIRTUAL or drive.lifecycle != DriveLifecycle.ENROLLED:
        raise IsoRipError(409, f"cannot cancel: drive_id={drive_id} is not an active ISO rip")
    job = await latest_job(db, drive_id)
    if job is not None and job.status in NON_TERMINAL_JOB_STATUSES:
        await abandon_job_transition(db, hub, job)
    # Commits the abandon + retire together, then removes the container.
    await retire_virtual_drive(db, manager, drive)
