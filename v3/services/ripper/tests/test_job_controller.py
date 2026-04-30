"""JobController behaviour with a fake BackendClient and stubbed scan."""

import asyncio
from collections import deque
from datetime import datetime, timezone

import pytest

import arm_ripper.job_controller as jc_module
from arm_common import DiscType, Job, JobStatus
from arm_common.schemas import JobView, RipStartResponse, ScanResult, TrackView, WSEnvelope
from arm_ripper.job_controller import JobController


def _job(status: JobStatus, *, title: str | None = None) -> Job:
    return Job(
        id="job_test",
        drive_id="drv_test",
        disc_type=DiscType.DVD,
        status=status,
        title=title,
        year=None,
        metadata_json={},
        resumed_from_crash=False,
        started_at=None,
        ripped_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _view(status: JobStatus, *, title: str | None = None) -> JobView:
    return JobView(
        id="job_test",
        drive_id="drv_test",
        disc_type=DiscType.DVD,
        status=status,
        title=title,
        year=None,
        metadata_json={},
        resumed_from_crash=False,
    )


class FakeClient:
    def __init__(self) -> None:
        self.identify_responses: deque[Job] = deque()
        self.get_job_responses: deque[JobView] = deque()
        self.identify_calls: list[ScanResult] = []
        self.get_job_calls: list[str] = []
        self.rip_start_calls: list[str] = []
        self.rip_complete_calls: list[str] = []

    async def identify(self, *, drive_id: str, scan_result: ScanResult) -> Job:
        self.identify_calls.append(scan_result)
        return self.identify_responses.popleft()

    async def get_job(self, job_id: str) -> JobView:
        self.get_job_calls.append(job_id)
        return self.get_job_responses.popleft()

    async def rip_start(self, job_id: str) -> RipStartResponse:
        self.rip_start_calls.append(job_id)
        return RipStartResponse(
            job_id=job_id,
            rip_preset_id="rpr_builtin_movie_archive",
            tracks=[],
        )

    async def update_track(self, track_id: str, **fields: object) -> TrackView:  # pragma: no cover
        raise AssertionError("update_track should not be called when track list is empty")

    async def rip_complete(self, job_id: str) -> JobView:
        self.rip_complete_calls.append(job_id)
        return _view(JobStatus.RIPPED)


@pytest.fixture(autouse=True)
def fast_polls(monkeypatch, tmp_path):
    """Don't wait 5+ seconds between polls; write under tmp_path, not /raw."""
    monkeypatch.setattr(jc_module, "POLL_INITIAL_SECONDS", 0.0)
    monkeypatch.setattr(jc_module, "POLL_MAX_SECONDS", 0.01)
    monkeypatch.setattr(jc_module, "EJECT_GRACE_SECONDS", 0.0)
    monkeypatch.setattr(jc_module, "RAW_ROOT", tmp_path)
    # WS-driven resolution path: collapse the boot-race grace window so
    # tests fall straight through to the REST fallback path that the
    # FakeClient feeds.
    monkeypatch.setattr(jc_module, "RESOLUTION_WS_FIRST_WAIT_SECONDS", 0.0)
    monkeypatch.setattr(jc_module, "RESOLUTION_WAIT_TIMEOUT_SECONDS", 1.0)


@pytest.fixture
def stub_eject(monkeypatch):
    async def _noop_eject(self, device_path: str) -> None:
        return None

    monkeypatch.setattr(jc_module.JobController, "_eject_with_retry", _noop_eject)


@pytest.fixture
def stub_scan(monkeypatch):
    async def _scan(_device_path: str) -> ScanResult:
        return ScanResult(disc_type=DiscType.DVD, volume_label="TEST")

    monkeypatch.setattr(jc_module, "scan_disc", _scan)


async def test_identified_runs_rip_with_empty_tracks(stub_scan, stub_eject):
    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.IDENTIFIED, title="Test Movie"))
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert len(client.identify_calls) == 1
    assert client.rip_start_calls == ["job_test"]
    assert client.rip_complete_calls == ["job_test"]


async def test_awaiting_polls_until_resolved_then_rips(stub_scan, stub_eject):
    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.AWAITING_USER_ID))
    client.get_job_responses.extend(
        [
            _view(JobStatus.AWAITING_USER_ID),
            _view(JobStatus.AWAITING_USER_ID),
            _view(JobStatus.IDENTIFIED, title="Resolved"),
        ]
    )
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert client.rip_start_calls == ["job_test"]
    assert client.rip_complete_calls == ["job_test"]


async def test_unexpected_status_stops_without_rip(stub_scan, stub_eject):
    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.AWAITING_USER_ID))
    client.get_job_responses.append(_view(JobStatus.ABANDONED))
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert client.rip_start_calls == []
    assert client.rip_complete_calls == []


async def test_ws_event_unblocks_resolution_faster_than_rest(monkeypatch, stub_scan, stub_eject):
    """An identify.resolved WS event makes _await_resolution return immediately.

    Confirms the new WS-driven path: registering the handler is enough; we
    don't need the slow REST fallback to do the work.
    """
    monkeypatch.setattr(jc_module, "RESOLUTION_WS_FIRST_WAIT_SECONDS", 5.0)
    monkeypatch.setattr(jc_module, "RESOLUTION_WAIT_TIMEOUT_SECONDS", 30.0)

    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.AWAITING_USER_ID))
    # Once the WS handler fires, we still verify via REST get_job — feed identified.
    client.get_job_responses.append(_view(JobStatus.IDENTIFIED, title="Resolved"))
    controller = JobController(client, "drv_test")

    async def fire_ws_event_after_a_tick() -> None:
        # Yield twice so handle_disc_inserted reaches _wait_for_resolution.
        await asyncio.sleep(0.05)
        envelope = WSEnvelope(
            event_id="evt_test",
            event_type="identify.resolved",
            emitted_at=datetime.now(timezone.utc),
            topic="ripper.commands.drv_test",
            job_id="job_test",
            payload={"job_id": "job_test", "title": "Resolved"},
        )
        await controller.on_ws_command(envelope)

    await asyncio.wait_for(
        asyncio.gather(
            controller.handle_disc_inserted("/dev/sr0"),
            fire_ws_event_after_a_tick(),
        ),
        timeout=2.0,
    )

    assert client.rip_start_calls == ["job_test"]
    assert client.rip_complete_calls == ["job_test"]


async def test_eject_runs_umount_then_eject_until_success(monkeypatch):
    monkeypatch.setattr(jc_module, "EJECT_RETRY_DELAYS", (0.0, 0.0, 0.0))

    invocations: list[tuple[str, ...]] = []
    rc_sequence = iter([1, 1, 1, 0])  # umount fails, eject 1+2 fail, eject 3 succeeds

    async def _fake_run(*argv: str, log_failure: bool = True) -> tuple[int | None, str]:
        invocations.append(argv)
        return next(rc_sequence), "Device or resource busy"

    monkeypatch.setattr(JobController, "_run_command", staticmethod(_fake_run))
    controller = JobController(FakeClient(), "drv_test")
    await controller._eject_with_retry("/dev/sr0")

    assert invocations[0] == ("umount", "/dev/sr0")
    assert all(call[0] == "eject" for call in invocations[1:])
    assert len(invocations) == 4


async def test_eject_gives_up_after_all_attempts(monkeypatch, caplog):
    monkeypatch.setattr(jc_module, "EJECT_RETRY_DELAYS", (0.0, 0.0))

    async def _always_busy(*argv: str, log_failure: bool = True) -> tuple[int | None, str]:
        return 1, "Device or resource busy"

    monkeypatch.setattr(JobController, "_run_command", staticmethod(_always_busy))
    controller = JobController(FakeClient(), "drv_test")
    with caplog.at_level("ERROR", logger="arm_ripper.job_controller"):
        await controller._eject_with_retry("/dev/sr0")

    assert any("check host auto-mount config" in r.message for r in caplog.records)
