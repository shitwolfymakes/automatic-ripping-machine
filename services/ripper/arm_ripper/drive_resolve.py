"""Resolve this ripper's drive to the device node it occupies right now.

The kernel assigns `srN` by enumeration order, so a drive unplugged and
replugged (or a host booted with two drives) can come back under a
different number. The backend hands each ripper the exact udev
`/dev/disk/by-id/` link name for its physical drive (ARM_DRIVE_BY_ID); udev
keeps that link pointing at the current node, so one readlink answers
"where is my drive now?" with no scanning and no guessing.

Rules:
  * by_id set and the link resolves to an optical node -> that node.
  * by_id set and anything else (no link, dangling, non-optical) -> ABSENT
    (None). Never fall back to the hint: on a multi-drive host the hint may
    now be someone else's drive.
  * by_id unset (port-identity drive, no by-id link on the host) -> the node
    named by the hint's basename under dev_root, if it exists and is optical.

"Optical" is checked through sysfs (`/sys/class/block/<name>/dev` major 11)
rather than stat(): readable unprivileged, and it works in tests with a
fixture tree instead of real device nodes.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger("arm_ripper.drive_resolve")

# <linux/major.h>: SCSI CD-ROM block devices.
SCSI_CDROM_MAJOR = 11

# A SCSI host component of a sysfs device path; the port is what precedes it.
_HOST_COMPONENT = re.compile(r"^host\d+$")

# (dev_root, node name) pairs already warned about. The poll loop resolves every
# couple of seconds; a node that stays missing is logged once, and again only
# after it has been present in between.
_warned_missing: set[tuple[str, str]] = set()


@dataclass(frozen=True)
class ResolvedDevice:
    path: str
    via: Literal["by_id", "hint"]


def _is_optical(name: str, sysfs_root: Path) -> bool:
    try:
        major = (sysfs_root / "class" / "block" / name / "dev").read_text().strip().split(":")[0]
    except OSError:
        return False
    return major == str(SCSI_CDROM_MAJOR)


def _optical_node(name: str, *, dev_root: Path, sysfs_root: Path, warn_if_missing: bool = False) -> str | None:
    node = dev_root / name
    key = (str(dev_root), name)
    if not node.exists():
        if warn_if_missing and key not in _warned_missing:
            _warned_missing.add(key)
            # udev says the drive is at <name>, but the entrypoint never
            # pre-created that node — so nothing in this container can open it.
            # Almost always a too-low ARM_OPTICAL_SR_MAX / ARM_OPTICAL_SG_MAX.
            logger.warning(
                "drive node %s is not present under %s — is it outside ARM_OPTICAL_SR_MAX/ARM_OPTICAL_SG_MAX?",
                name,
                dev_root,
            )
        return None
    _warned_missing.discard(key)
    if not _is_optical(name, sysfs_root):
        return None
    return str(node)


def resolve_drive_device(
    by_id: str | None,
    hint: str,
    *,
    disk_root: Path,
    dev_root: Path,
    sysfs_root: Path,
) -> ResolvedDevice | None:
    """Current node for this drive, or None when it is absent. Never raises."""
    if by_id:
        link = disk_root / "by-id" / by_id
        try:
            target = os.readlink(link)
        except OSError:
            return None
        path = _optical_node(Path(target).name, dev_root=dev_root, sysfs_root=sysfs_root, warn_if_missing=True)
        return ResolvedDevice(path=path, via="by_id") if path else None

    hint_path = Path(hint)
    path = _optical_node(hint_path.name, dev_root=dev_root, sysfs_root=sysfs_root)
    return ResolvedDevice(path=path, via="hint") if path else None


def node_port(node: str, *, sysfs_root: Path) -> str | None:
    """The port the drive behind `node` is plugged into: its sysfs device path
    cut before the first `hostN` component, as the backend scanner records
    `sysfs_port`. None when sysfs cannot say (no entry, no SCSI host)."""
    entry = sysfs_root / "class" / "block" / Path(node).name
    try:
        real = Path(os.path.realpath(entry, strict=True))
    except OSError:
        return None
    for i, part in enumerate(real.parts):
        if _HOST_COMPONENT.match(part):
            return str(Path(*real.parts[:i]))
    return None
