"""Synchronous drive-status probe shared across the ripper service.

Two callers:
  - rip/dispatcher._wait_for_drive_ready uses this to gate the next
    title in a multi-title rip on the medium being ready. Pass
    `verify_read=True` so the probe actually pulls bytes off the
    disc — CDS_DISC_OK alone is necessary but not sufficient: the
    LG BP50NB40 (and other USB BD drives) reports CDS_DISC_OK while
    the medium is parked, then returns SCSI NOT_READY when
    makemkvcon issues its first read seconds later.
  - the heartbeat task posts the same reading to the backend so the
    manual-rip API can refuse clicks made with an empty / open tray.
    Uses `verify_read=False` to keep the periodic call cheap; it
    only needs the medium-presence signal, not I/O readiness.

Centralising it here keeps the open() + ioctl call site honest (one
implementation, one set of error-mode decisions) and lets us keep the
mapping to DriveMediaStatus in one place.
"""

from __future__ import annotations

import errno as _errno
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

# A read-verify probe pulls one optical-block (2 KiB) from offset 0 to
# confirm the drive is actually delivering bytes, not just that the
# kernel knows about a medium. The errnos below mean "drive can't
# deliver right now" — treat them like the SCSI NOT_READY case.
_NOT_READY_READ_ERRNOS = frozenset(
    {
        _errno.EIO,  # generic I/O failure (often = SCSI NOT_READY)
        _errno.ENOMEDIUM,  # no medium loaded (kernel layer)
        _errno.ENXIO,  # device exists but no medium / not ready
        _errno.EAGAIN,  # non-blocking read on a not-yet-ready device
    }
)


def probe_drive_media(device_path: str, *, verify_read: bool = False) -> tuple[DriveMediaStatus, str]:
    """Return (status, human-readable reason). Never raises.

    open() failure → UNAVAILABLE; ioctl unsupported → UNKNOWN. When
    `verify_read=True` and the ioctl reports LOADED, additionally pull
    one block off offset 0 — if that read fails with a transient errno
    (EIO / ENOMEDIUM / ENXIO / EAGAIN) we downgrade to NOT_READY so
    the wait loop keeps polling instead of declaring victory and
    handing off to makemkvcon."""
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
        if verify_read and status is DriveMediaStatus.LOADED:
            try:
                # A 2 KiB read at offset 0 forces the drive to deliver
                # actual bytes. On a parked-but-recognised disc this
                # raises EIO/ENOMEDIUM; on a healthy ready drive it
                # returns immediately with the volume descriptor.
                os.lseek(fd, 0, os.SEEK_SET)
                os.read(fd, 2048)
            except OSError as exc:
                if exc.errno in _NOT_READY_READ_ERRNOS:
                    return (
                        DriveMediaStatus.NOT_READY,
                        f"verify-read: errno={exc.errno} {exc.strerror or exc}",
                    )
                # Anything else (e.g. EBADF) is unexpected — log and
                # report UNKNOWN so we don't loop forever on it.
                logger.warning("probe verify-read errored unexpectedly: %s", exc)
                return DriveMediaStatus.UNKNOWN, f"verify-read errno={exc.errno}"
            return DriveMediaStatus.LOADED, f"CDROM_DRIVE_STATUS={raw}; verify-read ok"
    finally:
        os.close(fd)
    return status, f"CDROM_DRIVE_STATUS={raw} ({status.value})"
