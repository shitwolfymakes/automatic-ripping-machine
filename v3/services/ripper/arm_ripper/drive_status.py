"""Synchronous drive-status probe shared across the ripper service.

Two callers:
  - rip/dispatcher._wait_for_drive_ready uses this to gate the next
    title in a multi-title rip on the medium being ready.
  - the heartbeat task posts the same reading to the backend so the
    manual-rip API can refuse clicks made with an empty / open tray.

Centralising it here keeps the open() + ioctl call site honest (one
implementation, one set of error-mode decisions) and lets us keep the
mapping to DriveMediaStatus in one place.
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

    open() failure → UNKNOWN with the errno; ioctl unsupported also
    falls through to UNKNOWN since we can't tell a working drive from
    a misconfigured one. Callers that want "is this drive rip-ready"
    should compare to DriveMediaStatus.LOADED."""
    try:
        fd = os.open(device_path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as exc:
        # Kernel device unbound, /dev node missing, etc. — distinguish
        # this from "we read the drive and it had nothing to tell us"
        # (UNKNOWN) so callers can treat it as not-ready.
        return DriveMediaStatus.UNAVAILABLE, f"open: errno={exc.errno} {exc.strerror or exc}"
    try:
        try:
            raw = fcntl.ioctl(fd, _CDROM_DRIVE_STATUS, 0)
        except OSError as exc:
            return DriveMediaStatus.UNKNOWN, f"ioctl unsupported (errno={exc.errno})"
    finally:
        os.close(fd)
    status = _CDS_TO_ENUM.get(raw, DriveMediaStatus.UNKNOWN)
    return status, f"CDROM_DRIVE_STATUS={raw} ({status.value})"
