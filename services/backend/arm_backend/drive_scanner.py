"""Reconcile a host drive scan into Drive rows, and the periodic scanner
that runs it. The scan itself is `drive_sysfs.enumerate_optical`."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.drive_sysfs import ScannedDrive, enumerate_optical
from arm_common import Config, Drive, DriveIdentityKind, DriveKind, DriveLifecycle, new_id

logger = logging.getLogger("arm_backend.drive_scanner")


class PruneUnavailable(RuntimeError):
    """Raised by scan_once(prune_now=True) when the host enumeration cannot be trusted."""


@dataclass(frozen=True)
class ScanSummary:
    detected: int
    ignored: int
    enrolled: int
    absent: int
    pruned: int


def _apply_scan(row: Drive, d: ScannedDrive) -> None:
    """Refresh the host facts a scan can see. Applies to every lifecycle —
    a port-identity drive that renumbers is followed only because this
    updates device_path on enrolled rows too."""
    row.device_path = d.device_path
    row.vendor = d.vendor
    row.model = d.model
    row.sysfs_port = d.sysfs_port
    if d.by_id_name:
        if (
            row.lifecycle is DriveLifecycle.ENROLLED
            and row.identity_kind is DriveIdentityKind.PORT
            and row.by_id_name is None
        ):
            # An enrolled port-identity row is adopting a by-id identity it
            # didn't have before — a different physical drive in this port
            # may be the one actually publishing the link (Plan 3's
            # register-time identity check is the safety net, not this).
            logger.warning(
                "enrolled drive %s in port %s is adopting by-id identity %s",
                row.id,
                row.sysfs_port,
                d.by_id_name,
            )
        # A drive can gain a by-id link (udev/driver change); never lose one.
        row.by_id_name = d.by_id_name
        row.serial = d.serial
        row.identity_kind = DriveIdentityKind.BY_ID
    elif row.identity_kind is None:
        row.identity_kind = DriveIdentityKind.PORT


def _match_row(d: ScannedDrive, by_id: dict[str, Drive], by_port: dict[str, Drive]) -> Drive | None:
    """The tracked row a scanned drive is: by its by-id link first, else by
    its sysfs port."""
    row = by_id.get(d.by_id_name) if d.by_id_name else None
    if row is None:
        row = by_port.get(d.sysfs_port)
    return row


def _new_drive_row(d: ScannedDrive) -> Drive:
    """A new DETECTED row for a drive no row matches, logged as detected."""
    # A per-row unique id, not d.node: two different physical drives
    # can land on the same srN across ticks (a swap, or an ignored
    # row that is never pruned), and hostname is UNIQUE — a
    # node-keyed placeholder collided and wedged every later tick.
    drive_id = new_id("drv")
    row = Drive(
        id=drive_id,
        hostname=f"scan-{drive_id}",  # placeholder until Plan 3 names the ripper by drive id
        device_path=d.device_path,
        lifecycle=DriveLifecycle.DETECTED,
        present=True,
    )
    logger.info("drive detected: %s %s %s (%s)", d.node, d.vendor, d.model, d.by_id_name or d.sysfs_port)
    return row


def _touch_presence(row: Drive, now: datetime) -> None:
    """Mark a scanned row present as of `now`, unless a ripper owns its
    presence."""
    # Presence is scanner-owned only for rows without a ripper.
    if row.lifecycle is not DriveLifecycle.ENROLLED:
        row.present = True
        row.last_seen_at = now


def _mark_absent(row: Drive) -> None:
    """Mark an unseen row absent, logging the change."""
    if row.present:
        row.present = False
        logger.info("drive absent: %s (%s)", row.device_path, row.by_id_name or row.sysfs_port)


def _aware_last_seen(row: Drive) -> datetime | None:
    """The row's last_seen_at, made aware (UTC) when the database handed it
    back naive."""
    last_seen = row.last_seen_at
    if last_seen is not None and last_seen.tzinfo is None:
        # SQLite hands back naive datetimes; `now`/`cutoff` are always
        # aware (UTC) — comparing naive to aware raises TypeError.
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    return last_seen


def _prunable(row: Drive, cutoff: datetime) -> bool:
    """Whether a DETECTED row was last seen before `cutoff`."""
    last_seen = _aware_last_seen(row)
    return row.lifecycle is DriveLifecycle.DETECTED and last_seen is not None and last_seen < cutoff


async def _retire_unseen(
    session: AsyncSession,
    rows: list[Drive],
    seen: set[int],
    *,
    now: datetime,
    prune_days: int,
) -> int:
    """Mark every row this scan didn't see absent, and delete the DETECTED
    ones past the prune window; enrolled rows are left alone. Returns how
    many were pruned."""
    pruned = 0
    cutoff = now - timedelta(days=prune_days)
    for row in list(rows):
        if id(row) in seen or row.lifecycle is DriveLifecycle.ENROLLED:
            continue
        _mark_absent(row)
        if _prunable(row, cutoff):
            await session.delete(row)
            rows.remove(row)
            pruned += 1
            logger.info("drive pruned after %dd absent: %s", prune_days, row.by_id_name or row.sysfs_port)
    return pruned


def _summarise(rows: list[Drive], pruned: int) -> ScanSummary:
    """The scan's counts by lifecycle and presence."""
    return ScanSummary(
        detected=sum(r.lifecycle is DriveLifecycle.DETECTED for r in rows),
        ignored=sum(r.lifecycle is DriveLifecycle.IGNORED for r in rows),
        enrolled=sum(r.lifecycle is DriveLifecycle.ENROLLED for r in rows),
        absent=sum((not r.present) and r.lifecycle is not DriveLifecycle.ENROLLED for r in rows),
        pruned=pruned,
    )


async def reconcile_drives(
    session: AsyncSession,
    scanned: list[ScannedDrive],
    *,
    now: datetime,
    prune_days: int,
) -> ScanSummary:
    # Virtual (ISO) drives are never scanned, matched, marked absent or
    # pruned here — the host sysfs scan has nothing to say about them; the
    # watchdog owns their lifecycle.
    rows = list((await session.execute(select(Drive).where(col(Drive.kind) == DriveKind.OPTICAL))).scalars().all())
    by_id = {r.by_id_name: r for r in rows if r.by_id_name}
    by_port = {r.sysfs_port: r for r in rows if r.sysfs_port and not r.by_id_name}
    seen: set[int] = set()

    for d in scanned:
        row = _match_row(d, by_id, by_port)
        is_new = row is None
        if row is None:
            row = _new_drive_row(d)
            rows.append(row)
        _apply_scan(row, d)
        _touch_presence(row, now)
        seen.add(id(row))
        if is_new:
            # Only genuinely new rows need session.add(); adding an
            # already-tracked row would register it a second time.
            session.add(row)

    pruned = await _retire_unseen(session, rows, seen, now=now, prune_days=prune_days)
    await session.commit()
    return _summarise(rows, pruned)


DEFAULT_SCAN_INTERVAL_SECONDS = 30
DEFAULT_PRUNE_DAYS = 7


async def scan_tunables(session: AsyncSession) -> tuple[int, int]:
    """(interval_seconds, prune_days) from the Config singleton; defaults when
    the row is missing or a column is None (in-memory rows predating 0030)."""
    cfg = (await session.execute(select(Config))).scalars().first()
    interval_v = getattr(cfg, "drive_scan_interval_seconds", None)
    prune_v = getattr(cfg, "drive_detected_prune_days", None)
    interval = interval_v if interval_v is not None else DEFAULT_SCAN_INTERVAL_SECONDS
    prune = prune_v if prune_v is not None else DEFAULT_PRUNE_DAYS
    return int(interval), int(prune)


class DriveScanner:
    """Periodic + on-demand detection. One instance on app.state;
    POST /api/drives/rescan calls scan_once with the request's session, the
    background loop opens its own."""

    def __init__(self, session_factory: Callable[[], AsyncSession], *, sysfs_root: Path, disk_root: Path) -> None:
        self._session_factory = session_factory
        self._sysfs_root = sysfs_root
        self._disk_root = disk_root
        # POST /rescan (request session) and the background loop (its own
        # session) can both call scan_once concurrently; both do an unlocked
        # select(Drive) then insert, so an overlapping pair can each decide a
        # row is new and double-INSERT. Serialize reconciliation in-process.
        self._lock = asyncio.Lock()
        # Surfaced by GET /api/drives/diagnostic so a dead or failing scanner
        # is visible in the UI, not only in the log.
        self.last_scan_at: datetime | None = None
        self.last_error: str | None = None

    @property
    def disk_root(self) -> Path:
        """The host `/dev/disk`-style mount this scanner enumerates —
        surfaced read-only for GET /api/drives/diagnostic's by-id check."""
        return self._disk_root

    def enumeration_problem(self) -> str | None:
        """None when the host enumeration can be trusted; otherwise a reason
        an empty (or partial) `enumerate_optical` result is not legitimate —
        the sysfs or by-id mount itself is missing, not "nothing plugged
        in". Checked before a prune_now scan (Force Rescan) so a degraded
        host mount can never be read as "prune everything absent"."""
        if not (self._sysfs_root / "class" / "block").is_dir():
            return f"host sysfs is not mounted ({self._sysfs_root / 'class' / 'block'})"
        if not (self._disk_root / "by-id").is_dir():
            return f"host by-id directory is not mounted ({self._disk_root / 'by-id'})"
        return None

    async def scan_once(self, session: AsyncSession, *, prune_now: bool = False) -> ScanSummary:
        """One reconcile. `prune_now` (Force Rescan) drops the prune window to
        zero days: every detected row that is not present right now is deleted
        — enrolled and ignored rows are never pruned (reconcile_drives). Refuses
        (raises PruneUnavailable) rather than pruning when the host enumeration
        cannot be trusted — an unreadable sysfs/by-id mount looks exactly like
        "no drives" otherwise, and prune_now would wipe every DETECTED row."""
        async with self._lock:
            if prune_now:
                problem = self.enumeration_problem()
                if problem is not None:
                    raise PruneUnavailable(problem)
            _, prune_days = await scan_tunables(session)
            scanned = enumerate_optical(sysfs_root=self._sysfs_root, disk_root=self._disk_root)
            summary = await reconcile_drives(
                session, scanned, now=datetime.now(timezone.utc), prune_days=0 if prune_now else prune_days
            )
            self.last_scan_at = datetime.now(timezone.utc)
            self.last_error = None
            return summary

    async def run(self) -> None:
        logger.info("drive scanner starting: sysfs=%s disk=%s", self._sysfs_root, self._disk_root)
        while True:
            interval = DEFAULT_SCAN_INTERVAL_SECONDS
            try:
                async with self._session_factory() as session:
                    interval, _ = await scan_tunables(session)
                    await self.scan_once(session)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — a bad tick must never kill the loop
                logger.exception("drive scan failed; retrying next tick")
                self.last_error = f"{type(exc).__name__}: {exc}"[:300]
            await asyncio.sleep(interval)
