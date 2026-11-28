"""A re-acquired rip runs in its own task, not in its caller's (#299).

`pickup` runs from the heartbeat loop, and `resume_inflight_job` /
`recover_held_job` from boot recovery (in amain before the heartbeat and poll
loops start, and in the poll loop on reattach). Run inline, the rip blocked the
heartbeat loop for its whole length, and `job.abandoned` cancelled whichever
task had awaited it: the heartbeat loop for good, or amain, exiting the ripper.
"""

import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

import asyncio
import logging

import pytest
from arm_common import DriveMediaStatus
from arm_common.enums import JobStatus
from arm_common.schemas.jobs import JobView

from arm_ripper import heartbeat as heartbeat_module
from arm_ripper.drive_handle import DriveHandle
from arm_ripper.heartbeat import heartbeat_loop
from arm_ripper.job_controller import JobController
from tests.test_job_controller import FakeClient, _view


class _HeartbeatClient:
    """Counts heartbeats and hands back a rip-ready job on the reprobe."""

    def __init__(self) -> None:
        self.beats = 0

    async def heartbeat(self, *, drive_id: str, media_status: DriveMediaStatus, scanning: bool = False) -> None:
        self.beats += 1

    async def get_current_job(self, drive_id: str) -> JobView:
        return _view(JobStatus.IDENTIFIED)


def _blocking_rip(controller: JobController) -> tuple[asyncio.Event, asyncio.Event]:
    started, release = asyncio.Event(), asyncio.Event()

    async def rip(job: JobView, device_path: str) -> None:
        started.set()
        await release.wait()

    controller._run_rip = rip  # type: ignore[method-assign]
    return started, release


async def _wait_for(predicate, timeout: float = 2.0) -> None:  # type: ignore[no-untyped-def]
    async def _poll() -> None:
        while not predicate():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(_poll(), timeout)


@pytest.fixture
def fast_heartbeat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(heartbeat_module, "HEARTBEAT_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(heartbeat_module, "_media_status", lambda _path: DriveMediaStatus.LOADED)


@pytest.mark.asyncio
async def test_heartbeats_keep_coming_while_a_reacquired_rip_runs(fast_heartbeat: None) -> None:
    controller = JobController(FakeClient(), "drv_test")
    started, release = _blocking_rip(controller)
    client = _HeartbeatClient()
    beat = asyncio.create_task(heartbeat_loop(client, "drv_test", DriveHandle("/dev/sr0"), controller))
    try:
        await asyncio.wait_for(started.wait(), 2.0)
        beats_at_start = client.beats
        await _wait_for(lambda: client.beats >= beats_at_start + 5)
        assert not controller.is_idle()  # still ripping: no second pickup either
    finally:
        release.set()
        beat.cancel()


@pytest.mark.asyncio
async def test_abandon_cancels_only_the_reacquired_rip(fast_heartbeat: None) -> None:
    controller = JobController(FakeClient(), "drv_test")
    started, _release = _blocking_rip(controller)
    client = _HeartbeatClient()
    beat = asyncio.create_task(heartbeat_loop(client, "drv_test", DriveHandle("/dev/sr0"), controller))
    try:
        await asyncio.wait_for(started.wait(), 2.0)
        rip = controller._active_task
        assert rip is not None and rip is not beat

        controller._handle_abandon("job_test", delete_raw=False)
        await _wait_for(lambda: rip.done())

        assert rip.cancelled()
        beats_after_abandon = client.beats
        await _wait_for(lambda: client.beats >= beats_after_abandon + 3)
        assert not beat.done()
    finally:
        beat.cancel()


@pytest.mark.asyncio
async def test_boot_resume_returns_to_its_caller_and_abandon_spares_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """Boot recovery returns while the resumed rip runs, so amain goes on to
    start the heartbeat and poll loops; abandoning the rip cancels the rip only."""
    controller = JobController(FakeClient(), "drv_test")
    started, _release = asyncio.Event(), asyncio.Event()

    async def execute_rip(**_kw: object) -> None:
        started.set()
        await _release.wait()

    async def no_prepare() -> None:
        return None

    controller._execute_rip = execute_rip  # type: ignore[method-assign]
    controller._makemkv.prepare = no_prepare  # type: ignore[method-assign]
    caller_carried_on = asyncio.Event()

    async def amain_like() -> None:
        await controller.resume_inflight_job(_view(JobStatus.RIPPING), "/dev/sr0")
        caller_carried_on.set()
        await asyncio.sleep(3600)

    caller = asyncio.create_task(amain_like())
    try:
        await asyncio.wait_for(caller_carried_on.wait(), 2.0)
        await asyncio.wait_for(started.wait(), 2.0)
        rip = controller._active_task
        assert rip is not None and rip is not caller

        controller._handle_abandon("job_test", delete_raw=False)
        await _wait_for(lambda: rip.done())

        assert rip.cancelled()
        assert not caller.done()
    finally:
        caller.cancel()


@pytest.mark.asyncio
async def test_boot_repark_returns_to_its_caller_while_it_waits_for_start() -> None:
    controller = JobController(FakeClient(), "drv_test")
    waiting = asyncio.Event()

    async def await_resolution(job_id: str, spec: object) -> JobView | None:
        waiting.set()
        await asyncio.sleep(3600)  # the operator hasn't pressed Start yet
        return None

    controller._waiter.await_resolution = await_resolution  # type: ignore[method-assign]

    task = await controller.recover_held_job(_view(JobStatus.AWAITING_REVIEW), "/dev/sr0")

    assert task is not None
    await asyncio.wait_for(waiting.wait(), 2.0)
    assert not controller.is_idle()
    controller._handle_abandon("job_test", delete_raw=False)
    await _wait_for(lambda: task.done())
    assert controller.is_idle()


@pytest.mark.asyncio
async def test_a_failing_reacquired_rip_is_logged_and_frees_the_gate(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR, logger="arm_ripper.job_controller")
    controller = JobController(FakeClient(), "drv_test")

    async def boom(job: JobView, device_path: str) -> None:
        raise RuntimeError("boom")

    controller._run_rip = boom  # type: ignore[method-assign]

    task = await controller.pickup(_view(JobStatus.IDENTIFIED), "/dev/sr0")
    assert task is not None
    await task

    assert controller.is_idle()
    assert any("pickup failed for job_id=job_test" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["resume_inflight_job", "recover_held_job"])
async def test_boot_recovery_is_skipped_while_another_rip_owns_the_drive(
    method: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="arm_ripper.job_controller")
    controller = JobController(FakeClient(), "drv_test")
    controller._active_task = object()  # type: ignore[assignment]

    assert await getattr(controller, method)(_view(JobStatus.RIPPING), "/dev/sr0") is None
    assert any("controller already busy" in r.getMessage() for r in caplog.records)
