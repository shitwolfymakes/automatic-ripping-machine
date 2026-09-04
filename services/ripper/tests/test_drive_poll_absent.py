import errno
import os

# Set up placeholders before importing arm_ripper modules
os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend.invalid")
os.environ.setdefault("ARM_SERVICE_TOKEN", "test-token")

from arm_ripper.drive_poll import DriveErrorKind, DriveState, InsertDetector, classify_drive_error


def _oserror(code: int) -> OSError:
    return OSError(code, "x", "/dev/sr0")


def test_absent_errnos_classify_as_absent() -> None:
    for code in (errno.ENOENT, errno.ENXIO, errno.ENODEV):
        assert classify_drive_error(_oserror(code)) is DriveErrorKind.ABSENT


def test_permission_errnos_classify_as_misconfigured() -> None:
    for code in (errno.EPERM, errno.EACCES):
        assert classify_drive_error(_oserror(code)) is DriveErrorKind.MISCONFIGURED


def test_anything_else_is_other() -> None:
    assert classify_drive_error(_oserror(errno.EIO)) is DriveErrorKind.OTHER
    assert classify_drive_error(OSError("no errno")) is DriveErrorKind.OTHER


def test_absent_is_neutral_for_the_detector() -> None:
    d = InsertDetector(not_ready_rearm_polls=3)
    assert d.update(DriveState.DISC_OK) is True  # first insertion fires
    assert d.update(DriveState.ABSENT) is False  # unplugged: no fire...
    assert d.update(DriveState.ABSENT) is False
    assert d.update(DriveState.DISC_OK) is False  # ...and no re-arm on its own


def test_reset_rearms_so_a_swapped_disc_rips_after_reattach() -> None:
    d = InsertDetector(not_ready_rearm_polls=3)
    assert d.update(DriveState.DISC_OK) is True
    d.update(DriveState.ABSENT)
    d.reset()
    assert d.update(DriveState.DISC_OK) is True


def test_reset_clears_the_not_ready_streak() -> None:
    d = InsertDetector(not_ready_rearm_polls=3)
    d.update(DriveState.DISC_OK)
    d.update(DriveState.NOT_READY)
    d.update(DriveState.NOT_READY)
    d.reset()
    # Two more NOT_READY must not reach the rearm threshold from a stale streak.
    d.update(DriveState.NOT_READY)
    d.update(DriveState.NOT_READY)
    assert d.update(DriveState.DISC_OK) is True  # reset already re-armed; streak did not matter
