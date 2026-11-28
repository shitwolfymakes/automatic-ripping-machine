"""The disc scan reads a Blu-ray's structure first; MakeMKV runs inline only when there is none to read."""

from __future__ import annotations

import logging

import pytest

import arm_ripper.scan.dispatcher as dispatcher_mod
from arm_common import DiscType
from arm_common.schemas import BdClip, BdDiscMeta, BdPlaylist, ScanResult, ScanTitle
from arm_ripper.scan.bd_structure import BdStructure
from arm_ripper.scan.disc_probe import DiscProbe

PLAYLIST = BdPlaylist(name="00800.mpls", clips=[1], clip_seconds=[7200.0], duration_seconds=7200, chapter_count=12)
CLIP = BdClip(number=1, seconds=7200.0, size_bytes=30_000_000_000)


class _Calls:
    def __init__(self) -> None:
        self.makemkv: list[str] = []
        self.probes: list[tuple[str, bool]] = []


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> _Calls:
    calls = _Calls()

    async def _makemkv(device: str, _min_title_length_seconds: int) -> ScanResult:
        calls.makemkv.append(device)
        return ScanResult(
            disc_type=DiscType.DVD, volume_label="MKV_LABEL", titles=[ScanTitle(index=0, duration_seconds=3600)]
        )

    async def _probe(device: str, *, bluray: bool) -> DiscProbe:
        calls.probes.append((device, bluray))
        return DiscProbe(
            crc64=None, thediscdb="tdb", matrix256="m256", bd_meta=BdDiscMeta(name="Studio Name", language="eng")
        )

    async def _data(_device: str) -> ScanResult:
        return ScanResult(disc_type=DiscType.DATA, volume_label="BLKID_LABEL")

    monkeypatch.setattr(dispatcher_mod, "scan_makemkv", _makemkv)
    monkeypatch.setattr(dispatcher_mod, "probe_disc", _probe)
    monkeypatch.setattr(dispatcher_mod, "scan_data", _data)
    return calls


def _structure(monkeypatch: pytest.MonkeyPatch, structure: BdStructure) -> list[str]:
    seen: list[str] = []

    async def _read(device: str) -> BdStructure:
        seen.append(device)
        return structure

    monkeypatch.setattr(dispatcher_mod, "scan_structure", _read)
    return seen


async def test_a_blu_ray_with_a_structure_is_scanned_without_makemkv(
    monkeypatch: pytest.MonkeyPatch, calls: _Calls
) -> None:
    seen = _structure(monkeypatch, BdStructure([PLAYLIST], [CLIP]))

    result = await dispatcher_mod.scan("/dev/sr0", 120)

    assert seen == ["/dev/sr0"]
    assert calls.makemkv == []
    assert calls.probes == [("/dev/sr0", True)]
    assert result.disc_type == DiscType.BLURAY
    assert result.titles == []
    assert result.playlists == [PLAYLIST] and result.clips == [CLIP]
    assert result.volume_label == "BLKID_LABEL"
    assert [(f.algo, f.value) for f in result.fingerprints] == [("thediscdb", "tdb"), ("matrix256", "m256")]
    assert result.bd_meta == BdDiscMeta(name="Studio Name", language="eng")


async def test_a_disc_without_a_structure_is_scanned_by_makemkv_as_before(
    monkeypatch: pytest.MonkeyPatch, calls: _Calls
) -> None:
    _structure(monkeypatch, BdStructure())

    result = await dispatcher_mod.scan("/dev/sr0", 120)

    assert calls.makemkv == ["/dev/sr0"]
    assert result.disc_type == DiscType.DVD and result.volume_label == "MKV_LABEL"
    assert result.playlists == [] and [t.index for t in result.titles] == [0]


async def test_a_blu_ray_whose_structure_read_failed_falls_back_and_says_so(
    monkeypatch: pytest.MonkeyPatch, calls: _Calls, caplog: pytest.LogCaptureFixture
) -> None:
    _structure(monkeypatch, BdStructure())

    async def _bd(device: str, _min_title_length_seconds: int) -> ScanResult:
        return ScanResult(disc_type=DiscType.BLURAY, titles=[ScanTitle(index=0, duration_seconds=7200)])

    monkeypatch.setattr(dispatcher_mod, "scan_makemkv", _bd)
    with caplog.at_level(logging.INFO, logger="arm_ripper.scan"):
        result = await dispatcher_mod.scan("/dev/sr0", 120)

    assert result.titles and result.playlists == []
    assert "structure_source=makemkv" in caplog.text
