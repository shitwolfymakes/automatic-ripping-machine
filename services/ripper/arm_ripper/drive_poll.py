import errno
import fcntl
import os
from enum import IntEnum, StrEnum

# <linux/cdrom.h>
CDROM_DRIVE_STATUS = 0x5326

CDS_NO_INFO = 0
CDS_NO_DISC = 1
CDS_TRAY_OPEN = 2
CDS_DRIVE_NOT_READY = 3
CDS_DISC_OK = 4


class DriveState(IntEnum):
    NO_INFO = CDS_NO_INFO
    NO_DISC = CDS_NO_DISC
    TRAY_OPEN = CDS_TRAY_OPEN
    NOT_READY = CDS_DRIVE_NOT_READY
    DISC_OK = CDS_DISC_OK
    # Not a kernel value. The device node is missing or has no hardware behind
    # it (drive unplugged, or not yet enumerated). Neutral for InsertDetector,
    # like NO_INFO; the poll loop resets the detector explicitly on reattach.
    ABSENT = -1


class DriveErrorKind(StrEnum):
    """Why open()/ioctl on the drive node failed. Drives the poll loop's
    log-once-per-transition behaviour: each kind is one event, not a
    per-poll signal."""

    ABSENT = "absent"  # ENOENT / ENXIO / ENODEV — plug it in
    MISCONFIGURED = "misconfigured"  # EPERM / EACCES — cgroup rule or group is wrong
    OTHER = "other"  # EIO and friends — a real per-poll signal, keep logging


_ABSENT_ERRNOS = frozenset({errno.ENOENT, errno.ENXIO, errno.ENODEV})
_MISCONFIGURED_ERRNOS = frozenset({errno.EPERM, errno.EACCES})


def classify_drive_error(exc: OSError) -> DriveErrorKind:
    if exc.errno in _ABSENT_ERRNOS:
        return DriveErrorKind.ABSENT
    if exc.errno in _MISCONFIGURED_ERRNOS:
        return DriveErrorKind.MISCONFIGURED
    return DriveErrorKind.OTHER


def read_drive_status(device_path: str) -> DriveState:
    fd = os.open(device_path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        raw = fcntl.ioctl(fd, CDROM_DRIVE_STATUS)
    finally:
        os.close(fd)
    try:
        return DriveState(raw)
    except ValueError:
        return DriveState.NO_INFO


# A real drive only reports TRAY_OPEN for a ~2s flash when the tray opens,
# then reports NOT_READY for as long as the tray sits open. With the 2s
# poll interval that flash routinely lands between polls, so the only
# reliable "the tray was opened" signal is a sustained NOT_READY run. This
# is the number of consecutive NOT_READY readings (≈ this × POLL_INTERVAL
# seconds) past which we assume the disc was swapped and re-arm. A seated
# disc's spin transition clears in one or two polls, well under this.
# default fallback; production passes settings.ARM_NOT_READY_REARM_POLLS (Tier-4)
DEFAULT_NOT_READY_REARM_POLLS = 3


class InsertDetector:
    """Edge-detects 'a disc just became available to rip' from a stream of
    CDROM_DRIVE_STATUS readings.

    A naive `prev != DISC_OK and now == DISC_OK` edge does not work on real
    optical drives. On insertion the tray flashes TRAY_OPEN for ~2s, sits
    in NOT_READY while open, then spins up straight to DISC_OK — so a
    genuine insertion settles as `NOT_READY -> DISC_OK`. Excluding
    NOT_READY from the edge (the previous behaviour) swallowed every real
    insertion; including it double-fired on a seated disc's brief spin-flap.

    Instead we latch ``_handled`` when a rip is kicked off for the disc
    currently in the drive, and re-arm only once the disc has demonstrably
    left:

    * an unambiguous no-media reading (NO_DISC / TRAY_OPEN), or
    * NOT_READY sustained past ``not_ready_rearm_polls`` consecutive
      readings — the fallback for when the brief TRAY_OPEN flash falls
      between polls (the common case at a 2s interval).

    NO_INFO (ioctl failure / unknown, e.g. the device held busy mid-rip)
    is treated as neutral: it neither re-arms nor fires.
    """

    def __init__(self, *, not_ready_rearm_polls: int = DEFAULT_NOT_READY_REARM_POLLS) -> None:
        self._handled = False
        self._not_ready_streak = 0
        self._not_ready_rearm_polls = not_ready_rearm_polls

    def reset(self) -> None:
        """Forget the current disc. Called when the drive reattaches after an
        ABSENT run: whatever is in the tray now may be a different disc, so
        the next DISC_OK must fire."""
        self._handled = False
        self._not_ready_streak = 0

    def update(self, state: DriveState) -> bool:
        """Feed one reading; return True exactly once per insertion, when a
        rip pipeline should start for the disc now in the drive."""
        if state in (DriveState.NO_DISC, DriveState.TRAY_OPEN):
            self._handled = False

        if state == DriveState.NOT_READY:
            self._not_ready_streak += 1
            if self._not_ready_streak >= self._not_ready_rearm_polls:
                self._handled = False
        else:
            self._not_ready_streak = 0

        if state == DriveState.DISC_OK and not self._handled:
            self._handled = True
            return True
        return False
