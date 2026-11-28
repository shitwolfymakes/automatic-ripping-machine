"""Which scans are structure scans, the titles tracks are built from, and the key a track gets."""

from __future__ import annotations

from arm_common import DiscType
from arm_common.disc_titles import (
    MAKEMKV_MIN_TITLE_SECONDS,
    is_structure_scan,
    scan_candidates,
    track_ref,
)
from arm_common.schemas import BdClip, BdPlaylist, ScanResult, ScanTitle


def _playlist(name: str, seconds: float, **kw: object) -> BdPlaylist:
    return BdPlaylist(
        name=name,
        clips=[1],
        clip_seconds=[seconds],
        duration_seconds=round(seconds),
        chapter_count=1,
        **kw,  # type: ignore[arg-type]
    )


def _structure_scan() -> ScanResult:
    return ScanResult(
        disc_type=DiscType.BLURAY,
        playlists=[
            _playlist("00001.mpls", 7000.0),
            _playlist("00002.mpls", float(MAKEMKV_MIN_TITLE_SECONDS - 1)),
            _playlist("00334.mpls", 5000.0, angle_clips=[[2]]),
        ],
        clips=[BdClip(number=1, seconds=7000.0, size_bytes=7_000), BdClip(number=2, seconds=5000.0, size_bytes=5_000)],
    )


def test_a_blu_ray_scan_with_playlists_is_a_structure_scan() -> None:
    assert is_structure_scan(_structure_scan())


def test_a_blu_ray_scan_without_playlists_is_not() -> None:
    assert not is_structure_scan(ScanResult(disc_type=DiscType.BLURAY, titles=[ScanTitle(index=0, duration_seconds=9)]))


def test_a_dvd_scan_is_not() -> None:
    assert not is_structure_scan(ScanResult(disc_type=DiscType.DVD, playlists=[_playlist("00001.mpls", 600.0)]))


def test_candidates_of_a_structure_scan_come_from_the_playlists_above_makemkvs_minimum() -> None:
    titles = scan_candidates(_structure_scan())
    assert [(t.index, t.source_file, t.angle) for t in titles] == [
        (0, "00001.mpls", None),
        (1, "00334.mpls", 1),
        (2, "00334.mpls", 2),
    ]


def test_candidates_of_any_other_scan_are_its_titles() -> None:
    scan = ScanResult(disc_type=DiscType.DVD, titles=[ScanTitle(index=3, duration_seconds=600)])
    assert scan_candidates(scan) == scan.titles


def test_a_structure_scan_keys_a_track_by_its_title_ref() -> None:
    scan = _structure_scan()
    first, second = scan_candidates(scan)[1:]
    assert [track_ref(scan, first), track_ref(scan, second)] == ["00334.mpls:1", "00334.mpls:2"]
    assert track_ref(scan, scan_candidates(scan)[0]) == "00001.mpls"


def test_any_other_scan_keys_a_track_by_its_index() -> None:
    scan = ScanResult(disc_type=DiscType.DVD, titles=[ScanTitle(index=3, duration_seconds=600)])
    assert track_ref(scan, scan.titles[0]) == "3"
