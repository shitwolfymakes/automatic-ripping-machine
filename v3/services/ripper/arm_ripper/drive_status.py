"""Synchronous drive-status probe shared across the ripper service.

Used by the heartbeat task to post the drive's current media status to
the backend, which then powers the manual-rip API's "tray-open / empty"
pre-check.

The probe is a pure ioctl read — `CDROM_DRIVE_STATUS` returns the
medium-presence signal without touching the SCSI read path. Cheap
enough to run every HEARTBEAT_INTERVAL_SECONDS.

(Earlier versions of this file also offered a `verify_read=True` mode
that pulled bytes from offset 0 to catch the "drive reports CDS_DISC_OK
but next SCSI read returns NOT_READY" case. That whole class of failure
came from the per-title rip loop letting the drive idle between
`makemkvcon` invocations; with the single-invocation rip the drive
stays open for the entire rip and the verify-read path is no longer
needed. See [.claude/memory/](.claude/memory/) for the rationale.)
"""

from __future__ import annotations

import fcntl
import logging
import os

from arm_common import DriveMediaStatus

logger = logging.getLogger("arm_ripper.drive_status")

# Linux <linux/cdrom.h>.
_CDROM_DRIVE_STATUS = 0x5326
_CDS_NO_INFO = 0
_CDS_NO_DISC = 1
_CDS_TRAY_OPEN = 2
_CDS_DRIVE_NOT_READY = 3
_CDS_DISC_OK = 4

_CDS_TO_ENUM: dict[int, DriveMediaStatus] = {
    _CDS_NO_INFO: DriveMediaStatus.UNKNOWN,
    _CDS_NO_DISC: DriveMediaStatus.NO_DISC,
    _CDS_TRAY_OPEN: DriveMediaStatus.TRAY_OPEN,
    _CDS_DRIVE_NOT_READY: DriveMediaStatus.NOT_READY,
    _CDS_DISC_OK: DriveMediaStatus.LOADED,
}


def probe_drive_media(device_path: str) -> tuple[DriveMediaStatus, str]:
    """Return (status, human-readable reason). Never raises.

    open() failure → UNAVAILABLE; ioctl unsupported → UNKNOWN.
    """
    try:
        fd = os.open(device_path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as exc:
        return DriveMediaStatus.UNAVAILABLE, f"open: errno={exc.errno} {exc.strerror or exc}"
    try:
        try:
            raw = fcntl.ioctl(fd, _CDROM_DRIVE_STATUS, 0)
        except OSError as exc:
            return DriveMediaStatus.UNKNOWN, f"ioctl unsupported (errno={exc.errno})"
        status = _CDS_TO_ENUM.get(raw, DriveMediaStatus.UNKNOWN)
    finally:
        os.close(fd)
    return status, f"CDROM_DRIVE_STATUS={raw} ({status.value})"
