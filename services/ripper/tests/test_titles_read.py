"""The background MakeMKV title read of a structure-scan disc: what it posts, and what waiting on it answers."""

import asyncio
import logging
from typing import Any

import httpx
import pytest

import arm_ripper.titles_read as titles_read_module
from arm_common import ScanFailureReason
from arm_common.schemas import ScanFailure, ScanTitle, TitlesReport
from arm_ripper.scan.makemkv import MakemkvScanFailed, ScanError
from arm_ripper.titles_read import NO_TITLES_FAILURE, TitlesRead

JOB = "job_test"


class _Backend:
    def __init__(self, error: Exception | None = None) -> None:
        self.reports: list[tuple[str, TitlesReport]] = []
        self.error = error

    async def post_titles(self, job_id: str, report: TitlesReport) -> None:
        if self.error is not None:
            raise self.error
        self.reports.append((job_id, report))


def _scan_titles(monkeypatch: pytest.MonkeyPatch, result: list[ScanTitle] | Exception) -> list[str]:
    devices: list[str] = []

    async def _fake(device_path: str, _min_title_length_seconds: int, **_options: object) -> list[ScanTitle]:
        devices.append(device_path)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(titles_read_module, "scan_titles", _fake)
    return devices


async def test_the_titles_makemkv_lists_are_posted(monkeypatch: pytest.MonkeyPatch) -> None:
    titles = [ScanTitle(index=0, duration_seconds=7200, source_file="00001.mpls")]
    devices = _scan_titles(monkeypatch, titles)
    backend = _Backend()
    read = TitlesRead(backend)  # type: ignore[arg-type]
    read.start(JOB, "/dev/sr0", 120, 1200)
    assert await read.wait(JOB) is True
    assert devices == ["/dev/sr0"]
    assert backend.reports == [(JOB, TitlesReport(titles=titles))]


@pytest.mark.parametrize("error", [ScanError("makemkvcon timed out after 300.0s"), OSError("device gone")])
async def test_a_failed_read_posts_the_reason(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    _scan_titles(monkeypatch, error)
    backend = _Backend()
    read = TitlesRead(backend)  # type: ignore[arg-type]
    read.start(JOB, "/dev/sr0", 120, 1200)
    assert await read.wait(JOB) is False
    failure = ScanFailure(reason=ScanFailureReason.MAKEMKV_ERROR, detail=str(error))
    assert backend.reports == [(JOB, TitlesReport(failure=failure))]


async def test_a_makemkv_scan_failure_posts_its_typed_reason_and_output(monkeypatch: pytest.MonkeyPatch) -> None:
    _scan_titles(monkeypatch, MakemkvScanFailed(ScanFailureReason.VOLUME_KEY_UNKNOWN, "no key", ('MSG:3303,0,1,"x"',)))
    backend = _Backend()
    read = TitlesRead(backend)  # type: ignore[arg-type]
    read.start(JOB, "/dev/sr0", 120, 1200)
    assert await read.wait(JOB) is False
    failure = ScanFailure(
        reason=ScanFailureReason.VOLUME_KEY_UNKNOWN, detail="no key", output_tail=['MSG:3303,0,1,"x"']
    )
    assert backend.reports == [(JOB, TitlesReport(failure=failure))]


async def test_a_disc_makemkv_lists_nothing_on_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _scan_titles(monkeypatch, [])
    backend = _Backend()
    read = TitlesRead(backend)  # type: ignore[arg-type]
    read.start(JOB, "/dev/sr0", 120, 1200)
    assert await read.wait(JOB) is False
    failure = ScanFailure(reason=ScanFailureReason.MAKEMKV_ERROR, detail=NO_TITLES_FAILURE)
    assert backend.reports == [(JOB, TitlesReport(failure=failure))]


async def test_a_post_the_backend_rejects_is_a_failed_read(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _scan_titles(monkeypatch, [ScanTitle(index=0, duration_seconds=7200)])
    request = httpx.Request("POST", "https://bk/api/ripper/jobs/job_test/titles")
    rejected = httpx.HTTPStatusError("409", request=request, response=httpx.Response(409, request=request))
    read = TitlesRead(_Backend(rejected))  # type: ignore[arg-type]
    with caplog.at_level(logging.WARNING):
        read.start(JOB, "/dev/sr0", 120, 1200)
        assert await read.wait(JOB) is False
    assert "titles post for job_test rejected" in caplog.text


async def test_waiting_with_no_read_in_flight_is_a_no_op() -> None:
    assert await TitlesRead(_Backend()).wait(JOB) is True  # type: ignore[arg-type]


async def test_the_answer_is_kept_for_a_second_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    _scan_titles(monkeypatch, ScanError("no key"))
    read = TitlesRead(_Backend())  # type: ignore[arg-type]
    read.start(JOB, "/dev/sr0", 120, 1200)
    assert await read.wait(JOB) is False
    assert await read.wait(JOB) is False


async def test_start_replaces_a_read_still_running(monkeypatch: pytest.MonkeyPatch) -> None:
    release = asyncio.Event()
    calls: list[int] = []

    async def _slow(_device: str, _min_title_length_seconds: int, **_options: object) -> list[ScanTitle]:
        calls.append(len(calls))
        await release.wait()
        return [ScanTitle(index=0, duration_seconds=7200)]

    monkeypatch.setattr(titles_read_module, "scan_titles", _slow)
    backend = _Backend()
    read = TitlesRead(backend)  # type: ignore[arg-type]
    read.start(JOB, "/dev/sr0", 120, 1200)
    await asyncio.sleep(0)
    first = read._tasks[JOB]
    read.start(JOB, "/dev/sr0", 120, 1200)
    await asyncio.sleep(0)
    assert first.cancelled() or first.cancelling()
    release.set()
    assert await read.wait(JOB) is True
    assert len(backend.reports) == 1


async def test_cancel_stops_a_running_read(monkeypatch: pytest.MonkeyPatch) -> None:
    started = asyncio.Event()
    cancelled: list[bool] = []

    async def _hang(_device: str, _min_title_length_seconds: int, **_options: object) -> list[ScanTitle]:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
        return []  # pragma: no cover

    monkeypatch.setattr(titles_read_module, "scan_titles", _hang)
    read = TitlesRead(_Backend())  # type: ignore[arg-type]
    read.start(JOB, "/dev/sr0", 120, 1200)
    await started.wait()
    await read.cancel(JOB)
    assert cancelled == [True]
    assert await read.wait(JOB) is True  # nothing in flight any more


async def test_cancel_with_nothing_running_is_a_no_op() -> None:
    await TitlesRead(_Backend()).cancel(JOB)  # type: ignore[arg-type]


async def test_wait_raises_when_the_waiting_task_is_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    release = asyncio.Event()

    async def _hang(_device: str, _min_title_length_seconds: int, **_options: object) -> list[ScanTitle]:
        await release.wait()
        return [ScanTitle(index=0, duration_seconds=7200)]

    monkeypatch.setattr(titles_read_module, "scan_titles", _hang)
    read = TitlesRead(_Backend())  # type: ignore[arg-type]
    read.start(JOB, "/dev/sr0", 120, 1200)
    waiter: asyncio.Task[Any] = asyncio.create_task(read.wait(JOB))
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    await read.cancel(JOB)
