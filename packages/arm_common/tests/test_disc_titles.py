"""titles_from_structure / title_ref / parse_title_ref on the two reference discs and synthetic shapes."""

from __future__ import annotations

import pytest
from arm_common.disc_titles import parse_title_ref, title_ref, titles_from_structure
from arm_common.schemas import BdClip, BdPlaylist

MIN_SECONDS = 120


def _playlist(name: str, clips: list[int], seconds: list[float], chapters: int = 1, **kw: object) -> BdPlaylist:
    return BdPlaylist(
        name=name,
        clips=clips,
        clip_seconds=seconds,
        duration_seconds=round(sum(seconds)),
        chapter_count=chapters,
        **kw,  # type: ignore[arg-type]
    )


def _bd3d_playlists() -> list[BdPlaylist]:
    """The 3D reference disc, genericized: a short extra, a two-angle feature, a one-chapter subset."""
    return [
        _playlist("00342.mpls", [368], [9698.98], 1, mvc_clips=[369]),
        _playlist("00102.mpls", [102], [287.0], 7),
        _playlist(
            "00334.mpls",
            [364, 368],
            [108.8, 9698.98],
            16,
            angle_clips=[[366, 368]],
            mvc_clips=[365, 367, 369],
        ),
    ]


def _bd3d_clips() -> list[BdClip]:
    return [
        BdClip(number=102, seconds=287.0, size_bytes=323_000_000),
        BdClip(number=364, seconds=108.8, size_bytes=1_000_000),
        BdClip(number=365, seconds=108.8, size_bytes=200_000, mvc=True),
        BdClip(number=366, seconds=108.8, size_bytes=900_000),
        BdClip(number=367, seconds=108.8, size_bytes=180_000, mvc=True),
        BdClip(number=368, seconds=9698.98, size_bytes=40_000_000),
        BdClip(number=369, seconds=9698.98, size_bytes=8_000_000, mvc=True),
    ]


def test_3d_disc_gives_one_title_per_playlist_and_angle_in_order() -> None:
    titles = titles_from_structure(_bd3d_playlists(), _bd3d_clips(), MIN_SECONDS)
    assert [(t.index, t.source_file, t.angle) for t in titles] == [
        (0, "00102.mpls", None),
        (1, "00334.mpls", 1),
        (2, "00334.mpls", 2),
        (3, "00342.mpls", None),
    ]
    assert [t.stereo_3d for t in titles] == [False, True, True, True]
    assert [t.chapter_count for t in titles] == [7, 16, 16, 1]
    assert [t.duration_seconds for t in titles] == [287, 9808, 9808, 9699]


def test_3d_titles_carry_the_angles_base_clips_and_sum_base_plus_dependent_sizes() -> None:
    titles = titles_from_structure(_bd3d_playlists(), _bd3d_clips(), MIN_SECONDS)
    by_ref = {title_ref(t.source_file or "", t.angle): t for t in titles}
    assert by_ref["00334.mpls:1"].segment_map == [364, 368]
    assert by_ref["00334.mpls:2"].segment_map == [366, 368]
    assert by_ref["00342.mpls"].segment_map == [368]
    assert by_ref["00334.mpls:1"].segment_count == 2
    assert by_ref["00334.mpls:1"].size_bytes == 1_000_000 + 200_000 + 40_000_000 + 8_000_000
    assert by_ref["00334.mpls:2"].size_bytes == 900_000 + 180_000 + 40_000_000 + 8_000_000
    assert by_ref["00342.mpls"].size_bytes == 40_000_000 + 8_000_000
    assert by_ref["00102.mpls"].size_bytes == 323_000_000


def test_playlists_below_the_minimum_are_dropped_and_indexes_stay_contiguous() -> None:
    playlists = [_playlist("00001.mpls", [1], [30.0]), _playlist("00002.mpls", [2], [600.0])]
    titles = titles_from_structure(playlists, [], MIN_SECONDS)
    assert [(t.index, t.source_file) for t in titles] == [(0, "00002.mpls")]


def test_2d_uhd_disc_has_no_angle_and_no_3d() -> None:
    playlists = [
        _playlist("01167.mpls", [582, 580], [7.0, 126.0], 1),
        _playlist("00801.mpls", [294], [7611.0], 36),
    ]
    clips = [BdClip(number=294, seconds=7611.0, size_bytes=62_100_000_000)]
    titles = titles_from_structure(playlists, clips, MIN_SECONDS)
    assert [(t.source_file, t.angle, t.stereo_3d) for t in titles] == [
        ("00801.mpls", None, False),
        ("01167.mpls", None, False),
    ]
    assert titles[0].size_bytes == 62_100_000_000
    assert titles[1].size_bytes is None  # 582 / 580 are unlisted


def test_partly_used_clip_scales_the_size_by_the_played_share() -> None:
    playlists = [_playlist("00010.mpls", [5], [150.0])]
    clips = [BdClip(number=5, seconds=300.0, size_bytes=1000)]
    (title,) = titles_from_structure(playlists, clips, MIN_SECONDS)
    assert title.size_bytes == 500


def test_clip_shorter_than_its_play_item_is_not_scaled_up() -> None:
    playlists = [_playlist("00010.mpls", [5], [300.0])]
    clips = [BdClip(number=5, seconds=100.0, size_bytes=1000)]
    (title,) = titles_from_structure(playlists, clips, MIN_SECONDS)
    assert title.size_bytes == 1000


def test_clip_with_no_length_counts_whole() -> None:
    playlists = [_playlist("00010.mpls", [5], [300.0])]
    clips = [BdClip(number=5, seconds=0.0, size_bytes=1000)]
    (title,) = titles_from_structure(playlists, clips, MIN_SECONDS)
    assert title.size_bytes == 1000


def test_dependent_clip_not_declared_mvc_is_not_3d() -> None:
    # An extra whose SubPath block lists a clip that CLPI does not mark as a dependent view.
    playlists = [_playlist("00020.mpls", [7], [600.0], mvc_clips=[8])]
    clips = [BdClip(number=7, seconds=600.0, size_bytes=100), BdClip(number=8, seconds=600.0, size_bytes=50)]
    (title,) = titles_from_structure(playlists, clips, MIN_SECONDS)
    assert title.stereo_3d is False
    assert title.size_bytes == 100


def test_dependent_clip_missing_from_the_clip_list_is_not_3d() -> None:
    playlists = [_playlist("00020.mpls", [7], [600.0], mvc_clips=[8])]
    (title,) = titles_from_structure(playlists, [BdClip(number=7, seconds=600.0, size_bytes=100)], MIN_SECONDS)
    assert title.stereo_3d is False


def test_3d_title_with_unsized_dependent_has_no_size() -> None:
    playlists = [_playlist("00020.mpls", [7], [600.0], mvc_clips=[8])]
    clips = [BdClip(number=7, seconds=600.0, size_bytes=100), BdClip(number=8, seconds=600.0, mvc=True)]
    (title,) = titles_from_structure(playlists, clips, MIN_SECONDS)
    assert title.stereo_3d is True
    assert title.size_bytes is None


def test_one_dependent_per_item_is_shared_by_every_angle() -> None:
    # A multi-angle item whose SubPlayItem is not multi-clip: one dependent view for both angles.
    playlist = _playlist("00030.mpls", [10], [600.0], angle_clips=[[11]], mvc_clips=[12])
    clips = [
        BdClip(number=10, seconds=600.0, size_bytes=10),
        BdClip(number=11, seconds=600.0, size_bytes=20),
        BdClip(number=12, seconds=600.0, size_bytes=5, mvc=True),
    ]
    titles = titles_from_structure([playlist], clips, MIN_SECONDS)
    assert [(t.angle, t.stereo_3d, t.size_bytes) for t in titles] == [(1, True, 15), (2, True, 25)]


def test_unpairable_dependent_list_keeps_3d_but_not_the_size() -> None:
    # Two items, one angle each, but three dependent clips: the pairing is ambiguous.
    playlist = _playlist("00040.mpls", [10, 11], [300.0, 300.0], mvc_clips=[12, 13, 14])
    clips = [BdClip(number=n, seconds=300.0, size_bytes=10, mvc=n >= 12) for n in (10, 11, 12, 13, 14)]
    (title,) = titles_from_structure([playlist], clips, MIN_SECONDS)
    assert title.stereo_3d is True
    assert title.size_bytes is None


def test_unpairable_dependent_list_without_mvc_clips_is_2d() -> None:
    playlist = _playlist("00040.mpls", [10, 11], [300.0, 300.0], mvc_clips=[12, 13, 14])
    clips = [BdClip(number=n, seconds=300.0, size_bytes=10) for n in (10, 11, 12, 13, 14)]
    (title,) = titles_from_structure([playlist], clips, MIN_SECONDS)
    assert title.stereo_3d is False
    assert title.size_bytes == 20


def test_item_with_fewer_angles_than_its_neighbour_uses_its_own_dependent_for_every_angle() -> None:
    # Item 1 has two angles (dependents 21, 23), item 2 has one (25): angle 2 plays item 2's own clip.
    playlist = _playlist("00334.mpls", [20, 24], [100.0, 200.0], angle_clips=[[22, 24]], mvc_clips=[21, 23, 25])
    clips = [BdClip(number=n, seconds=100.0 if n < 24 else 200.0, size_bytes=n, mvc=n % 2 == 1) for n in range(20, 26)]
    titles = titles_from_structure([playlist], clips, MIN_SECONDS)
    assert [t.size_bytes for t in titles] == [20 + 21 + 24 + 25, 22 + 23 + 24 + 25]


def test_title_ref_round_trip() -> None:
    assert title_ref("00334.mpls", None) == "00334.mpls"
    assert title_ref("00334.mpls", 2) == "00334.mpls:2"
    assert parse_title_ref("00334.mpls") == ("00334.mpls", None)
    assert parse_title_ref("00334.mpls:2") == ("00334.mpls", 2)


@pytest.mark.parametrize("ref", ["00334.mpls:", "00334.mpls:x", "00334.mpls:0", "00334.mpls:1:2", ""])
def test_parse_title_ref_rejects_malformed_refs(ref: str) -> None:
    with pytest.raises(ValueError, match="title ref"):
        parse_title_ref(ref)
