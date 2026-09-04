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

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

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
            target_rel = Path(os.readlink(link))
        except OSError:
            continue
        # Resolve relative to the link's parent directory
        try:
            target_real = (link.parent / target_rel).resolve()
        except OSError, ValueError:
            continue
        # Check if the resolved target exists
        if not target_real.exists():
            continue  # dangling: the drive is gone or the link is stale
        out.setdefault(target_real.name, link.name)
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
