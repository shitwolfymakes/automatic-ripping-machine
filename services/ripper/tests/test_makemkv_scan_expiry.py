"""Regression tests for the MakeMKV binary-expired (MSG:5021) early-exit
guard in `scan_disc`.

MakeMKV beta binaries carry a hard-coded 60-day kill-switch from their
release date. When upstream is between betas, every `makemkvcon info`
emits `MSG:5021,131332,1,"application version is too old"` and either
exits instantly (`info disc:9999`) or — for an `iso:/big.iso` source —
spins for the full SCAN_TIMEOUT_SECONDS before our timeout kills it.
The guard streams stdout line-by-line so the second case becomes a
deterministic ~few-second failure with a distinct error type.

See docs/ops/makemkv.md § Failure modes.
"""

from __future__ import annotations

from typing import Any

import pytest

import arm_ripper.scan.makemkv as makemkv_mod
from arm_ripper.scan.makemkv import (
    MakemkvBinaryExpiredError,
    ScanError,
    scan_disc,
)


class _AsyncByteStream:
    """Async-iterable byte stream — drop-in for `proc.stdout` / `proc.stderr`.
    Each item is a line (bytes, newline-included)."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    def __aiter__(self) -> "_AsyncByteStream":
        return self

    async def __anext__(self) -> bytes:
        if not self._lines:
            raise StopAsyncIteration
        return self._lines.pop(0)


class _FakeProc:
    def __init__(self, stdout_lines: list[bytes], stderr_lines: list[bytes] | None = None) -> None:
        self.stdout = _AsyncByteStream(stdout_lines)
        self.stderr = _AsyncByteStream(stderr_lines or [])
        self.returncode: int | None = None
        self.killed = False
        # When kill() fires, the streamer trims any remaining lines so the
        # iterator runs to EOF promptly — mirrors what a real kill does to
        # the pipe.
        self._stdout_ref = self.stdout

    async def wait(self) -> int:
        if self.returncode is None:
            self.returncode = -9 if self.killed else 0
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        # Drain any remaining stdout so the async iterator hits EOF.
        self._stdout_ref._lines.clear()
        # Set returncode so subsequent proc.wait() doesn't hang.
        if self.returncode is None:
            self.returncode = -9


def _stub_subprocess(monkeypatch: pytest.MonkeyPatch, proc: _FakeProc) -> _FakeProc:
    async def _factory(*_a: Any, **_kw: Any) -> _FakeProc:
        return proc

    monkeypatch.setattr(makemkv_mod.asyncio, "create_subprocess_exec", _factory)
    return proc


async def _stub_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub probe_disc so scan_disc doesn't shell out to mount/loopback.
    Tests focus on the MakeMKV branch; probe is exercised elsewhere."""
    from arm_ripper.scan.disc_probe import DiscProbe

    async def _fake(_device: str) -> DiscProbe:
        return DiscProbe(disc_type=None, crc64=None)

    monkeypatch.setattr(makemkv_mod, "probe_disc", _fake)


@pytest.mark.asyncio
async def test_msg_5021_raises_binary_expired_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """When MSG:5021 appears on stdout, scan_disc raises the distinct
    `MakemkvBinaryExpiredError` subtype and kills the subprocess so the
    SCAN_TIMEOUT_SECONDS ceiling doesn't fire."""
    await _stub_probe(monkeypatch)
    proc = _stub_subprocess(
        monkeypatch,
        _FakeProc(
            stdout_lines=[
                b'MSG:1005,0,1,"MakeMKV v1.18.3 started","%1 started","..."\n',
                b'MSG:5021,131332,1,"This application version is too old.","...","..."\n',
                # These trailing lines must never be reached — the guard
                # kills the proc as soon as MSG:5021 is seen.
                b'CINFO:1,0,"DVD disc"\n',
                b'CINFO:2,0,"NEVER_REACHED"\n',
            ]
        ),
    )

    with pytest.raises(MakemkvBinaryExpiredError) as excinfo:
        await scan_disc("iso:/fake/big.iso")

    assert proc.killed is True
    # Distinct, operator-actionable message — includes MSG:5021 reference
    # and points at the docs.
    assert "MSG:5021" in str(excinfo.value)
    assert "docs/ops/makemkv.md" in str(excinfo.value)


@pytest.mark.asyncio
async def test_msg_5021_is_a_scan_error_subtype(monkeypatch: pytest.MonkeyPatch) -> None:
    """`MakemkvBinaryExpiredError` is a `ScanError`, so existing
    `except ScanError` handlers in the dispatcher still catch it
    (with the option to refine on the subtype if needed)."""
    await _stub_probe(monkeypatch)
    _stub_subprocess(
        monkeypatch,
        _FakeProc(stdout_lines=[b'MSG:5021,131332,1,"too old","...","..."\n']),
    )

    with pytest.raises(ScanError):
        await scan_disc("iso:/fake/big.iso")


@pytest.mark.asyncio
async def test_clean_scan_completes_without_expiry_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard is invisible on the happy path — a normal makemkvcon
    output yields a valid ScanResult and never raises."""
    await _stub_probe(monkeypatch)
    _stub_subprocess(
        monkeypatch,
        _FakeProc(
            stdout_lines=[
                b'MSG:1005,0,1,"MakeMKV started","%1 started","..."\n',
                b'CINFO:1,0,"DVD disc"\n',
                b'CINFO:2,0,"TEST_VOLUME"\n',
                b'TINFO:0,9,0,"1:23:45"\n',
                b'TINFO:0,27,0,"title00.mkv"\n',
            ]
        ),
    )

    result = await scan_disc("/dev/sr0")
    assert result.volume_label == "TEST_VOLUME"
    assert len(result.titles) == 1
    assert result.titles[0].duration_seconds == 1 * 3600 + 23 * 60 + 45


@pytest.mark.asyncio
async def test_msg_5021_check_is_anchored_to_line_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """The match is `line.startswith(MSG:5021,)`, not a substring search.
    A diagnostic message that *quotes* the string 'MSG:5021' inside
    another message body must NOT trigger the expiry path."""
    await _stub_probe(monkeypatch)
    _stub_subprocess(
        monkeypatch,
        _FakeProc(
            stdout_lines=[
                b'MSG:1005,0,1,"MakeMKV started","%1 started","..."\n',
                # A hypothetical diagnostic line that mentions the code
                # mid-message — must not trip the guard.
                b'MSG:3025,0,1,"see MSG:5021,131332 in the manual","...","..."\n',
                b'CINFO:1,0,"DVD disc"\n',
                b'CINFO:2,0,"OK_AFTER_REFERENCE"\n',
                b'TINFO:0,9,0,"0:30:00"\n',
            ]
        ),
    )

    result = await scan_disc("/dev/sr0")
    assert result.volume_label == "OK_AFTER_REFERENCE"
