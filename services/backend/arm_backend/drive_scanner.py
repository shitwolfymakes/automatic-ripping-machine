"""Detect optical drives on the backend's host without privilege (spec §2).

Everything here reads sysfs and the udev by-id symlink directory — no
device node is ever opened, so the backend needs no cgroup rule and
cannot touch a drive. Verified: an unprivileged container with only a
read-only /dev/disk bind enumerates name, major:minor, vendor/model, the
sg pairing and the by-id link, and gets ENOENT on open().

Identity (spec §1):
  * by_id_name — the udev /dev/disk/by-id link whose target is this node.
    Unique and stable across replug and srN renumbering.
  * sysfs_port — the device's sysfs path cut before the first hostN
    component. hostN/targetN numbers change on replug; the USB port
    (usb4/4-1/4-1:1.0) or SATA port (ata3) does not. Fallback identity for
    drives with no by-id link.
  * serial — parsed from by_id_name (udev builds it as
    <bus>-<VENDOR>_<MODEL>_<SERIAL>[-<lun>]); display + Job.drive_serial.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from arm_common import Config, Drive, DriveIdentityKind, DriveLifecycle

logger = logging.getLogger("arm_backend.drive_scanner")

SCSI_CDROM_MAJOR = 11
_HOST_COMPONENT = re.compile(r"^host\d+$")
_LUN_SUFFIX = re.compile(r"-\d+:\d+$")


@dataclass(frozen=True)
class ScannedDrive:
    node: str
    device_path: str
    major: int
    minor: int
    vendor: str | None
    model: str | None
    sg: str | None
    by_id_name: str | None
    serial: str | None
    sysfs_port: str


def parse_short_serial(by_id_name: str) -> str | None:
    """udev's ID_SERIAL_SHORT, recovered from the link name: strip the
    trailing `-N:N` lun, take the last `_`-separated token."""
    stem = _LUN_SUFFIX.sub("", by_id_name)
    if "_" not in stem:
        return None
    return stem.rsplit("_", 1)[1] or None


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def _sysfs_port(class_entry: Path) -> str:
    real = Path(os.path.realpath(class_entry))
    parts = real.parts
    for i, part in enumerate(parts):
        if _HOST_COMPONENT.match(part):
            return str(Path(*parts[:i]))
    # No SCSI host in the path (virtual devices): cut at the block dir.
    if "block" in parts:
        return str(Path(*parts[: parts.index("block")]))
    return str(real)


def _by_id_links(disk_root: Path) -> dict[str, str]:
    """node name -> by-id link name, for links that resolve to an existing target."""
    out: dict[str, str] = {}
    by_id = disk_root / "by-id"
    try:
        entries = sorted(by_id.iterdir())
    except OSError:
        return out
    for link in entries:
        try:
            target = Path(os.readlink(link))
        except OSError:
            continue
        if not (by_id / target).exists():
            continue  # dangling: the drive is gone or the link is stale
        out.setdefault(target.name, link.name)
    return out


def enumerate_optical(*, sysfs_root: Path, disk_root: Path) -> list[ScannedDrive]:
    """Every optical (block major 11) drive visible in sysfs. Never raises."""
    class_block = sysfs_root / "class" / "block"
    try:
        entries = sorted(p for p in class_block.iterdir() if p.name.startswith("sr"))
    except OSError:
        return []
    links = _by_id_links(disk_root)
    drives: list[ScannedDrive] = []
    for entry in entries:
        dev = _read(entry / "dev")
        if not dev or ":" not in dev:
            continue
        major_s, minor_s = dev.split(":", 1)
        if not (major_s.isdigit() and minor_s.isdigit()) or int(major_s) != SCSI_CDROM_MAJOR:
            continue
        device = entry / "device"
        sg: str | None = None
        try:
            sg = sorted(p.name for p in (device / "scsi_generic").iterdir())[0]
        except OSError, IndexError:
            sg = None
        by_id = links.get(entry.name)
        drives.append(
            ScannedDrive(
                node=entry.name,
                device_path=f"/dev/{entry.name}",
                major=int(major_s),
                minor=int(minor_s),
                vendor=_read(device / "vendor"),
                model=_read(device / "model"),
                sg=sg,
                by_id_name=by_id,
                serial=parse_short_serial(by_id) if by_id else None,
                sysfs_port=_sysfs_port(entry),
            )
        )
    return drives


@dataclass(frozen=True)
class ScanSummary:
    detected: int
    ignored: int
    enrolled: int
    absent: int
    pruned: int


def _apply_scan(row: Drive, d: ScannedDrive, now: datetime) -> None:
    """Refresh the host facts a scan can see. Applies to every lifecycle —
    a port-identity drive that renumbers is followed only because this
    updates device_path on enrolled rows too (spec §2)."""
    row.device_path = d.device_path
    row.vendor = d.vendor
    row.model = d.model
    row.sysfs_port = d.sysfs_port
    if d.by_id_name:
        # A drive can gain a by-id link (udev/driver change); never lose one.
        row.by_id_name = d.by_id_name
        row.serial = d.serial
        row.identity_kind = DriveIdentityKind.BY_ID
    elif row.identity_kind is None:
        row.identity_kind = DriveIdentityKind.PORT


async def reconcile_drives(
    session: AsyncSession,
    scanned: list[ScannedDrive],
    *,
    now: datetime,
    prune_days: int,
) -> ScanSummary:
    rows = list((await session.execute(select(Drive))).scalars().all())
    by_id = {r.by_id_name: r for r in rows if r.by_id_name}
    by_port = {r.sysfs_port: r for r in rows if r.sysfs_port and not r.by_id_name}
    seen: set[int] = set()

    for d in scanned:
        row = by_id.get(d.by_id_name) if d.by_id_name else None
        if row is None:
            row = by_port.get(d.sysfs_port)
        is_new = row is None
        if row is None:
            row = Drive(
                hostname=f"scan-{d.node}",  # placeholder until Plan 3 names the ripper by drive id
                device_path=d.device_path,
                lifecycle=DriveLifecycle.DETECTED,
                present=True,
            )
            rows.append(row)
            logger.info("drive detected: %s %s %s (%s)", d.node, d.vendor, d.model, d.by_id_name or d.sysfs_port)
        _apply_scan(row, d, now)
        # Presence is scanner-owned only for rows without a ripper (spec §1).
        if row.lifecycle is not DriveLifecycle.ENROLLED:
            row.present = True
            row.last_seen_at = now
        seen.add(id(row))
        if is_new:
            # Only genuinely new rows need session.add(); adding an
            # already-tracked row would register it a second time.
            session.add(row)

    pruned = 0
    cutoff = now - timedelta(days=prune_days)
    for row in list(rows):
        if id(row) in seen or row.lifecycle is DriveLifecycle.ENROLLED:
            continue
        if row.present:
            row.present = False
            logger.info("drive absent: %s (%s)", row.device_path, row.by_id_name or row.sysfs_port)
        if row.lifecycle is DriveLifecycle.DETECTED and row.last_seen_at is not None and row.last_seen_at < cutoff:
            await session.delete(row)
            rows.remove(row)
            pruned += 1
            logger.info("drive pruned after %dd absent: %s", prune_days, row.by_id_name or row.sysfs_port)

    await session.commit()
    return ScanSummary(
        detected=sum(r.lifecycle is DriveLifecycle.DETECTED for r in rows),
        ignored=sum(r.lifecycle is DriveLifecycle.IGNORED for r in rows),
        enrolled=sum(r.lifecycle is DriveLifecycle.ENROLLED for r in rows),
        absent=sum((not r.present) and r.lifecycle is not DriveLifecycle.ENROLLED for r in rows),
        pruned=pruned,
    )


DEFAULT_SCAN_INTERVAL_SECONDS = 30
DEFAULT_PRUNE_DAYS = 7


async def _tunables(session: AsyncSession) -> tuple[int, int]:
    """(interval_seconds, prune_days) from the Config singleton; defaults when
    the row is missing or a column is None (in-memory rows predating 0029)."""
    cfg = (await session.execute(select(Config))).scalars().first()
    interval = getattr(cfg, "drive_scan_interval_seconds", None) or DEFAULT_SCAN_INTERVAL_SECONDS
    prune = getattr(cfg, "drive_detected_prune_days", None) or DEFAULT_PRUNE_DAYS
    return int(interval), int(prune)


class DriveScanner:
    """Periodic + on-demand detection (spec §2). One instance on app.state;
    POST /api/drives/rescan calls scan_once with the request's session, the
    background loop opens its own."""

    def __init__(self, session_factory: Callable[[], AsyncSession], *, sysfs_root: Path, disk_root: Path) -> None:
        self._session_factory = session_factory
        self._sysfs_root = sysfs_root
        self._disk_root = disk_root

    async def scan_once(self, session: AsyncSession) -> ScanSummary:
        _, prune_days = await _tunables(session)
        scanned = enumerate_optical(sysfs_root=self._sysfs_root, disk_root=self._disk_root)
        return await reconcile_drives(session, scanned, now=datetime.now(timezone.utc), prune_days=prune_days)

    async def run(self) -> None:
        logger.info("drive scanner starting: sysfs=%s disk=%s", self._sysfs_root, self._disk_root)
        while True:
            interval = DEFAULT_SCAN_INTERVAL_SECONDS
            try:
                async with self._session_factory() as session:
                    interval, _ = await _tunables(session)
                    await self.scan_once(session)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — a bad tick must never kill the loop
                logger.exception("drive scan failed; retrying next tick")
            await asyncio.sleep(interval)
