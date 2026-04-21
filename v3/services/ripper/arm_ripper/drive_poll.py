import fcntl
import os
from enum import IntEnum

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
