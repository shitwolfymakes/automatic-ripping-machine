"""The scan dispatcher hands the minimum title length to every MakeMKV scan and falls back to CD, then data."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend.invalid")
os.environ.setdefault("ARM_SERVICE_TOKEN", "test-token")

import arm_ripper.scan.dispatcher as scan_dispatcher  # noqa: E402
from arm_common import DiscType  # noqa: E402
from arm_common.schemas import ScanResult, ScanTitle  # noqa: E402
from arm_ripper.scan.makemkv import ScanError  # noqa: E402

_TITLE = ScanTitle(index=0, duration_seconds=3600)


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    makemkv: list[ScanResult | Exception],
    cd: ScanResult | None = None,
    data: ScanResult | None = None,
    extracted: Path | None = None,
) -> dict[str, list]:
    seen: dict[str, list] = {"minimums": [], "timeouts": [], "discarded": []}

    async def _makemkv(_p: str, min_title_length_seconds: int, *, timeout_seconds: float | None = None) -> ScanResult:
        seen["minimums"].append(min_title_length_seconds)
        seen["timeouts"].append(timeout_seconds)
        answer = makemkv.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def _cd(_p: str) -> ScanResult | None:
        return cd

    async def _data(_p: str) -> ScanResult:
        return data or ScanResult(disc_type=DiscType.DATA)

    async def _extract(_p: str) -> Path | None:
        return extracted

    async def _discard() -> None:
        seen["discarded"].append("all")

    monkeypatch.setattr(scan_dispatcher, "scan_makemkv", _makemkv)
    monkeypatch.setattr(scan_dispatcher, "scan_cd", _cd)
    monkeypatch.setattr(scan_dispatcher, "scan_data", _data)
    monkeypatch.setattr(scan_dispatcher.iso_extract, "extract", _extract)
    monkeypatch.setattr(scan_dispatcher.iso_extract, "discard_all", _discard)
    return seen


async def test_a_titled_makemkv_scan_gets_the_minimum_and_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    found = ScanResult(disc_type=DiscType.DVD, titles=[_TITLE])
    seen = _patch(monkeypatch, makemkv=[found])

    assert await scan_dispatcher.scan("/dev/sr0", 60) is found
    assert seen["minimums"] == [60]


async def test_the_drive_scan_timeout_reaches_makemkv(monkeypatch: pytest.MonkeyPatch) -> None:
    found = ScanResult(disc_type=DiscType.DVD, titles=[_TITLE])
    seen = _patch(monkeypatch, makemkv=[found])

    assert await scan_dispatcher.scan("/dev/sr0", 60, timeout_seconds=900) is found
    assert seen["timeouts"] == [900]


async def test_the_drive_scan_timeout_reaches_the_rescan_of_an_unpacked_image(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    iso = tmp_path / "m.iso"
    iso.write_bytes(b"\0")
    found = ScanResult(disc_type=DiscType.BLURAY, titles=[_TITLE])
    seen = _patch(monkeypatch, makemkv=[ScanError("exit -11"), found], extracted=tmp_path / "m")

    result = await scan_dispatcher.scan(str(iso), 60, timeout_seconds=900)

    assert result.titles == [_TITLE]
    assert seen["timeouts"] == [900, 900]


async def test_an_image_that_cannot_be_unpacked_falls_through_to_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    iso = tmp_path / "m.iso"
    iso.write_bytes(b"\0")
    seen = _patch(monkeypatch, makemkv=[ScanError("exit -11")], extracted=None)

    result = await scan_dispatcher.scan(str(iso), 60)

    assert result.disc_type == DiscType.DATA
    assert seen["minimums"] == [60]


async def test_a_failed_rescan_of_the_unpacked_image_drops_the_extraction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    iso = tmp_path / "m.iso"
    iso.write_bytes(b"\0")
    seen = _patch(monkeypatch, makemkv=[ScanError("exit -11"), ScanError("exit -11")], extracted=tmp_path / "m")

    result = await scan_dispatcher.scan(str(iso), 45)

    assert result.disc_type == DiscType.DATA
    assert seen["minimums"] == [45, 45]
    assert seen["discarded"] == ["all"]


async def test_an_untitled_disc_with_a_cd_toc_is_a_cd(monkeypatch: pytest.MonkeyPatch) -> None:
    cd = ScanResult(disc_type=DiscType.CD, musicbrainz_disc_id="mb", raw={"track_count": 9})
    _patch(monkeypatch, makemkv=[ScanResult(disc_type=DiscType.DVD)], cd=cd)

    assert await scan_dispatcher.scan("/dev/sr0", 120) is cd


async def test_an_untitled_disc_with_a_data_label_is_data(monkeypatch: pytest.MonkeyPatch) -> None:
    data = ScanResult(disc_type=DiscType.DATA, volume_label="BACKUP")
    _patch(monkeypatch, makemkv=[ScanResult(disc_type=DiscType.DVD)], data=data)

    assert await scan_dispatcher.scan("/dev/sr0", 120) is data


async def test_an_untitled_disc_without_a_data_label_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, makemkv=[ScanResult(disc_type=DiscType.DVD, volume_label="MKV_LABEL")])

    result = await scan_dispatcher.scan("/dev/sr0", 120)

    assert result.disc_type == DiscType.UNKNOWN
    assert result.volume_label == "MKV_LABEL"
