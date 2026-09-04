import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

from arm_common import DiscType, JobStatus  # noqa: E402
from arm_common.schemas import JobView, RipStartResponse  # noqa: E402
from arm_ripper import job_controller as jc_module  # noqa: E402
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


class _RipClient:
    async def rip_complete(self, job_id: str) -> JobView:
        return JobView(
            id=job_id,
            drive_id="drv_1",
            disc_type=DiscType.DVD,
            status=JobStatus.RIPPED,
            title=None,
            year=None,
            metadata_json={},
            resumed_from_crash=False,
            wait_start_time=None,
            manual_pause=False,
        )


async def test_post_rip_eject_uses_the_handles_current_node(monkeypatch, tmp_path) -> None:
    """The node captured at rip start is stale after a mid-rip renumbering;
    eject must follow the handle (followups: Plan 1 drill finding)."""
    monkeypatch.setattr(jc_module, "RAW_ROOT", tmp_path)
    monkeypatch.setattr(jc_module, "EJECT_GRACE_SECONDS", 0.0)
    ejected: list[str] = []

    async def _rip_all(**kw):  # the rip itself is not under test
        handle.set("/dev/sr1")  # drive renumbered mid-rip

    async def _eject(self, device_path: str) -> None:
        ejected.append(device_path)

    monkeypatch.setattr(jc_module, "rip_all", _rip_all)
    monkeypatch.setattr(jc_module.JobController, "_eject_with_retry", _eject)
    handle = DriveHandle("/dev/sr0")
    c = JobController(_RipClient(), "drv_1", device_path=handle)  # type: ignore[arg-type]
    await c._execute_rip(
        job_id="job_1",
        disc_type=DiscType.DVD,
        device_path="/dev/sr0",
        rip_start=RipStartResponse(job_id="job_1", rip_preset_id="rp_1", tracks=[], min_length_seconds=None),
    )
    assert ejected == ["/dev/sr1"]
