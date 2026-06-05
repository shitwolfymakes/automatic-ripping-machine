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

    _install_fake_pydvdid(monkeypatch, _DvdId)
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
