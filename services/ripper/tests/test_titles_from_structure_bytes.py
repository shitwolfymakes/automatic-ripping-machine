"""The structure-to-title path end to end on synthetic bytes shaped like the 3D reference disc:
MPLS and CLPI built with the byte builders, parsed by the ripper readers, turned into titles by
arm_common, and mapped to MakeMKV's numbering."""

from __future__ import annotations

from arm_common.disc_titles import titles_from_structure
from arm_common.schemas import BdPlaylist
from arm_common.title_map import map_titles
from bd_builders import (
    CODING_MVC,
    SS_SUBPATHS,
    SUBPATH_MVC,
    clpi,
    extension_data,
    mpls,
    play_item,
    ss_sub_paths,
    sub_path,
    sub_play_item,
)

from arm_ripper.scan.bd_clips import build_clips, parse_clpi
from arm_ripper.scan.bd_playlists import parse_playlists
from arm_ripper.scan.makemkv_info import parse_makemkvcon_info


def _playlists() -> list[BdPlaylist]:
    angles = ss_sub_paths([sub_path(SUBPATH_MVC, [sub_play_item(365, extra_clips=[367]), sub_play_item(369)])])
    subset = ss_sub_paths([sub_path(SUBPATH_MVC, [sub_play_item(369)])])
    files = {
        "00102.mpls": mpls([play_item(102, 287.0)], marks=[1] * 7),
        "00334.mpls": mpls(
            [play_item(364, 108.8, extra_angles=[366]), play_item(368, 9698.98, start=524280)],
            marks=[1] * 16,
            extension=extension_data({SS_SUBPATHS: angles}),
        ),
        "00342.mpls": mpls([play_item(368, 9698.98)], marks=[1], extension=extension_data({SS_SUBPATHS: subset})),
    }
    return parse_playlists({name: data for name, data in files.items()})


def _clips() -> list:
    seconds = {102: 287.0, 364: 108.8, 366: 108.8, 368: 9698.98, 365: 108.8, 367: 108.8, 369: 9698.98}
    info = {}
    for number, length in seconds.items():
        dependent = number in (365, 367, 369)
        data = clpi([length], [] if dependent else [0x1B], ss_coding_types=[CODING_MVC] if dependent else None)
        assert parse_clpi(data) is not None
        info[f"{number:05d}.clpi"] = data
    return build_clips(info, {f"{n:05d}.m2ts": 1000 * n for n in seconds})


MAKEMKV_INFO = [
    'TINFO:0,9,0,"0:04:47"',
    'TINFO:0,16,0,"00102.mpls"',
    'TINFO:1,9,0,"2:43:27"',
    'TINFO:1,15,0,"1"',
    'TINFO:1,16,0,"00334.mpls"',
    'TINFO:2,9,0,"2:43:27"',
    'TINFO:2,15,0,"2"',
    'TINFO:2,16,0,"00334.mpls"',
    'TINFO:3,9,0,"2:41:38"',
    'TINFO:3,16,0,"00342.mpls"',
]


def test_blade_runner_shaped_disc_maps_to_makemkv_numbers() -> None:
    titles = titles_from_structure(_playlists(), _clips(), 120)
    assert [(t.source_file, t.angle, t.stereo_3d) for t in titles] == [
        ("00102.mpls", None, False),
        ("00334.mpls", 1, True),
        ("00334.mpls", 2, True),
        ("00342.mpls", None, True),
    ]
    assert titles[1].size_bytes == 364 * 1000 + 365 * 1000 + 368 * 1000 + 369 * 1000
    assert titles[2].size_bytes == 366 * 1000 + 367 * 1000 + 368 * 1000 + 369 * 1000
    _, makemkv_titles, _ = parse_makemkvcon_info(MAKEMKV_INFO)
    result = map_titles(titles, makemkv_titles)
    assert result.numbers == {"00102.mpls": 0, "00334.mpls:1": 1, "00334.mpls:2": 2, "00342.mpls": 3}
    assert (result.makemkv_only, result.unexposed) == ([], [])


UHD_INFO = [
    'TINFO:0,9,0,"2:06:51"',
    'TINFO:0,16,0,"00801.mpls"',
    'TINFO:1,9,0,"0:02:13"',
    'TINFO:1,16,0,"01167.mpls"',
    'TINFO:2,9,0,"2:06:51"',
    'TINFO:2,16,0,"00294.m2ts"',
    'TINFO:3,9,0,"0:02:06"',
    'TINFO:3,16,0,"00580.m2ts"',
]


def test_uhd_shaped_disc_leaves_the_raw_stream_titles_makemkv_only() -> None:
    files = {
        "00801.mpls": mpls([play_item(294, 7611.0)], marks=[1] * 36),
        "01167.mpls": mpls([play_item(582, 7.0), play_item(580, 126.0)], marks=[1]),
    }
    titles = titles_from_structure(parse_playlists(files), [], 120)
    assert [(t.source_file, t.duration_seconds, t.angle, t.stereo_3d) for t in titles] == [
        ("00801.mpls", 7611, None, False),
        ("01167.mpls", 133, None, False),
    ]
    _, makemkv_titles, _ = parse_makemkvcon_info(UHD_INFO)
    result = map_titles(titles, makemkv_titles)
    assert result.numbers == {"00801.mpls": 0, "01167.mpls": 1}
    assert (result.makemkv_only, result.unexposed) == ([2, 3], [])
