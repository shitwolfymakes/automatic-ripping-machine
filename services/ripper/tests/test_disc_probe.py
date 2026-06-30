"""disc_probe CRC64 fingerprint tests.

The 1337server community DB is keyed on ARM v2's original-`pydvdid` CRC64
form — `format(crc, "016x")`, a plain 16-hex string with no separator. The
`pydvdid-m` fork v3 pins stringifies the same bytes as "<high8>|<low8>"
(with a pipe). `_compute_crc` must strip the pipe so the stored fingerprint
and the 1337server lookup match the DB; a piped value misses every disc on
format alone.
"""

from __future__ import annotations

import os
import sys
import types

import pytest

# arm_ripper.config builds a pydantic Settings at import time; set placeholders
# before importing any arm_ripper.* module (matches the other ripper tests).
os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend.invalid")
os.environ.setdefault("ARM_SERVICE_TOKEN", "test-token")

import arm_ripper.scan.disc_probe as disc_probe  # noqa: E402


class _PipedChecksum:
    """Mimics pydvdid-m's CRC64: __str__ → '<high8>|<low8>'."""

    def __str__(self) -> str:
        return "79df7b12|8b27d001"


def _install_fake_pydvdid(monkeypatch: pytest.MonkeyPatch, dvdid_cls: type) -> None:
    """_compute_crc does `from pydvdid_m import DvdId` lazily, so inject a fake
    module — the test never touches the real package or a disc device."""
    module = types.ModuleType("pydvdid_m")
    module.DvdId = dvdid_cls  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pydvdid_m", module)


def test_compute_crc_strips_pipe_to_v2_canonical_form(monkeypatch: pytest.MonkeyPatch) -> None:
    class _DvdId:
        def __init__(self, device_path: str) -> None:
            self.checksum = _PipedChecksum()

    _install_fake_pydvdid(monkeypatch, _DvdId)
    # pydvdid-m emits "79df7b12|8b27d001"; 1337server expects "79df7b128b27d001".
    assert disc_probe._compute_crc("/dev/sr0") == "79df7b128b27d001"


@pytest.mark.asyncio
async def test_probe_disc_returns_pipe_free_crc(monkeypatch: pytest.MonkeyPatch) -> None:
    class _DvdId:
        def __init__(self, device_path: str) -> None:
            self.checksum = _PipedChecksum()

    async def _ready(_dev: str) -> bool:
        return True

    _install_fake_pydvdid(monkeypatch, _DvdId)
    monkeypatch.setattr(disc_probe, "await_device_ready", _ready)
    probe = await disc_probe.probe_disc("/dev/sr0")
    assert probe.crc64 == "79df7b128b27d001"
    assert "|" not in probe.crc64


def test_compute_crc_none_when_checksum_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    class _DvdId:
        def __init__(self, device_path: str) -> None:
            self.checksum = None  # Blu-ray / CD: no /VIDEO_TS tree

    _install_fake_pydvdid(monkeypatch, _DvdId)
    assert disc_probe._compute_crc("/dev/sr0") is None


def test_compute_crc_none_on_pydvdid_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _DvdId:
        def __init__(self, device_path: str) -> None:
            raise RuntimeError("pycdlib read error")

    _install_fake_pydvdid(monkeypatch, _DvdId)
    assert disc_probe._compute_crc("/dev/sr0") is None


@pytest.mark.asyncio
async def test_await_device_ready_true_after_settle(monkeypatch: pytest.MonkeyPatch) -> None:
    # Device is NOT_READY for two polls, then DISC_OK — the helper must wait and proceed.
    from arm_ripper.drive_poll import DriveState

    states = iter([DriveState.NOT_READY, DriveState.NOT_READY, DriveState.DISC_OK])
    monkeypatch.setattr(disc_probe, "read_drive_status", lambda _dev: next(states))
    sleeps: list[float] = []

    async def _fake_sleep(s: float) -> None:
        sleeps.append(s)

    monkeypatch.setattr(disc_probe.asyncio, "sleep", _fake_sleep)
    assert await disc_probe.await_device_ready("/dev/sr0") is True
    assert len(sleeps) == 2  # slept after each non-terminal poll, not after the DISC_OK


@pytest.mark.asyncio
async def test_await_device_ready_iso_skips_ioctl(monkeypatch: pytest.MonkeyPatch) -> None:
    # ISO source → always ready, read_drive_status must NOT be called.
    monkeypatch.setattr(disc_probe, "is_iso_source", lambda _p: True)

    def _boom(_dev: str) -> object:
        raise AssertionError("read_drive_status must not be called for an ISO source")

    monkeypatch.setattr(disc_probe, "read_drive_status", _boom)
    assert await disc_probe.await_device_ready("iso:/img.iso") is True


@pytest.mark.asyncio
async def test_await_device_ready_false_on_no_disc(monkeypatch: pytest.MonkeyPatch) -> None:
    from arm_ripper.drive_poll import DriveState

    monkeypatch.setattr(disc_probe, "is_iso_source", lambda _p: False)
    monkeypatch.setattr(disc_probe, "read_drive_status", lambda _dev: DriveState.NO_DISC)
    assert await disc_probe.await_device_ready("/dev/sr0") is False


@pytest.mark.asyncio
async def test_await_device_ready_false_on_tray_open(monkeypatch: pytest.MonkeyPatch) -> None:
    from arm_ripper.drive_poll import DriveState

    monkeypatch.setattr(disc_probe, "is_iso_source", lambda _p: False)
    monkeypatch.setattr(disc_probe, "read_drive_status", lambda _dev: DriveState.TRAY_OPEN)
    assert await disc_probe.await_device_ready("/dev/sr0") is False


@pytest.mark.asyncio
async def test_await_device_ready_false_on_budget_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    from arm_ripper.drive_poll import DriveState

    monkeypatch.setattr(disc_probe, "is_iso_source", lambda _p: False)
    monkeypatch.setattr(disc_probe, "read_drive_status", lambda _dev: DriveState.NOT_READY)
    monkeypatch.setattr(disc_probe, "DEVICE_READY_TIMEOUT_SECONDS", 6.0)
    monkeypatch.setattr(disc_probe.settings, "POLL_INTERVAL_SECONDS", 2.0)
    sleeps: list[float] = []

    async def _fake_sleep(s: float) -> None:
        sleeps.append(s)

    monkeypatch.setattr(disc_probe.asyncio, "sleep", _fake_sleep)
    assert await disc_probe.await_device_ready("/dev/sr0") is False
    # 6.0s budget / 2.0s interval = 3 polls → 2 sleeps between them.
    assert len(sleeps) == 2


@pytest.mark.asyncio
async def test_probe_disc_skips_compute_when_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    # Device not ready → probe_disc must NOT call _compute_crc (the race can't be reached).
    async def _not_ready(_dev: str) -> bool:
        return False

    monkeypatch.setattr(disc_probe, "await_device_ready", _not_ready)

    def _boom(_dev: str) -> str | None:
        raise AssertionError("_compute_crc must not run on a not-ready device")

    monkeypatch.setattr(disc_probe, "_compute_crc", _boom)
    probe = await disc_probe.probe_disc("/dev/sr0")
    assert probe.crc64 is None


@pytest.mark.asyncio
async def test_probe_disc_computes_when_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    # Device ready → probe_disc runs _compute_crc and returns its value.
    async def _ready(_dev: str) -> bool:
        return True

    monkeypatch.setattr(disc_probe, "await_device_ready", _ready)
    monkeypatch.setattr(disc_probe, "_compute_crc", lambda _dev: "79df7b128b27d001")
    probe = await disc_probe.probe_disc("/dev/sr0")
    assert probe.crc64 == "79df7b128b27d001"


@pytest.mark.asyncio
async def test_await_device_ready_false_on_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    # read_drive_status raising OSError (e.g. ENOMEDIUM mid-resettle) must be
    # caught and treated as not-ready — never propagate. Budget then expires → False.
    monkeypatch.setattr(disc_probe, "is_iso_source", lambda _p: False)

    def _raise(_dev: str) -> object:
        raise OSError(123, "No medium found")

    monkeypatch.setattr(disc_probe, "read_drive_status", _raise)

    async def _fake_sleep(_s: float) -> None:
        pass

    monkeypatch.setattr(disc_probe.asyncio, "sleep", _fake_sleep)
    assert await disc_probe.await_device_ready("/dev/sr0") is False


@pytest.mark.asyncio
async def test_probe_disc_none_when_read_status_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # End-to-end: read_drive_status raising OSError must NOT propagate out of probe_disc.
    monkeypatch.setattr(disc_probe, "is_iso_source", lambda _p: False)

    def _raise(_dev: str) -> object:
        raise OSError(123, "No medium found")

    monkeypatch.setattr(disc_probe, "read_drive_status", _raise)

    async def _fake_sleep(_s: float) -> None:
        pass

    monkeypatch.setattr(disc_probe.asyncio, "sleep", _fake_sleep)
    probe = await disc_probe.probe_disc("/dev/sr0")
    assert probe.crc64 is None
