"""Direct coverage of JobController.resume_inflight_job's single-flight gate."""

import asyncio
import logging
import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

from arm_common import DiscType, JobStatus  # noqa: E402
from arm_common.schemas import JobView, RipStartResponse  # noqa: E402
from arm_ripper import makemkv_prep as makemkv_prep_module  # noqa: E402
from arm_ripper.job_controller import JobController  # noqa: E402
from arm_ripper.makemkv_prep import MakeMKVPrep  # noqa: E402


class _Client:
    def __init__(self) -> None:
        self.resume_calls: list[str] = []

    async def resume(self, job_id: str) -> RipStartResponse:
        self.resume_calls.append(job_id)
        return RipStartResponse(
            end_on_completion_message=False, job_id=job_id, rip_preset_id="rp_1", tracks=[], min_length_seconds=None
        )


def _job() -> JobView:
    return JobView(
        id="job_r",
        drive_id="drv_test",
        disc_type=DiscType.DVD,
        status=JobStatus.RIPPING,
        title=None,
        year=None,
        metadata_json={},
        resumed_from_crash=True,
        wait_start_time=None,
        manual_pause=False,
    )


def _quiet(monkeypatch) -> None:
    async def _none(*a, **k):
        return None

    async def _false(*a, **k):
        return False

    monkeypatch.setattr(makemkv_prep_module, "refresh_makemkv_key", _none)
    monkeypatch.setattr(MakeMKVPrep, "_configured_makemkv_key", _none)
    monkeypatch.setattr(MakeMKVPrep, "_community_keydb_enabled", _false)
    monkeypatch.setattr(MakeMKVPrep, "_makemkv_sdf_enabled", _false)
    monkeypatch.setattr(MakeMKVPrep, "_spawn_keydb_refresh", lambda self, *, enabled: None)
    monkeypatch.setattr(MakeMKVPrep, "_spawn_sdf_refresh", lambda self, *, enabled: None)


async def test_resume_holds_the_single_flight_gate_while_ripping(monkeypatch) -> None:
    _quiet(monkeypatch)
    started = asyncio.Event()
    release = asyncio.Event()
    seen_idle: list[bool] = []

    async def _execute_rip(self, **kw) -> None:
        started.set()
        await release.wait()

    monkeypatch.setattr(JobController, "_execute_rip", _execute_rip)
    client = _Client()
    c = JobController(client, "drv_test", device_path="/dev/sr0")  # type: ignore[arg-type]
    assert c.is_idle()
    task = await c.resume_inflight_job(_job(), "/dev/sr0")
    assert task is not None
    await started.wait()
    seen_idle.append(c.is_idle())
    release.set()
    await task
    assert seen_idle == [False]  # gate held for the whole rip
    assert c.is_idle()  # and released after
    assert client.resume_calls == ["job_r"]


async def test_resume_releases_the_gate_when_the_rip_raises(monkeypatch) -> None:
    _quiet(monkeypatch)

    async def _boom(self, **kw) -> None:
        raise RuntimeError("makemkv died")

    monkeypatch.setattr(JobController, "_execute_rip", _boom)
    c = JobController(_Client(), "drv_test", device_path="/dev/sr0")  # type: ignore[arg-type]
    task = await c.resume_inflight_job(_job(), "/dev/sr0")
    assert task is not None
    await task  # the error is logged in the rip's own task
    assert c.is_idle()


async def test_resume_logs_rip_started_with_resumed_true(monkeypatch, caplog) -> None:
    _quiet(monkeypatch)

    async def _noop(self, **kw) -> None:
        return None

    monkeypatch.setattr(JobController, "_execute_rip", _noop)
    c = JobController(_Client(), "drv_test", device_path="/dev/sr0")  # type: ignore[arg-type]
    with caplog.at_level(logging.INFO, logger="arm_ripper.job_controller"):
        task = await c.resume_inflight_job(_job(), "/dev/sr0")
        assert task is not None
        await task
    (record,) = [r for r in caplog.records if getattr(r, "event", None) == "rip.started"]
    assert record.fields["resumed"] is True
    assert record.fields["disc_type"] == "dvd"
