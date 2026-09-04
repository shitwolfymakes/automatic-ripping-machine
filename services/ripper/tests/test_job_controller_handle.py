import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

from arm_ripper.drive_handle import DriveHandle  # noqa: E402
from arm_ripper.job_controller import JobController  # noqa: E402


class _Client:  # the controller only stores it in these tests
    pass


def test_controller_follows_a_shared_handle() -> None:
    h = DriveHandle("/dev/sr0")
    c = JobController(_Client(), "drv_1", device_path=h)  # type: ignore[arg-type]
    assert c._device_path == "/dev/sr0"
    h.set("/dev/sr2")
    assert c._device_path == "/dev/sr2"  # no copy was taken
    h.set(None)
    assert c._device_path is None


def test_a_plain_string_still_works_as_a_fixed_handle() -> None:
    c = JobController(_Client(), "drv_1", device_path="/tmp/disc.iso")  # type: ignore[arg-type]
    assert c._device_path == "/tmp/disc.iso"


def test_none_is_an_absent_handle() -> None:
    c = JobController(_Client(), "drv_1")  # type: ignore[arg-type]
    assert c._device_path is None
