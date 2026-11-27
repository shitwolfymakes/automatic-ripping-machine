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
from arm_common.enums import DiscType  # noqa: E402
from arm_common.schemas import BdPlaylist, DiscFingerprintInput  # noqa: E402

import arm_ripper.scan.makemkv as makemkv_mod  # noqa: E402
from arm_ripper.scan.disc_probe import DiscProbe  # noqa: E402
from arm_ripper.scan.makemkv import (
    MakemkvScanFailed,
    ScanError,
    ScanFailureReason,
    _fingerprints,
    scan_disc,
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


@pytest.fixture(autouse=True)
def _no_disc_playlists(monkeypatch: pytest.MonkeyPatch) -> None:
    """scan_disc reads playlists off the device first; keep the tests off real I/O."""

    async def _none(_device: str) -> list[BdPlaylist]:
        return []

    monkeypatch.setattr(makemkv_mod, "scan_playlists", _none)


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
        await scan_disc("/dev/sr0")

    assert str(excinfo.value) == "makemkvcon binary not found on PATH"
    assert excinfo.value.__cause__ is original


async def test_idle_timeout_kills_reaps_and_reports_timed_out(monkeypatch: pytest.MonkeyPatch) -> None:
    proc = _Proc(_HangingStream())
    _spawn(monkeypatch, proc)
    monkeypatch.setattr(makemkv_mod, "SCAN_IDLE_TIMEOUT_SECONDS", 0.05)

    with pytest.raises(MakemkvScanFailed) as excinfo:
        await scan_disc("/dev/sr0")

    assert excinfo.value.reason is ScanFailureReason.TIMED_OUT
    assert proc.killed is True
    assert proc.waited is True


async def test_nonzero_exit_reports_last_output_line_and_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    _spawn(monkeypatch, _Proc(_Stream(b"stdout text\n"), stderr=b"  disc read failed \n", returncode=3))

    with pytest.raises(MakemkvScanFailed) as excinfo:
        await scan_disc("/dev/sr0")

    assert excinfo.value.reason is ScanFailureReason.MAKEMKV_ERROR
    assert excinfo.value.detail == "makemkvcon exited 3:   disc read failed "
    assert excinfo.value.tail == ("stdout text", "  disc read failed ")


async def test_nonzero_exit_without_output_has_empty_detail_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    _spawn(monkeypatch, _Proc(_Stream(b""), stderr=b"", returncode=1))

    with pytest.raises(MakemkvScanFailed) as excinfo:
        await scan_disc("/dev/sr0")

    assert str(excinfo.value) == "makemkvcon exited 1: "
    assert excinfo.value.tail == ()


async def test_scan_command_asks_for_progress_on_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[Any, ...]] = []

    async def _factory(*args: Any, **_kw: Any) -> _Proc:
        seen.append(args)
        return _Proc(_Stream(b'CINFO:1,6206,"DVD disc"\n'))

    monkeypatch.setattr(makemkv_mod.asyncio, "create_subprocess_exec", _factory)
    monkeypatch.setattr(makemkv_mod, "probe_disc", _noop_probe)

    await scan_disc("/dev/sr0")

    assert "--progress=-stdout" in seen[0]


async def _noop_probe(_device: str, *, bluray: bool) -> DiscProbe:
    return DiscProbe(crc64=None)


async def test_all_three_fingerprints_in_fixed_order(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = DiscProbe(crc64="c64", thediscdb="tdb", matrix256="m256")
    _run_ok(monkeypatch, b'CINFO:1,6206,"DVD disc"\n', probe)

    result = await scan_disc("/dev/sr0")

    assert result.fingerprints == [
        DiscFingerprintInput(algo="crc64", value="c64"),
        DiscFingerprintInput(algo="thediscdb", value="tdb"),
        DiscFingerprintInput(algo="matrix256", value="m256"),
    ]


async def test_empty_fingerprints_yield_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    _run_ok(monkeypatch, b'CINFO:1,6206,"DVD disc"\n', DiscProbe(crc64="", thediscdb="", matrix256=""))

    result = await scan_disc("/dev/sr0")

    assert result.fingerprints == []


async def test_only_matrix256_fingerprint(monkeypatch: pytest.MonkeyPatch) -> None:
    _run_ok(monkeypatch, b'CINFO:1,6206,"DVD disc"\n', DiscProbe(crc64=None, matrix256="m256"))

    result = await scan_disc("/dev/sr0")

    assert result.fingerprints == [DiscFingerprintInput(algo="matrix256", value="m256")]


async def test_cinfo_type_wins_over_title_heuristic(monkeypatch: pytest.MonkeyPatch) -> None:
    # Titles alone would classify as Blu-ray (2h, > 4.7GB); CINFO:1 says DVD.
    stdout = b'CINFO:1,6206,"DVD disc"\nTINFO:0,9,0,"2:00:00"\nTINFO:0,11,0,"5000000000"\n'
    flags = _run_ok(monkeypatch, stdout, DiscProbe(crc64=None))

    result = await scan_disc("/dev/sr0")

    assert result.disc_type == DiscType.DVD
    assert flags == [False]


async def test_missing_cinfo_falls_back_to_title_heuristic(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = b'TINFO:0,9,0,"2:00:00"\nTINFO:0,11,0,"5000000000"\n'
    flags = _run_ok(monkeypatch, stdout, DiscProbe(crc64=None))

    result = await scan_disc("/dev/sr0")

    assert result.disc_type == DiscType.BLURAY
    assert flags == [True]


async def test_missing_cinfo_and_no_titles_is_unknown_and_not_bluray(monkeypatch: pytest.MonkeyPatch) -> None:
    flags = _run_ok(monkeypatch, b"", DiscProbe(crc64=None))

    result = await scan_disc("/dev/sr0")

    assert result.disc_type == DiscType.UNKNOWN
    assert flags == [False]


async def test_scan_carries_playlists_read_before_makemkvcon(monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []
    found = [BdPlaylist(name="00800.mpls", clips=[1, 2], clip_seconds=[5.0, 6.5], duration_seconds=12, chapter_count=3)]

    async def _playlists(device: str) -> list[BdPlaylist]:
        order.append(f"playlists:{device}")
        return found

    async def _factory(*_a: Any, **_kw: Any) -> _Proc:
        order.append("makemkvcon")
        return _Proc(_Stream(b'CINFO:1,6206,"Blu-ray disc"\n'))

    monkeypatch.setattr(makemkv_mod, "scan_playlists", _playlists)
    monkeypatch.setattr(makemkv_mod.asyncio, "create_subprocess_exec", _factory)

    async def _probe(_device: str, *, bluray: bool) -> DiscProbe:
        return DiscProbe(crc64=None)

    monkeypatch.setattr(makemkv_mod, "probe_disc", _probe)

    result = await scan_disc("/dev/sr0")

    assert result.playlists == found
    assert order == ["playlists:/dev/sr0", "makemkvcon"]


def test_fingerprints_all_present_in_fixed_order() -> None:
    probe = DiscProbe(crc64="c64", thediscdb="tdb", matrix256="m256")

    assert _fingerprints(probe) == [
        DiscFingerprintInput(algo="crc64", value="c64"),
        DiscFingerprintInput(algo="thediscdb", value="tdb"),
        DiscFingerprintInput(algo="matrix256", value="m256"),
    ]


@pytest.mark.parametrize("empty", ["", None])
def test_fingerprints_none_present_is_empty(empty: str | None) -> None:
    assert _fingerprints(DiscProbe(crc64=empty, thediscdb=empty, matrix256=empty)) == []


def test_fingerprints_only_thediscdb() -> None:
    probe = DiscProbe(crc64=None, thediscdb="tdb", matrix256="")

    assert _fingerprints(probe) == [DiscFingerprintInput(algo="thediscdb", value="tdb")]
