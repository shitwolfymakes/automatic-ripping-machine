"""Scan dispatcher: which scan outcomes may fall back to blkid / the data-copy rip, and which stop."""

from __future__ import annotations

import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend.invalid")
os.environ.setdefault("ARM_SERVICE_TOKEN", "test-token")

import pytest  # noqa: E402
from arm_common import DiscType  # noqa: E402
from arm_common.schemas import ScanResult, ScanTitle  # noqa: E402

import arm_ripper.scan.dispatcher as dispatcher  # noqa: E402
from arm_ripper.scan.makemkv import MakemkvScanFailed, ScanError, ScanFailureReason  # noqa: E402

_KEY_UNKNOWN = MakemkvScanFailed(
    ScanFailureReason.VOLUME_KEY_UNKNOWN, "volume key unknown", ("MSG:3303,key",), DiscType.BLURAY
)
_TITLES = [ScanTitle(index=0, duration_seconds=3600)]


class _Calls:
    """Records which fallbacks ran and answers each from the test's arrangement."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        makemkv: ScanResult | Exception,
        cd: ScanResult | None = None,
        data: ScanResult | None = None,
    ) -> None:
        self.cd_calls = 0
        self.data_calls = 0

        async def _makemkv(_p: str) -> ScanResult:
            if isinstance(makemkv, Exception):
                raise makemkv
            return makemkv

        async def _cd(_p: str) -> ScanResult | None:
            self.cd_calls += 1
            return cd

        async def _data(_p: str) -> ScanResult:
            self.data_calls += 1
            assert data is not None, "blkid / data fallback must not run"
            return data

        monkeypatch.setattr(dispatcher, "scan_makemkv", _makemkv)
        monkeypatch.setattr(dispatcher, "scan_cd", _cd)
        monkeypatch.setattr(dispatcher, "scan_data", _data)


async def test_undecryptable_disc_is_not_a_data_disc(monkeypatch: pytest.MonkeyPatch) -> None:
    """The #700 sequence: makemkvcon fails with the volume key unknown, blkid would read a UDF label."""
    calls = _Calls(monkeypatch, makemkv=_KEY_UNKNOWN, data=ScanResult(disc_type=DiscType.DATA, volume_label="UDF"))

    with pytest.raises(MakemkvScanFailed) as excinfo:
        await dispatcher.scan("/dev/sr0")

    assert excinfo.value is _KEY_UNKNOWN
    assert calls.cd_calls == 1
    assert calls.data_calls == 0


async def test_makemkv_failure_still_tries_cd_and_returns_it(monkeypatch: pytest.MonkeyPatch) -> None:
    cd = ScanResult(disc_type=DiscType.CD, musicbrainz_disc_id="abc")
    calls = _Calls(monkeypatch, makemkv=_KEY_UNKNOWN, cd=cd)

    result = await dispatcher.scan("/dev/sr0")

    assert result is cd
    assert calls.data_calls == 0


async def test_titles_return_without_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    found = ScanResult(disc_type=DiscType.DVD, volume_label="MOVIE", titles=_TITLES)
    calls = _Calls(monkeypatch, makemkv=found)

    assert await dispatcher.scan("/dev/sr0") is found
    assert (calls.cd_calls, calls.data_calls) == (0, 0)


async def test_makemkv_ran_with_no_titles_and_a_label_is_data(monkeypatch: pytest.MonkeyPatch) -> None:
    data = ScanResult(disc_type=DiscType.DATA, volume_label="BACKUP")
    _Calls(monkeypatch, makemkv=ScanResult(disc_type=DiscType.UNKNOWN), data=data)

    assert await dispatcher.scan("/dev/sr0") is data


async def test_makemkv_ran_with_no_titles_and_no_label_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    _Calls(
        monkeypatch,
        makemkv=ScanResult(disc_type=DiscType.UNKNOWN, volume_label="MKV_LABEL"),
        data=ScanResult(disc_type=DiscType.UNKNOWN),
    )

    result = await dispatcher.scan("/dev/sr0")

    assert result.disc_type is DiscType.UNKNOWN
    assert result.volume_label == "MKV_LABEL"


async def test_makemkv_that_cannot_run_still_falls_back_to_data(monkeypatch: pytest.MonkeyPatch) -> None:
    data = ScanResult(disc_type=DiscType.DATA, volume_label="BACKUP")
    _Calls(monkeypatch, makemkv=ScanError("makemkvcon binary not found on PATH"), data=data)

    assert await dispatcher.scan("/dev/sr0") is data
