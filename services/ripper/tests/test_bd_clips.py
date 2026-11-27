"""CLPI decoding (length, MVC dependent-view marker) and the clip list joined with the STREAM sizes."""

from __future__ import annotations

from pathlib import Path

import pytest
from arm_common.schemas import BdClip
from bd_builders import CODING_AVC, CODING_MVC, clpi

from arm_ripper.scan.bd_clips import build_clips, folder_stream_sizes, parse_clpi, read_clpi_files

# --- parse_clpi -------------------------------------------------------------------


def test_duration_sums_every_stc_sequence() -> None:
    assert parse_clpi(clpi([60.0, 48.8])) == (pytest.approx(108.8), False)


def test_2d_clip_is_not_mvc() -> None:
    assert parse_clpi(clpi([10.0], [CODING_AVC, 0x81, 0x90])) == (10.0, False)


def test_dependent_view_clip_is_mvc_through_program_info_ss() -> None:
    # The dependent clip's own ProgramInfo has no video; the MVC stream is in the SS extension.
    assert parse_clpi(clpi([108.8], [], ss_coding_types=[CODING_MVC])) == (pytest.approx(108.8), True)


def test_mvc_stream_in_the_main_program_info_counts() -> None:
    assert parse_clpi(clpi([5.0], [CODING_MVC])) == (5.0, True)


def test_base_view_clip_of_a_3d_disc_is_not_mvc() -> None:
    # Its ProgramInfo_SS names the pair's MVC stream, but it has base video of its own.
    assert parse_clpi(clpi([108.8], [CODING_AVC], ss_coding_types=[CODING_MVC])) == (pytest.approx(108.8), False)


def test_clip_with_both_views_in_one_stream_is_not_a_dependent_clip() -> None:
    assert parse_clpi(clpi([5.0], [CODING_AVC, CODING_MVC])) == (5.0, False)


def test_base_view_clip_without_a_program_info_ss_is_not_mvc() -> None:
    assert parse_clpi(clpi([108.8], [CODING_AVC], ss_coding_types=[])) == (pytest.approx(108.8), False)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"HDMV",
        b"NOPE0200" + b"\x00" * 64,
        clpi([10.0])[:45],  # cut inside the SequenceInfo
        clpi([10.0])[:-3],  # cut inside the ProgramInfo
        clpi([10.0], ss_coding_types=[CODING_MVC])[:-4],  # cut inside the extension block
    ],
)
def test_garbage_or_truncated_is_none(data: bytes) -> None:
    assert parse_clpi(data) is None


# --- build_clips ------------------------------------------------------------------


def test_build_clips_joins_sizes_and_orders_by_number() -> None:
    clips = build_clips(
        {
            "00021.clpi": clpi([108.8], [], ss_coding_types=[CODING_MVC]),
            "00020.clpi": clpi([108.8]),
            "00024.clpi": clpi([9698.98]),
        },
        {"00020.m2ts": 333_404_160, "00021.m2ts": 300_000_000, "00099.m2ts": 1},
    )
    assert [(c.number, c.size_bytes, c.mvc) for c in clips] == [
        (20, 333_404_160, False),
        (21, 300_000_000, True),
        (24, None, False),
    ]
    assert [c.seconds for c in clips] == pytest.approx([108.8, 108.8, 9698.98])


def test_build_clips_skips_unparsable_files() -> None:
    assert build_clips({"00001.clpi": b"garbage", "00002.clpi": clpi([1.0])}, {}) == [
        BdClip(number=2, seconds=1.0, size_bytes=None, mvc=False)
    ]


def test_build_clips_with_nothing_is_empty() -> None:
    assert build_clips({}, {"00001.m2ts": 5}) == []


# --- folder reads -------------------------------------------------------------------


def test_read_clpi_files_filters_by_name(tmp_path: Path) -> None:
    (tmp_path / "00001.CLPI").write_bytes(b"a")
    (tmp_path / "00002.clpi").write_bytes(b"b")
    (tmp_path / "notes.txt").write_bytes(b"c")
    assert read_clpi_files(tmp_path) == {"00001.clpi": b"a", "00002.clpi": b"b"}


def test_read_clpi_files_missing_directory(tmp_path: Path) -> None:
    assert read_clpi_files(tmp_path / "nope") == {}


def test_folder_stream_sizes(tmp_path: Path) -> None:
    (tmp_path / "00001.M2TS").write_bytes(b"x" * 7)
    (tmp_path / "SSIF").mkdir()
    (tmp_path / "readme.txt").write_bytes(b"x")
    assert folder_stream_sizes(tmp_path) == {"00001.m2ts": 7}


def test_folder_stream_sizes_missing_directory(tmp_path: Path) -> None:
    assert folder_stream_sizes(tmp_path / "nope") == {}
