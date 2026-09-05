import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

import pytest
from arm_common.enums import JobStatus
from arm_common.schemas.jobs import JobView
from arm_ripper.main import maybe_reacquire_current_job


class _Ctrl:
    def __init__(self, *, idle: bool):
        self._idle = idle
        self.picked: str | None = None

    def is_idle(self) -> bool:
        return self._idle

    async def pickup(self, job, device_path):
        self.picked = job.id


def _jobview(status):
    return JobView(
        id="job_x",
        drive_id="drv_1",
        disc_type="dvd",
        status=status,
        title=None,
        year=None,
        metadata_json={},
        resumed_from_crash=False,
    )


@pytest.mark.asyncio
async def test_reacquire_when_idle_seated_and_identified():
    ctrl = _Ctrl(idle=True)

    async def fake_get_current(drive_id):
        return _jobview(JobStatus.IDENTIFIED)

    await maybe_reacquire_current_job(
        ctrl, get_current_job=fake_get_current, drive_id="drv_1", device_path="/dev/sr0", seated=True
    )
    assert ctrl.picked == "job_x"


@pytest.mark.asyncio
async def test_no_reacquire_when_busy():
    ctrl = _Ctrl(idle=False)

    async def fake_get_current(drive_id):
        return _jobview(JobStatus.IDENTIFIED)

    await maybe_reacquire_current_job(
        ctrl, get_current_job=fake_get_current, drive_id="drv_1", device_path="/dev/sr0", seated=True
    )
    assert ctrl.picked is None


@pytest.mark.asyncio
async def test_no_reacquire_when_no_disc():
    ctrl = _Ctrl(idle=True)

    async def fake_get_current(drive_id):
        return _jobview(JobStatus.IDENTIFIED)

    await maybe_reacquire_current_job(
        ctrl, get_current_job=fake_get_current, drive_id="drv_1", device_path="/dev/sr0", seated=False
    )
    assert ctrl.picked is None


@pytest.mark.asyncio
async def test_no_reacquire_when_no_current_job():
    ctrl = _Ctrl(idle=True)

    async def fake_get_current(drive_id):
        return None

    await maybe_reacquire_current_job(
        ctrl, get_current_job=fake_get_current, drive_id="drv_1", device_path="/dev/sr0", seated=True
    )
    assert ctrl.picked is None


@pytest.mark.asyncio
async def test_no_reacquire_when_status_not_rip_ready():
    """Jobs in terminal/non-rip-ready statuses should not be re-acquired."""
    ctrl = _Ctrl(idle=True)

    async def fake_get_current(drive_id):
        return _jobview(JobStatus.ABANDONED)

    await maybe_reacquire_current_job(
        ctrl, get_current_job=fake_get_current, drive_id="drv_1", device_path="/dev/sr0", seated=True
    )
    assert ctrl.picked is None


@pytest.mark.asyncio
async def test_reacquire_when_status_ripping():
    """RIPPING status is in _RIP_READY so it should trigger pickup."""
    ctrl = _Ctrl(idle=True)

    async def fake_get_current(drive_id):
        return _jobview(JobStatus.RIPPING)

    await maybe_reacquire_current_job(
        ctrl, get_current_job=fake_get_current, drive_id="drv_1", device_path="/dev/sr0", seated=True
    )
    assert ctrl.picked == "job_x"


@pytest.mark.asyncio
async def test_no_reacquire_when_status_awaiting_review():
    """AWAITING_REVIEW must NOT trigger pickup via the heartbeat reprobe.

    Review-gated discs go through _review_countdown_expired / _await_resolution,
    which honour the countdown, manual_pause, and global ripping_paused.  Picking
    up here would call controller.pickup → _run_rip → rip_start and bypass all
    three guards — so AWAITING_REVIEW is excluded from _RIP_READY.
    """
    ctrl = _Ctrl(idle=True)

    async def fake_get_current(drive_id):
        return _jobview(JobStatus.AWAITING_REVIEW)

    await maybe_reacquire_current_job(
        ctrl, get_current_job=fake_get_current, drive_id="drv_1", device_path="/dev/sr0", seated=True
    )
    assert ctrl.picked is None


@pytest.mark.asyncio
async def test_errors_are_swallowed():
    """Errors from get_current_job must be swallowed; no exception propagates."""
    ctrl = _Ctrl(idle=True)

    async def fake_get_current(drive_id):
        import httpx

        raise httpx.ConnectError("connection refused")

    # Should not raise
    await maybe_reacquire_current_job(
        ctrl, get_current_job=fake_get_current, drive_id="drv_1", device_path="/dev/sr0", seated=True
    )
    assert ctrl.picked is None
