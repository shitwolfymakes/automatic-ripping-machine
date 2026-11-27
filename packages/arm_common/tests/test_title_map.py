"""map_titles: structure titles <-> MakeMKV title numbers on the two reference discs."""

from __future__ import annotations

from arm_common.schemas import ScanTitle
from arm_common.title_map import TitleMap, map_titles


def _t(index: int, source: str, seconds: int, angle: int | None = None) -> ScanTitle:
    return ScanTitle(index=index, duration_seconds=seconds, source_file=source, angle=angle)


def test_3d_disc_maps_each_playlist_and_angle() -> None:
    ours = [
        _t(0, "00102.mpls", 287),
        _t(1, "00334.mpls", 9808, 1),
        _t(2, "00334.mpls", 9808, 2),
        _t(3, "00342.mpls", 9699),
    ]
    makemkv = [
        _t(0, "00102.mpls", 287),
        _t(1, "00334.mpls", 9807, 1),
        _t(2, "00334.mpls", 9807, 2),
        _t(3, "00342.mpls", 9698),
    ]
    assert map_titles(ours, makemkv) == TitleMap(
        numbers={"00102.mpls": 0, "00334.mpls:1": 1, "00334.mpls:2": 2, "00342.mpls": 3},
        makemkv_only=[],
        unexposed=[],
    )


def test_uhd_raw_stream_titles_are_makemkv_only() -> None:
    ours = [_t(0, "00801.mpls", 7611), _t(1, "01167.mpls", 133)]
    makemkv = [
        _t(0, "00801.mpls", 7611),
        _t(1, "01167.mpls", 133),
        _t(2, "00294.m2ts", 7611),
        _t(3, "00580.m2ts", 126),
    ]
    result = map_titles(ours, makemkv)
    assert result.numbers == {"00801.mpls": 0, "01167.mpls": 1}
    assert result.makemkv_only == [2, 3]
    assert result.unexposed == []


def test_makemkv_title_without_an_angle_maps_to_angle_1() -> None:
    ours = [_t(0, "00334.mpls", 600, 1), _t(1, "00334.mpls", 600, 2)]
    makemkv = [_t(5, "00334.mpls", 600), _t(6, "00334.mpls", 600, 2)]
    assert map_titles(ours, makemkv).numbers == {"00334.mpls:1": 5, "00334.mpls:2": 6}


def test_single_angle_ref_matches_a_makemkv_title_that_reports_angle_1() -> None:
    assert map_titles([_t(0, "00001.mpls", 600)], [_t(4, "00001.mpls", 600, 1)]).numbers == {"00001.mpls": 4}


def test_ref_makemkv_does_not_expose_is_reported() -> None:
    ours = [_t(0, "00001.mpls", 600), _t(1, "00002.mpls", 700)]
    result = map_titles(ours, [_t(0, "00001.mpls", 600)])
    assert result.numbers == {"00001.mpls": 0}
    assert result.unexposed == ["00002.mpls"]
    assert result.makemkv_only == []


def test_duration_disagreement_beyond_two_seconds_does_not_map() -> None:
    ours = [_t(0, "00001.mpls", 600)]
    result = map_titles(ours, [_t(3, "00001.mpls", 603)])
    assert result.numbers == {}
    assert result.makemkv_only == [3]
    assert result.unexposed == ["00001.mpls"]


def test_duration_within_two_seconds_maps() -> None:
    assert map_titles([_t(0, "00001.mpls", 600)], [_t(3, "00001.mpls", 602)]).numbers == {"00001.mpls": 3}


def test_source_name_case_is_ignored() -> None:
    assert map_titles([_t(0, "00001.mpls", 600)], [_t(2, "00001.MPLS", 600)]).numbers == {"00001.mpls": 2}


def test_makemkv_title_without_a_source_is_makemkv_only() -> None:
    result = map_titles([_t(0, "00001.mpls", 600)], [ScanTitle(index=7, duration_seconds=600)])
    assert result.makemkv_only == [7]
    assert result.unexposed == ["00001.mpls"]


def test_our_title_without_a_source_is_ignored() -> None:
    assert map_titles([ScanTitle(index=0, duration_seconds=600)], []) == TitleMap({}, [], [])


def test_a_second_makemkv_title_for_the_same_ref_is_makemkv_only() -> None:
    result = map_titles([_t(0, "00001.mpls", 600)], [_t(1, "00001.mpls", 600), _t(2, "00001.mpls", 600)])
    assert result.numbers == {"00001.mpls": 1}
    assert result.makemkv_only == [2]
