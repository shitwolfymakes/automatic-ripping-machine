"""Characterization tests for `scan_disc`: failure modes, fingerprints and disc-type choice."""

from __future__ import annotations

import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend.invalid")
os.environ.setdefault("ARM_SERVICE_TOKEN", "test-token")

import asyncio  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from arm_common.enums import DiscType, ScanFailureReason  # noqa: E402
from arm_common.schemas import DiscFingerprintInput  # noqa: E402

import arm_ripper.scan.makemkv as makemkv_mod  # noqa: E402
from arm_ripper.scan.disc_probe import DiscProbe  # noqa: E402
from arm_ripper.scan.makemkv import (
    MakemkvScanFailed,
    ScanError,
    disc_fingerprints,
    scan_disc,
    scan_titles,
)  # noqa: E402


class _Stream:
    def __init__(self, data: bytes) -> None:
        self._lines = data.splitlines(keepends=True)

    def __aiter__(self) -> _Stream:
        return self

    async def __anext__(self) -> bytes:
        if not self._lines:
            raise StopAsyncIteration
        return self._lines.pop(0)


class _HangingStream:
    """Stdout that never ends until released (by kill)."""

    def __init__(self) -> None:
        self.released = asyncio.Event()

    def __aiter__(self) -> _HangingStream:
        return self

    async def __anext__(self) -> bytes:
        await self.released.wait()
        raise StopAsyncIteration


class _Proc:
    def __init__(self, stdout: Any, stderr: bytes = b"", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = _Stream(stderr)
        self.returncode: int | None = None
        self._rc = returncode
        self.killed = False
        self.waited = False

    def kill(self) -> None:
        self.killed = True
        if isinstance(self.stdout, _HangingStream):
            self.stdout.released.set()

    async def wait(self) -> int:
        self.waited = True
        self.returncode = -9 if self.killed else self._rc
        return self.returncode


def _spawn(monkeypatch: pytest.MonkeyPatch, proc: _Proc) -> None:
    async def _factory(*_a: Any, **_kw: Any) -> _Proc:
        return proc

    monkeypatch.setattr(makemkv_mod.asyncio, "create_subprocess_exec", _factory)


def _run_ok(monkeypatch: pytest.MonkeyPatch, stdout: bytes, probe: DiscProbe) -> list[bool]:
    """Fake a clean makemkvcon run and probe_disc; returns the recorded `bluray` flags."""
    _spawn(monkeypatch, _Proc(_Stream(stdout)))
    flags: list[bool] = []

    async def _probe(_device: str, *, bluray: bool) -> DiscProbe:
        flags.append(bluray)
        return probe

    monkeypatch.setattr(makemkv_mod, "probe_disc", _probe)
    return flags


async def test_binary_missing_raises_scan_error_chained(monkeypatch: pytest.MonkeyPatch) -> None:
    original = FileNotFoundError("makemkvcon")

    async def _boom(*_a: Any, **_kw: Any) -> None:
        raise original

    monkeypatch.setattr(makemkv_mod.asyncio, "create_subprocess_exec", _boom)

    with pytest.raises(ScanError) as excinfo:
        await scan_disc("/dev/sr0", 120)

    assert str(excinfo.value) == "makemkvcon binary not found on PATH"
    assert excinfo.value.__cause__ is original


async def test_idle_timeout_kills_reaps_and_reports_timed_out(monkeypatch: pytest.MonkeyPatch) -> None:
    proc = _Proc(_HangingStream())
    _spawn(monkeypatch, proc)
    monkeypatch.setattr(makemkv_mod, "SCAN_IDLE_TIMEOUT_SECONDS", 0.05)

    with pytest.raises(MakemkvScanFailed) as excinfo:
        await scan_disc("/dev/sr0", 120)

    assert excinfo.value.reason is ScanFailureReason.TIMED_OUT
    assert proc.killed is True
    assert proc.waited is True


async def test_nonzero_exit_reports_last_output_line_and_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    _spawn(monkeypatch, _Proc(_Stream(b"stdout text\n"), stderr=b"  disc read failed \n", returncode=3))

    with pytest.raises(MakemkvScanFailed) as excinfo:
        await scan_disc("/dev/sr0", 120)

    assert excinfo.value.reason is ScanFailureReason.MAKEMKV_ERROR
    assert excinfo.value.detail == "makemkvcon exited 3:   disc read failed "
    assert excinfo.value.tail == ("stdout text", "  disc read failed ")


async def test_nonzero_exit_without_output_has_empty_detail_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    _spawn(monkeypatch, _Proc(_Stream(b""), stderr=b"", returncode=1))

    with pytest.raises(MakemkvScanFailed) as excinfo:
        await scan_disc("/dev/sr0", 120)

    assert str(excinfo.value) == "makemkvcon exited 1: "
    assert excinfo.value.tail == ()


async def test_scan_command_asks_for_progress_on_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[Any, ...]] = []

    async def _factory(*args: Any, **_kw: Any) -> _Proc:
        seen.append(args)
        return _Proc(_Stream(b'CINFO:1,6206,"DVD disc"\n'))

    monkeypatch.setattr(makemkv_mod.asyncio, "create_subprocess_exec", _factory)
    monkeypatch.setattr(makemkv_mod, "probe_disc", _noop_probe)

    await scan_disc("/dev/sr0", 120)

    assert "--progress=-stdout" in seen[0]


async def _noop_probe(_device: str, *, bluray: bool) -> DiscProbe:
    return DiscProbe(crc64=None)


async def test_all_three_fingerprints_in_fixed_order(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = DiscProbe(crc64="c64", thediscdb="tdb", matrix256="m256")
    _run_ok(monkeypatch, b'CINFO:1,6206,"DVD disc"\n', probe)

    result = await scan_disc("/dev/sr0", 120)

    assert result.fingerprints == [
        DiscFingerprintInput(algo="crc64", value="c64"),
        DiscFingerprintInput(algo="thediscdb", value="tdb"),
        DiscFingerprintInput(algo="matrix256", value="m256"),
    ]


async def test_empty_fingerprints_yield_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    _run_ok(monkeypatch, b'CINFO:1,6206,"DVD disc"\n', DiscProbe(crc64="", thediscdb="", matrix256=""))

    result = await scan_disc("/dev/sr0", 120)

    assert result.fingerprints == []


async def test_only_matrix256_fingerprint(monkeypatch: pytest.MonkeyPatch) -> None:
    _run_ok(monkeypatch, b'CINFO:1,6206,"DVD disc"\n', DiscProbe(crc64=None, matrix256="m256"))

    result = await scan_disc("/dev/sr0", 120)

    assert result.fingerprints == [DiscFingerprintInput(algo="matrix256", value="m256")]


async def test_cinfo_type_wins_over_title_heuristic(monkeypatch: pytest.MonkeyPatch) -> None:
    # Titles alone would classify as Blu-ray (2h, > 4.7GB); CINFO:1 says DVD.
    stdout = b'CINFO:1,6206,"DVD disc"\nTINFO:0,9,0,"2:00:00"\nTINFO:0,11,0,"5000000000"\n'
    flags = _run_ok(monkeypatch, stdout, DiscProbe(crc64=None))

    result = await scan_disc("/dev/sr0", 120)

    assert result.disc_type == DiscType.DVD
    assert flags == [False]


async def test_missing_cinfo_falls_back_to_title_heuristic(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = b'TINFO:0,9,0,"2:00:00"\nTINFO:0,11,0,"5000000000"\n'
    flags = _run_ok(monkeypatch, stdout, DiscProbe(crc64=None))

    result = await scan_disc("/dev/sr0", 120)

    assert result.disc_type == DiscType.BLURAY
    assert flags == [True]


async def test_missing_cinfo_and_no_titles_is_unknown_and_not_bluray(monkeypatch: pytest.MonkeyPatch) -> None:
    flags = _run_ok(monkeypatch, b"", DiscProbe(crc64=None))

    result = await scan_disc("/dev/sr0", 120)

    assert result.disc_type == DiscType.UNKNOWN
    assert flags == [False]


async def test_scan_disc_does_not_read_the_playlists(monkeypatch: pytest.MonkeyPatch) -> None:
    """The structure read happens once, in the dispatcher; the MakeMKV scan only adds MakeMKV's own facts."""
    _run_ok(monkeypatch, b'CINFO:1,6206,"Blu-ray disc"\n', DiscProbe(crc64=None))

    result = await scan_disc("/dev/sr0", 120)

    assert result.playlists == [] and result.clips == []
    assert not hasattr(makemkv_mod, "scan_playlists")


async def test_scan_titles_returns_the_titles_makemkv_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = b'CINFO:1,6206,"Blu-ray disc"\nTINFO:0,9,0,"2:00:00"\nTINFO:0,16,0,"00001.mpls"\nTINFO:1,9,0,"0:05:00"\n'
    _spawn(monkeypatch, _Proc(_Stream(stdout)))

    titles = await scan_titles("/dev/sr0", 120)

    assert [(t.index, t.duration_seconds, t.source_file) for t in titles] == [
        (0, 7200, "00001.mpls"),
        (1, 300, None),
    ]


async def test_scan_titles_raises_what_a_failed_run_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _spawn(monkeypatch, _Proc(_Stream(b""), stderr=b"no key", returncode=5))

    with pytest.raises(ScanError, match="makemkvcon exited 5: no key"):
        await scan_titles("/dev/sr0", 120)


async def test_a_cancelled_run_kills_and_reaps_makemkvcon(monkeypatch: pytest.MonkeyPatch) -> None:
    proc = _Proc(_HangingStream())
    _spawn(monkeypatch, proc)

    task = asyncio.create_task(scan_titles("/dev/sr0", 120))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert proc.killed is True
    assert proc.waited is True


def test_fingerprints_all_present_in_fixed_order() -> None:
    probe = DiscProbe(crc64="c64", thediscdb="tdb", matrix256="m256")

    assert disc_fingerprints(probe) == [
        DiscFingerprintInput(algo="crc64", value="c64"),
        DiscFingerprintInput(algo="thediscdb", value="tdb"),
        DiscFingerprintInput(algo="matrix256", value="m256"),
    ]


@pytest.mark.parametrize("empty", ["", None])
def test_fingerprints_none_present_is_empty(empty: str | None) -> None:
    assert disc_fingerprints(DiscProbe(crc64=empty, thediscdb=empty, matrix256=empty)) == []


def test_fingerprints_only_thediscdb() -> None:
    probe = DiscProbe(crc64=None, thediscdb="tdb", matrix256="")

    assert disc_fingerprints(probe) == [DiscFingerprintInput(algo="thediscdb", value="tdb")]


async def test_failure_carries_cinfo_disc_type_without_sniffing(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_path: str) -> DiscType | None:
        raise AssertionError("CINFO:1 already says what the disc is")

    monkeypatch.setattr(makemkv_mod, "sniff_video_image", _boom)
    _spawn(monkeypatch, _Proc(_Stream(b'CINFO:1,6209,"Blu-ray disc"\nMSG:3303,0,1,"key unknown"\nTCOUNT:0\n')))

    with pytest.raises(MakemkvScanFailed) as excinfo:
        await scan_disc("/dev/sr0", 120)

    assert excinfo.value.disc_type is DiscType.BLURAY


async def test_failure_without_cinfo_sniffs_the_device_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def _sniff(path: str) -> DiscType | None:
        seen.append(path)
        return DiscType.BLURAY

    monkeypatch.setattr(makemkv_mod, "sniff_video_image", _sniff)
    _spawn(monkeypatch, _Proc(_Stream(b'MSG:3303,0,1,"key unknown"\nTCOUNT:0\n')))

    with pytest.raises(MakemkvScanFailed) as excinfo:
        await scan_disc("/dev/sr0", 120)

    assert excinfo.value.disc_type is DiscType.BLURAY
    assert seen == ["/dev/sr0"]


async def test_failure_with_no_cinfo_and_no_layout_has_no_disc_type(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(makemkv_mod, "sniff_video_image", lambda _p: None)
    _spawn(monkeypatch, _Proc(_Stream(b""), returncode=1))

    with pytest.raises(MakemkvScanFailed) as excinfo:
        await scan_disc("/dev/sr0", 120)

    assert excinfo.value.disc_type is None


async def test_info_run_lists_titles_down_to_the_scan_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    """The scan passes MakeMKV's 120 s minimum explicitly, the same floor the rip uses."""
    captured: list[tuple[Any, ...]] = []

    async def _factory(*args: Any, **_kw: Any) -> _Proc:
        captured.append(args)
        return _Proc(_Stream(b""))

    monkeypatch.setattr(makemkv_mod.asyncio, "create_subprocess_exec", _factory)

    await makemkv_mod._run_info("/dev/sr0", 120)

    assert "--minlength=120" in captured[0]


async def test_info_run_lists_titles_down_to_the_configured_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[Any, ...]] = []

    async def _factory(*args: Any, **_kw: Any) -> _Proc:
        captured.append(args)
        return _Proc(_Stream(b""))

    monkeypatch.setattr(makemkv_mod.asyncio, "create_subprocess_exec", _factory)

    await makemkv_mod._run_info("/dev/sr0", 60)

    assert "--minlength=60" in captured[0]


async def test_scan_records_the_minimum_it_listed_titles_with(monkeypatch: pytest.MonkeyPatch) -> None:
    _run_ok(monkeypatch, b'CINFO:1,6206,"DVD disc"\n', DiscProbe(crc64=None))
    result = await scan_disc("/dev/sr0", 45)
    assert result.min_title_length_seconds == 45
