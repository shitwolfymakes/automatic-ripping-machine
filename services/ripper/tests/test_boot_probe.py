"""Phase 9 — `boot_probe` orchestration with a fake BackendClient and
stubbed ioctl. We don't exercise the rip-loop itself; only that the
probe makes the right control-flow decisions before handing off.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

import arm_ripper.recovery as recovery_module
from arm_common import DiscType, JobStatus
from arm_common.schemas import JobView, RipStartResponse
from arm_ripper.drive_poll import DriveState
from arm_ripper.recovery import boot_probe, wipe_raw_dir


def _make_view() -> JobView:
    return JobView(
        id="job_resume",
        drive_id="drv_x",
        disc_type=DiscType.DVD,
        status=JobStatus.RIPPING,
        title="Iron Man",
        year=2008,
        metadata_json={},
        resumed_from_crash=True,
    )


class FakeBackendClient:
    def __init__(
        self,
        *,
        in_flight: JobView | None = None,
        in_flight_raises: Exception | None = None,
    ) -> None:
        self._in_flight = in_flight
        self._in_flight_raises = in_flight_raises
        self.in_flight_calls: list[str] = []
        self.resume_calls: list[str] = []
        self.resume_raises: Exception | None = None

    async def get_in_flight_job(self, drive_id: str) -> JobView | None:
        self.in_flight_calls.append(drive_id)
        if self._in_flight_raises is not None:
            raise self._in_flight_raises
        return self._in_flight

    async def resume(self, job_id: str) -> RipStartResponse:
        self.resume_calls.append(job_id)
        if self.resume_raises is not None:
            raise self.resume_raises
        return RipStartResponse(job_id=job_id, rip_preset_id="rpr_x", tracks=[])


class FakeController:
    def __init__(self) -> None:
        self.resume_calls: list[tuple[str, str]] = []
        self.raises: Exception | None = None

    async def resume_inflight_job(self, job: JobView, device_path: str) -> None:
        self.resume_calls.append((job.id, device_path))
        if self.raises is not None:
            raise self.raises


@pytest.fixture(autouse=True)
def patch_raw_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recovery_module, "RAW_ROOT", tmp_path)


@pytest.fixture
def stub_disc_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recovery_module, "read_drive_status", lambda _p: DriveState.DISC_OK)


@pytest.fixture
def stub_no_disc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recovery_module, "read_drive_status", lambda _p: DriveState.NO_DISC)


@pytest.mark.asyncio
async def test_no_inflight_is_noop() -> None:
    client = FakeBackendClient(in_flight=None)
    controller = FakeController()

    await boot_probe(client, "drv_x", "/dev/sr0", controller)  # type: ignore[arg-type]

    assert client.in_flight_calls == ["drv_x"]
    assert controller.resume_calls == []


@pytest.mark.asyncio
async def test_inflight_but_disc_absent_skips(stub_no_disc: None) -> None:
    view = _make_view()
    client = FakeBackendClient(in_flight=view)
    controller = FakeController()

    await boot_probe(client, "drv_x", "/dev/sr0", controller)  # type: ignore[arg-type]

    assert controller.resume_calls == []


@pytest.mark.asyncio
async def test_inflight_with_disc_wipes_and_resumes(stub_disc_ok: None, tmp_path: Path) -> None:
    # Pre-create /raw/<job_id>/ with content; assert the wipe takes it out.
    raw_dir = tmp_path / "job_resume"
    raw_dir.mkdir()
    (raw_dir / "leftover.mkv").write_text("garbage")
    assert raw_dir.exists()

    view = _make_view()
    client = FakeBackendClient(in_flight=view)
    controller = FakeController()

    await boot_probe(client, "drv_x", "/dev/sr0", controller)  # type: ignore[arg-type]

    assert not raw_dir.exists()
    assert controller.resume_calls == [("job_resume", "/dev/sr0")]


@pytest.mark.asyncio
async def test_resume_failure_logged_not_propagated(stub_disc_ok: None, caplog: pytest.LogCaptureFixture) -> None:
    view = _make_view()
    client = FakeBackendClient(in_flight=view)
    controller = FakeController()
    controller.raises = RuntimeError("kaboom")

    # Must not raise.
    await boot_probe(client, "drv_x", "/dev/sr0", controller)  # type: ignore[arg-type]

    assert controller.resume_calls == [("job_resume", "/dev/sr0")]
    assert any("resume failed" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_in_flight_lookup_http_error_swallowed() -> None:
    client = FakeBackendClient(in_flight_raises=httpx.ConnectError("backend down"))
    controller = FakeController()

    await boot_probe(client, "drv_x", "/dev/sr0", controller)  # type: ignore[arg-type]

    assert controller.resume_calls == []


def test_wipe_raw_dir_idempotent_when_missing(tmp_path: Path) -> None:
    # Different job_id — directory does not exist. Should not raise.
    wipe_raw_dir("never_existed")
