"""BD playlist reader: MPLS parsing from in-memory bytes (the disc read is `bd_structure`'s, tested there)."""

from __future__ import annotations

import asyncio
import logging
import struct
from pathlib import Path

import pytest
from arm_common.schemas import BdPlaylist
from bd_builders import (
    SS_SUBPATHS,
    SUBPATH_MVC,
    SUBPATH_TEXT_SUBTITLE,
    extension_data,
    mpls,
    play_item,
    ss_sub_paths,
    sub_path,
    sub_play_item,
)

from arm_ripper.scan import bd_extract
from arm_ripper.scan.bd_playlists import parse_mpls, parse_playlists, read_mpls_files

# --- parse_mpls -----------------------------------------------------------------


def test_parse_durations_clip_order_and_chapters() -> None:
    data = mpls([play_item(5, 600.0), play_item(2, 90.5, start=1000)], marks=[1, 2, 1, 1])
    playlist = parse_mpls(data, "00202.mpls")
    assert playlist == BdPlaylist(
        name="00202.mpls",
        clips=[5, 2],
        clip_seconds=[600.0, 90.5],
        duration_seconds=round(690.5),
        chapter_count=3,
    )
    assert playlist is not None
    assert playlist.angle_clips == []
    assert playlist.mvc_clips == []


def test_parse_two_angles_lists_the_second_angle_per_item() -> None:
    data = mpls([play_item(10, 100.0, extra_angles=[12]), play_item(11, 50.0)])
    playlist = parse_mpls(data, "00001.mpls")
    assert playlist is not None
    assert playlist.clips == [10, 11]
    # The item without angles plays its own clip in every angle.
    assert playlist.angle_clips == [[12, 11]]


def test_parse_three_angles_and_a_later_item_with_fewer() -> None:
    data = mpls(
        [
            play_item(10, 100.0, extra_angles=[12, 14]),
            play_item(20, 50.0, extra_angles=[22]),
            play_item(30, 10.0),
        ]
    )
    playlist = parse_mpls(data, "00001.mpls")
    assert playlist is not None
    assert playlist.clips == [10, 20, 30]
    assert playlist.angle_clips == [[12, 22, 30], [14, 20, 30]]


def test_parse_truncated_angle_table_drops_the_playlist() -> None:
    data = mpls([play_item(10, 100.0, extra_angles=[12, 14])])
    # Cut inside the last angle entry; the item's own length field now overruns the data.
    assert parse_mpls(data[: 50 + 2 + 34 + 10 + 5], "00001.mpls") is None


def _overstate_entry_count(item: bytes, count_at: int) -> bytes:
    """Same bytes and length, but the entry count claims one more entry than the structure holds."""
    patched = bytearray(item)
    patched[count_at] += 1
    return bytes(patched)


def test_parse_angle_count_beyond_the_table_is_none() -> None:
    item = _overstate_entry_count(play_item(10, 100.0, extra_angles=[12]), 2 + 32)
    assert parse_mpls(mpls([item]), "00001.mpls") is None


def test_parse_multi_clip_count_beyond_the_table_is_none() -> None:
    sub_item = _overstate_entry_count(sub_play_item(11, extra_clips=[13]), 2 + 28)
    data = mpls([play_item(10, 100.0)], sub_paths=[sub_path(SUBPATH_MVC, [sub_item])])
    assert parse_mpls(data, "00001.mpls") is None


def test_parse_non_numeric_angle_clip_is_none() -> None:
    item = bytearray(play_item(10, 100.0, extra_angles=[12]))
    item[2 + 34 : 2 + 34 + 5] = b"12\x00\x00\x00"
    assert parse_mpls(mpls([bytes(item)]), "00001.mpls") is None


def test_parse_mvc_subpath_in_the_main_list() -> None:
    data = mpls(
        [play_item(10, 100.0)],
        sub_paths=[
            sub_path(SUBPATH_MVC, [sub_play_item(11)]),
            sub_path(SUBPATH_MVC, [sub_play_item(13)]),
        ],
    )
    playlist = parse_mpls(data, "00001.mpls")
    assert playlist is not None
    assert playlist.mvc_clips == [11, 13]


def test_parse_ignores_other_subpath_types() -> None:
    data = mpls(
        [play_item(10, 100.0)],
        sub_paths=[sub_path(SUBPATH_TEXT_SUBTITLE, [sub_play_item(11)]), sub_path(SUBPATH_MVC, [sub_play_item(13)])],
    )
    playlist = parse_mpls(data, "00001.mpls")
    assert playlist is not None
    assert playlist.mvc_clips == [13]


def test_parse_mvc_subpath_in_the_extension_with_multi_clip_entries() -> None:
    # The dependent clips of angle 1 and 2 share one multi-clip SubPlayItem, the next item has one.
    ss = ss_sub_paths([sub_path(SUBPATH_MVC, [sub_play_item(11, extra_clips=[13]), sub_play_item(21)])])
    data = mpls(
        [play_item(10, 100.0, extra_angles=[12]), play_item(20, 50.0)],
        extension=extension_data({(2, 1): b"\x00" * 8, SS_SUBPATHS: ss}),
    )
    playlist = parse_mpls(data, "00001.mpls")
    assert playlist is not None
    assert playlist.mvc_clips == [11, 13, 21]
    assert playlist.angle_clips == [[12, 20]]


def test_parse_extension_ignores_non_mvc_subpaths_and_other_blocks() -> None:
    ss = ss_sub_paths([sub_path(SUBPATH_TEXT_SUBTITLE, [sub_play_item(11)])])
    data = mpls([play_item(10, 100.0)], extension=extension_data({SS_SUBPATHS: ss}))
    playlist = parse_mpls(data, "00001.mpls")
    assert playlist is not None
    assert playlist.mvc_clips == []


def test_parse_extension_without_the_ss_block_is_2d() -> None:
    data = mpls([play_item(10, 100.0)], extension=extension_data({(1, 1): b"\x00" * 8}))
    playlist = parse_mpls(data, "00001.mpls")
    assert playlist is not None
    assert playlist.mvc_clips == []


def test_parse_truncated_extension_drops_the_playlist() -> None:
    ss = ss_sub_paths([sub_path(SUBPATH_MVC, [sub_play_item(11)])])
    data = mpls([play_item(10, 100.0)], extension=extension_data({SS_SUBPATHS: ss}))
    assert parse_mpls(data[:-10], "00001.mpls") is None


def test_parse_reversed_times_count_as_zero() -> None:
    item = bytearray(play_item(1, 10.0))
    item[14:22] = struct.pack(">II", 900, 100)
    playlist = parse_mpls(mpls([bytes(item)]), "00001.mpls")
    assert playlist is not None
    assert playlist.clip_seconds == [0.0]


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"NOPE" + b"\x00" * 60,
        mpls([play_item(1, 1.0)])[:30],  # cut inside the header offsets' target
        mpls([play_item(1, 1.0)])[:60],  # cut inside the PlayItem
        mpls([play_item(1, 1.0)], marks=[1])[:-13],  # cut inside the marks
        mpls([]),  # no PlayItems
    ],
)
def test_parse_garbage_or_truncated_is_none(data: bytes) -> None:
    assert parse_mpls(data, "00001.mpls") is None


def test_parse_non_numeric_clip_name_is_none() -> None:
    item = bytearray(play_item(1, 1.0))
    item[2:7] = b"ABCDE"
    assert parse_mpls(mpls([bytes(item)]), "00001.mpls") is None


def test_parse_non_ascii_clip_name_is_none() -> None:
    item = bytearray(play_item(1, 1.0))
    item[2] = 0xFF
    assert parse_mpls(mpls([bytes(item)]), "00001.mpls") is None


# --- fixtures modelled on the two reference discs --------------------------------


def _bd3d_angle_playlist() -> bytes:
    """Two PlayItems; the first has two angles. Dependent views live in the extension SubPath:
    a multi-clip entry (one per angle) for the first item, a single clip for the second."""
    ss = ss_sub_paths([sub_path(SUBPATH_MVC, [sub_play_item(21, extra_clips=[23]), sub_play_item(25)])])
    return mpls(
        [play_item(20, 108.8, extra_angles=[22]), play_item(24, 9698.98, start=524280)],
        marks=[1] * 16,
        extension=extension_data({(2, 1): b"\x00" * 8, SS_SUBPATHS: ss}),
    )


def _bd3d_subset_playlist() -> bytes:
    ss = ss_sub_paths([sub_path(SUBPATH_MVC, [sub_play_item(25)])])
    return mpls([play_item(24, 9698.98)], marks=[1], extension=extension_data({SS_SUBPATHS: ss}))


def test_3d_disc_playlist_with_angles() -> None:
    playlist = parse_mpls(_bd3d_angle_playlist(), "00334.mpls")
    assert playlist is not None
    assert playlist.clips == [20, 24]
    assert playlist.angle_clips == [[22, 24]]
    assert playlist.mvc_clips == [21, 23, 25]
    assert playlist.chapter_count == 16
    assert playlist.duration_seconds == round(108.8 + 9698.98)


def test_3d_disc_subset_playlist_is_3d_without_angles() -> None:
    playlist = parse_mpls(_bd3d_subset_playlist(), "00342.mpls")
    assert playlist is not None
    assert (playlist.clips, playlist.angle_clips, playlist.mvc_clips) == ([24], [], [25])
    assert playlist.chapter_count == 1


def test_2d_uhd_playlist_has_no_angles_and_no_dependent_view() -> None:
    playlist = parse_mpls(mpls([play_item(294, 7200.0)], marks=[1, 1, 1]), "00801.mpls")
    assert playlist == BdPlaylist(
        name="00801.mpls", clips=[294], clip_seconds=[7200.0], duration_seconds=7200, chapter_count=3
    )


# --- reading and ordering ---------------------------------------------------------------


def test_read_mpls_files_missing_directory(tmp_path: Path) -> None:
    assert read_mpls_files(tmp_path / "nope") == {}


def test_parse_playlists_orders_by_name_and_drops_garbage() -> None:
    files = {"00002.mpls": mpls([play_item(1, 1.0)]), "00001.mpls": mpls([play_item(1, 1.0)]), "00003.mpls": b""}
    assert [p.name for p in parse_playlists(files)] == ["00001.mpls", "00002.mpls"]


class _WedgedProc:
    """A child that ignores SIGKILL (drive I/O wedge): wait() never completes."""

    pid = 4242
    returncode: int | None = None

    def __init__(self) -> None:
        self.killed = False

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        await asyncio.sleep(60)
        return -9


async def test_reap_gives_up_on_a_wedged_child_instead_of_hanging(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(bd_extract, "REAP_TIMEOUT_SECONDS", 0.05)
    proc = _WedgedProc()
    with caplog.at_level(logging.ERROR, logger="arm_ripper.scan.bd_extract"):
        await bd_extract._reap(proc)  # type: ignore[arg-type]
    assert proc.killed
    assert any("did not exit" in r.getMessage() for r in caplog.records)


async def test_reap_leaves_a_finished_child_alone() -> None:
    proc = _WedgedProc()
    proc.returncode = 0
    await bd_extract._reap(proc)  # type: ignore[arg-type]
    assert not proc.killed
