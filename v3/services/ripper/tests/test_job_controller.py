"""JobController behaviour with a fake BackendClient and stubbed scan."""

import asyncio
from collections import deque
from datetime import datetime, timezone

import pytest

import arm_ripper.job_controller as jc_module
from arm_common import DiscType, Job, JobStatus
from arm_common.schemas import JobView, ScanResult
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
    )


class FakeClient:
    def __init__(self) -> None:
        self.identify_responses: deque[Job] = deque()
        self.get_job_responses: deque[JobView] = deque()
        self.identify_calls: list[ScanResult] = []
        self.get_job_calls: list[str] = []

    async def identify(self, *, drive_id: str, scan_result: ScanResult) -> Job:
        self.identify_calls.append(scan_result)
        return self.identify_responses.popleft()

    async def get_job(self, job_id: str) -> JobView:
        self.get_job_calls.append(job_id)
        return self.get_job_responses.popleft()


@pytest.fixture(autouse=True)
def fast_polls(monkeypatch):
    """Don't wait 5+ seconds between polls in tests."""
    monkeypatch.setattr(jc_module, "POLL_INITIAL_SECONDS", 0.0)
    monkeypatch.setattr(jc_module, "POLL_MAX_SECONDS", 0.01)


@pytest.fixture
def stub_scan(monkeypatch):
    async def _scan(_device_path: str) -> ScanResult:
        return ScanResult(disc_type=DiscType.DVD, volume_label="TEST")

    monkeypatch.setattr(jc_module, "scan_disc", _scan)


async def test_identified_returns_immediately(stub_scan):
    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.IDENTIFIED, title="Test Movie"))
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert len(client.identify_calls) == 1
    assert client.get_job_calls == []


async def test_awaiting_polls_until_resolved(stub_scan):
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

    assert len(client.identify_calls) == 1
    assert client.get_job_calls == ["job_test"] * 3


async def test_unexpected_status_stops_polling(stub_scan):
    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.AWAITING_USER_ID))
    client.get_job_responses.append(_view(JobStatus.ABANDONED))
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert client.get_job_calls == ["job_test"]
