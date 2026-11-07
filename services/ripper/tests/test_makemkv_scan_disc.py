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
from arm_common.schemas import DiscFingerprintInput  # noqa: E402

import arm_ripper.scan.makemkv as makemkv_mod  # noqa: E402
from arm_ripper.scan.disc_probe import DiscProbe  # noqa: E402
from arm_ripper.scan.makemkv import (
    MakemkvBinaryExpiredError,
    ScanError,
    _fingerprints,
    _InfoRun,
    _raise_for_failure,
    _read_info_stderr,
    _read_info_stdout,
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


async def test_timeout_kills_reaps_and_suppresses_cause(monkeypatch: pytest.MonkeyPatch) -> None:
    proc = _Proc(_HangingStream())
    _spawn(monkeypatch, proc)
    monkeypatch.setattr(makemkv_mod, "SCAN_TIMEOUT_SECONDS", 0.05)

    with pytest.raises(ScanError) as excinfo:
        await scan_disc("/dev/sr0")

    assert str(excinfo.value) == "makemkvcon timed out after 0.05s"
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True
    assert proc.killed is True
    assert proc.waited is True


async def test_nonzero_exit_reports_stripped_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    _spawn(monkeypatch, _Proc(_Stream(b"stdout text\n"), stderr=b"  disc read failed \n", returncode=3))

    with pytest.raises(ScanError) as excinfo:
        await scan_disc("/dev/sr0")

    assert str(excinfo.value) == "makemkvcon exited 3: disc read failed"


async def test_nonzero_exit_with_empty_stderr_uses_first_200_stdout_chars(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = b"a" * 200 + b"b" * 50
    _spawn(monkeypatch, _Proc(_Stream(stdout), stderr=b"", returncode=1))

    with pytest.raises(ScanError) as excinfo:
        await scan_disc("/dev/sr0")

    assert str(excinfo.value) == "makemkvcon exited 1: " + "a" * 200


async def test_nonzero_exit_with_whitespace_stderr_falls_back_to_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    _spawn(monkeypatch, _Proc(_Stream(b"  out line\n"), stderr=b" \n\t", returncode=2))

    with pytest.raises(ScanError) as excinfo:
        await scan_disc("/dev/sr0")

    assert str(excinfo.value) == "makemkvcon exited 2:   out line\n"


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


def test_raise_for_failure_expired_wins_over_nonzero_exit() -> None:
    run = _InfoRun(stdout=b"out", stderr=b"err", expired=True, returncode=1)

    with pytest.raises(MakemkvBinaryExpiredError):
        _raise_for_failure(run)


def test_raise_for_failure_returns_none_on_clean_exit() -> None:
    assert _raise_for_failure(_InfoRun(stdout=b"out", stderr=b"", expired=False, returncode=0)) is None


def test_raise_for_failure_nonzero_exit_reports_stripped_stderr() -> None:
    run = _InfoRun(stdout=b"out", stderr=b"  boom \n", expired=False, returncode=3)

    with pytest.raises(ScanError) as excinfo:
        _raise_for_failure(run)

    assert str(excinfo.value) == "makemkvcon exited 3: boom"


def test_raise_for_failure_nonzero_exit_without_stderr_reports_first_200_stdout_chars() -> None:
    run = _InfoRun(stdout=b"x" * 250, stderr=b"", expired=False, returncode=2)

    with pytest.raises(ScanError) as excinfo:
        _raise_for_failure(run)

    assert str(excinfo.value) == "makemkvcon exited 2: " + "x" * 200


class _KillCountingProc(_Proc):
    def __init__(self, stdout: Any, stderr: bytes = b"") -> None:
        super().__init__(stdout, stderr)
        self.kills = 0

    def kill(self) -> None:
        self.kills += 1
        super().kill()


async def test_read_info_stdout_without_expiry_joins_lines_and_does_not_kill() -> None:
    proc = _KillCountingProc(_Stream(b"line one\nline two\n"))

    stdout, expired = await _read_info_stdout(proc)  # type: ignore[arg-type]

    assert (stdout, expired, proc.kills) == (b"line one\nline two\n", False, 0)


async def test_read_info_stdout_kills_once_on_expiry_and_keeps_draining() -> None:
    data = b"MSG:5021,a\nMSG:5021,b\nlater line\n"
    proc = _KillCountingProc(_Stream(data))

    stdout, expired = await _read_info_stdout(proc)  # type: ignore[arg-type]

    assert (stdout, expired, proc.kills) == (data, True, 1)


async def test_read_info_stderr_returns_joined_bytes() -> None:
    proc = _KillCountingProc(_Stream(b""), stderr=b"err one\nerr two\n")

    assert await _read_info_stderr(proc) == b"err one\nerr two\n"  # type: ignore[arg-type]
