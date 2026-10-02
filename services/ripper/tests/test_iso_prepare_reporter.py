"""ISO "preparing" reports: an ISO ripper tells the backend what it is doing
before identify creates its job (scanning the image, unpacking it with 7-Zip
for MakeMKV, scanning the unpacked folder), so the dashboard shows the rip."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import httpx
import pytest

os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend.invalid")
os.environ.setdefault("ARM_SERVICE_TOKEN", "test-token")

import arm_ripper.iso_extract as iso_extract  # noqa: E402
import arm_ripper.prepare as prepare  # noqa: E402
import arm_ripper.scan.dispatcher as scan_dispatcher  # noqa: E402
from arm_common import DiscType, IsoPreparePhase  # noqa: E402
from arm_common.schemas import ScanResult  # noqa: E402
from arm_ripper.scan.makemkv import ScanError  # noqa: E402

SCANNING, EXTRACTING = IsoPreparePhase.SCANNING, IsoPreparePhase.EXTRACTING


class _Client:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[IsoPreparePhase, int | None, str | None]] = []
        self._fail = fail

    async def report_iso_prepare(
        self, *, drive_id: str, phase: IsoPreparePhase, progress_pct: int | None, current_file: str | None
    ) -> None:
        assert drive_id == "drv_iso"
        if self._fail:
            raise httpx.ConnectError("backend down")
        self.sent.append((phase, progress_pct, current_file))


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(autouse=True)
def _unconfigured() -> Any:
    prepare.reset()
    yield
    prepare.reset()


# --- 7-Zip progress parsing --------------------------------------------------


def test_parse_progress_reads_the_last_percentage_and_file() -> None:
    text = "  0% Open\b\b\b\b\b\b\b\b\b  0%\b\b\b\b    \b\b\b\b 75% 3 - BDMV/STREAM/00002.m2ts\b\b\b\b"
    assert iso_extract.parse_progress(text) == (75, "BDMV/STREAM/00002.m2ts")


def test_parse_progress_without_a_file() -> None:
    assert iso_extract.parse_progress("\b\b\b 12%\b\b\b") == (12, None)


def test_parse_progress_none_without_a_percentage() -> None:
    assert iso_extract.parse_progress("  0M Scan /source/\b\b\b") is None


# --- reporter ----------------------------------------------------------------


async def test_unconfigured_reports_are_a_no_op() -> None:
    await prepare.report(SCANNING)  # source mode only; a physical drive never configures it
    await prepare.finish()


async def test_phase_changes_are_sent_and_progress_is_throttled() -> None:
    client, clock = _Client(), _Clock()
    prepare.configure(client, "drv_iso", min_interval=3.0, keepalive=3600, clock=clock)  # type: ignore[arg-type]

    await prepare.report(SCANNING)
    await prepare.report(EXTRACTING, 1, "BDMV/a")
    clock.now += 1
    await prepare.report(EXTRACTING, 2, "BDMV/a")  # too soon: dropped
    clock.now += 3
    await prepare.report(EXTRACTING, 5, "BDMV/b")
    await prepare.report(SCANNING)  # a phase change always goes out
    await prepare.finish()

    assert client.sent == [(SCANNING, None, None), (EXTRACTING, 1, "BDMV/a"), (EXTRACTING, 5, "BDMV/b"), (SCANNING, None, None)]


async def test_the_current_phase_is_resent_as_a_keepalive_until_finish() -> None:
    """A MakeMKV scan reports nothing for minutes; the keepalive keeps the
    backend's status from ageing out meanwhile."""
    client = _Client()
    prepare.configure(client, "drv_iso", keepalive=0.01)  # type: ignore[arg-type]

    await prepare.report(SCANNING)
    await asyncio.sleep(0.05)
    await prepare.finish()
    sent = len(client.sent)
    await asyncio.sleep(0.03)

    assert sent >= 3
    assert set(client.sent) == {(SCANNING, None, None)}
    assert len(client.sent) == sent  # nothing after finish


async def test_a_failed_report_never_breaks_the_pipeline() -> None:
    prepare.configure(_Client(fail=True), "drv_iso", keepalive=3600)  # type: ignore[arg-type]
    await prepare.report(SCANNING)
    await prepare.finish()


# --- who reports what --------------------------------------------------------


async def test_scan_reports_scanning_then_the_extraction_then_scanning_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    iso = tmp_path / "m.iso"
    iso.write_bytes(b"\0")
    phases: list[IsoPreparePhase] = []

    async def _report(phase: IsoPreparePhase, *_a: object) -> None:
        phases.append(phase)

    async def _makemkv(_p: str) -> ScanResult:
        if iso_extract.extracted_dir(str(iso)) is None:
            raise ScanError("makemkvcon exited -11")
        return ScanResult(disc_type=DiscType.BLURAY, titles=[{"index": 0, "duration_seconds": 5400}])

    async def _extract(path: str) -> Path:
        await prepare.report(EXTRACTING, 50, "BDMV/x")
        iso_extract._extracted[path] = tmp_path / "m"
        return tmp_path / "m"

    async def _data(_p: str) -> ScanResult:
        return ScanResult(disc_type=DiscType.BLURAY)

    monkeypatch.setattr(prepare, "report", _report)
    monkeypatch.setattr(scan_dispatcher, "scan_makemkv", _makemkv)
    monkeypatch.setattr(scan_dispatcher.iso_extract, "extract", _extract)
    monkeypatch.setattr(scan_dispatcher, "scan_data", _data)
    try:
        await scan_dispatcher.scan(str(iso))
    finally:
        iso_extract._extracted.clear()

    assert phases == [SCANNING, EXTRACTING, SCANNING]


class _Stream:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    async def read(self, _n: int = -1) -> bytes:
        await asyncio.sleep(0)
        return self._chunks.pop(0) if self._chunks else b""


async def test_extract_reports_7z_progress(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(iso_extract, "EXTRACT_ROOT", tmp_path / ".iso-extract")
    iso = tmp_path / "m.iso"
    iso.write_bytes(b"\0")
    reports: list[tuple[Any, ...]] = []

    async def _report(*args: Any) -> None:
        reports.append(args)

    monkeypatch.setattr(prepare, "report", _report)
    monkeypatch.setattr(iso_extract.shutil, "which", lambda name: "/usr/bin/7zz" if name == "7zz" else None)

    class _Proc:
        returncode = 0

        def __init__(self, out: str) -> None:
            self.stdout = _Stream([b"  0% Open\b\b\b\b\b\b\b\b\b", b" 40% 1 - BDMV/STREAM/0.m2ts\b\b", b" 90% 2 - BDMV/STREAM/1.m2ts"])
            self.stderr = _Stream([])
            (Path(out) / "BDMV").mkdir(parents=True)

        async def wait(self) -> int:
            return 0

    async def _exec(*args: str, **_k: object) -> _Proc:
        assert "-bsp1" in args
        return _Proc(next(a for a in args if a.startswith("-o"))[2:])

    monkeypatch.setattr(iso_extract.asyncio, "create_subprocess_exec", _exec)
    try:
        assert await iso_extract.extract(str(iso)) is not None
    finally:
        iso_extract.discard_all()

    assert reports[0] == (EXTRACTING, 0, None)
    assert (EXTRACTING, 40, "BDMV/STREAM/0.m2ts") in reports
    assert reports[-1] == (EXTRACTING, 90, "BDMV/STREAM/1.m2ts")
