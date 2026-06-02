"""Tests for `scan_cd` against a faked `discid.read` C-extension.

`scan_cd` runs libdiscid in a thread (the C call is blocking). The fake
replaces the `discid` module import with a stub whose `read()` context
manager yields a disc-id + per-track tuple. Covers:

  - Happy path: real-looking disc → ScanResult with the disc id and one
    ScanTitle per audio track (index + duration_seconds).
  - Empty TOC: the bound device has no audio tracks (e.g. data disc or
    pure mixed-mode) → None.
  - libdiscid not installed (ImportError on import discid): graceful None
    return with a warning log line.
  - libdiscid raises on read() (DiscError surrogate): None, no exception
    propagates.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from arm_common import DiscType
from arm_ripper.scan.musicbrainz_disc import scan_cd


class _FakeTrack:
    def __init__(self, number: int, seconds: int) -> None:
        self.number = number
        self.seconds = seconds


class _FakeDisc:
    def __init__(self, disc_id: str, tracks: list[_FakeTrack]) -> None:
        self.id = disc_id
        self.tracks = tracks

    def __enter__(self) -> "_FakeDisc":
        return self

    def __exit__(self, *_a: Any) -> None:
        return None


def _install_fake_discid(monkeypatch, *, disc: _FakeDisc | None = None, raise_on_read: Exception | None = None) -> None:
    fake = types.ModuleType("discid")

    def fake_read(_device_path: str) -> _FakeDisc:
        if raise_on_read is not None:
            raise raise_on_read
        assert disc is not None
        return disc

    fake.read = fake_read  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "discid", fake)


@pytest.mark.asyncio
async def test_scan_cd_returns_result_with_disc_id_and_tracks(monkeypatch):
    disc = _FakeDisc(
        disc_id="lXLNQrPmEs5dXJG6XJrGm3qfWAA-",
        tracks=[_FakeTrack(1, 180), _FakeTrack(2, 240), _FakeTrack(3, 300)],
    )
    _install_fake_discid(monkeypatch, disc=disc)

    result = await scan_cd("/dev/sr0")
    assert result is not None
    assert result.disc_type == DiscType.CD
    assert result.musicbrainz_disc_id == "lXLNQrPmEs5dXJG6XJrGm3qfWAA-"
    assert [t.index for t in result.titles] == [1, 2, 3]
    assert [t.duration_seconds for t in result.titles] == [180, 240, 300]
    assert result.raw == {"track_count": 3}


@pytest.mark.asyncio
async def test_scan_cd_returns_none_when_disc_has_no_tracks(monkeypatch):
    """A disc with no audio TOC entries (e.g. a DVD slipped in by
    mistake — libdiscid sees the device but reports zero tracks). The
    scanner should reject it cleanly rather than create a CD job with
    empty tracks."""
    disc = _FakeDisc(disc_id="any", tracks=[])
    _install_fake_discid(monkeypatch, disc=disc)

    assert await scan_cd("/dev/sr0") is None


@pytest.mark.asyncio
async def test_scan_cd_returns_none_when_discid_module_missing(monkeypatch, caplog):
    """Defensive: the python-discid package isn't always installed in
    every test environment / container variant. The scanner returns
    None and logs a warning rather than crashing the rip pipeline."""
    monkeypatch.delitem(sys.modules, "discid", raising=False)

    # Force `import discid` to raise even if the real library is
    # installed in the test venv.
    import builtins

    real_import = builtins.__import__

    def deny_discid(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "discid":
            raise ImportError("simulated missing discid")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", deny_discid)

    with caplog.at_level("WARNING", logger="arm_ripper.scan.musicbrainz_disc"):
        result = await scan_cd("/dev/sr0")
    assert result is None
    assert any("python-discid not installed" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_scan_cd_returns_none_when_discid_read_raises(monkeypatch, caplog):
    """libdiscid raises (typically `DiscError` from a non-CD device, but
    the scanner catches BaseException since libdiscid's exception types
    aren't stable). Returns None, logs at INFO, no propagation."""
    _install_fake_discid(monkeypatch, raise_on_read=RuntimeError("not a CD"))

    with caplog.at_level("INFO", logger="arm_ripper.scan.musicbrainz_disc"):
        result = await scan_cd("/dev/sr0")
    assert result is None
    assert any("discid read failed" in r.getMessage() for r in caplog.records)
