"""Whole-disc structure read: playlists and clips from a disc folder and through a fake 7-Zip, modelled on the reference discs."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from arm_common.schemas import BdClip
from bd_builders import (
    CODING_AVC,
    CODING_MVC,
    SS_SUBPATHS,
    SUBPATH_MVC,
    clpi,
    extension_data,
    fake_7zz,
    mpls,
    play_item,
    ss_sub_paths,
    sub_path,
    sub_play_item,
)

from arm_ripper.scan import bd_structure
from arm_ripper.scan.bd_structure import BdStructure, scan_structure


def _write(root: Path, relative: str, data: bytes) -> None:
    target = root / "BDMV" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def _stream(root: Path, number: int, size: int) -> None:
    _write(root, f"STREAM/{number:05d}.m2ts", b"\x00" * size)


def _bd3d_folder(folder: Path) -> None:
    """Angle 1 = clips 20/24, angle 2 = 22/24, dependent views 21, 23, 25; a 3D subset playlist; a 2D extra."""
    ss = ss_sub_paths([sub_path(SUBPATH_MVC, [sub_play_item(21, extra_clips=[23]), sub_play_item(25)])])
    _write(
        folder,
        "PLAYLIST/00334.mpls",
        mpls(
            [play_item(20, 108.8, extra_angles=[22]), play_item(24, 600.0)],
            marks=[1] * 16,
            extension=extension_data({SS_SUBPATHS: ss}),
        ),
    )
    ss_subset = ss_sub_paths([sub_path(SUBPATH_MVC, [sub_play_item(25)])])
    _write(
        folder,
        "PLAYLIST/00342.mpls",
        mpls([play_item(24, 600.0)], marks=[1], extension=extension_data({SS_SUBPATHS: ss_subset})),
    )
    _write(folder, "PLAYLIST/00102.mpls", mpls([play_item(1, 287.0)]))
    for number in (20, 22, 24, 1):
        # A base clip of a 3D disc: own video, plus a ProgramInfo_SS naming its pair's MVC stream.
        _write(folder, f"CLIPINF/{number:05d}.clpi", clpi([108.8], [CODING_AVC], ss_coding_types=[CODING_MVC]))
    for number in (21, 23, 25):
        _write(folder, f"CLIPINF/{number:05d}.clpi", clpi([108.8], [], ss_coding_types=[CODING_MVC]))
    for number, size in ((20, 100), (21, 60), (22, 90), (23, 55), (24, 900), (25, 500), (1, 10)):
        _stream(folder, number, size)


def _assert_3d_structure(structure: BdStructure) -> None:
    by_name = {p.name: p for p in structure.playlists}
    assert list(by_name) == ["00102.mpls", "00334.mpls", "00342.mpls"]
    assert (by_name["00334.mpls"].clips, by_name["00334.mpls"].angle_clips) == ([20, 24], [[22, 24]])
    assert by_name["00334.mpls"].mvc_clips == [21, 23, 25]
    assert by_name["00342.mpls"].mvc_clips == [25]  # the subset playlist is 3D too
    assert by_name["00102.mpls"].mvc_clips == []
    mvc = {c.number for c in structure.clips if c.mvc}
    assert mvc == {21, 23, 25}  # the base clips' SS blocks do not make them dependent
    assert {
        n for p in structure.playlists for n in p.mvc_clips
    } == mvc  # CLPI confirms every playlist's dependent clips
    assert {c.number: c.size_bytes for c in structure.clips} == {
        1: 10,
        20: 100,
        21: 60,
        22: 90,
        23: 55,
        24: 900,
        25: 500,
    }


async def test_3d_disc_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "")  # a folder needs no 7-Zip
    _bd3d_folder(tmp_path)
    _assert_3d_structure(await scan_structure(str(tmp_path)))


async def test_3d_disc_through_7z(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "src"
    _bd3d_folder(src)
    listing = "".join(
        f"Path = BDMV/STREAM/{n:05d}.m2ts\nFolder = -\nSize = {s}\n\n"
        for n, s in ((20, 100), (21, 60), (22, 90), (23, 55), (24, 900), (25, 500), (1, 10))
    )
    (tmp_path / "listing.txt").write_text(listing + "Path = BDMV/STREAM/SSIF\nFolder = +\nSize = 0\n\n")
    argv = tmp_path / "argv"
    fake_7zz(
        tmp_path,
        monkeypatch,
        f'printf "%s\\n" "$@" >> {argv}\n'
        f'case "$1" in x) /bin/cp -r {src}/. "$OUT"/ ;; l) /bin/cat {tmp_path / "listing.txt"} ;; esac',
    )
    _assert_3d_structure(await scan_structure("/dev/sr0"))
    lines = argv.read_text().splitlines()
    assert lines[:1] == ["x"]
    assert lines[lines.index("/dev/sr0") + 1 : lines.index("/dev/sr0") + 3] == [
        "BDMV/PLAYLIST/*.mpls",
        "BDMV/CLIPINF/*.clpi",
    ]
    assert lines[lines.index("l") : lines.index("l") + 5] == ["l", "-slt", "-ba", "--", "/dev/sr0"]
    assert lines[-1] == "BDMV/STREAM/*.m2ts"


async def test_2d_disc_with_a_raw_stream_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A film playlist plus a clip no playlist names (a raw stream MakeMKV lists as its own title)."""
    monkeypatch.setenv("PATH", "")
    _write(tmp_path, "PLAYLIST/00801.mpls", mpls([play_item(294, 7200.0)], marks=[1, 1]))
    _write(tmp_path, "CLIPINF/00294.clpi", clpi([7200.0], [CODING_AVC]))
    _write(tmp_path, "CLIPINF/00580.clpi", clpi([7200.0], [CODING_AVC]))
    _stream(tmp_path, 294, 2000)
    _stream(tmp_path, 580, 2000)
    structure = await scan_structure(str(tmp_path))
    assert [(p.name, p.clips, p.angle_clips, p.mvc_clips) for p in structure.playlists] == [
        ("00801.mpls", [294], [], [])
    ]
    assert structure.clips == [
        BdClip(number=294, seconds=7200.0, size_bytes=2000, mvc=False),
        BdClip(number=580, seconds=7200.0, size_bytes=2000, mvc=False),
    ]


async def test_folder_without_bdmv_is_empty(tmp_path: Path) -> None:
    assert await scan_structure(str(tmp_path)) == BdStructure()


async def test_failed_listing_keeps_the_clips_without_sizes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "src"
    _write(src, "PLAYLIST/00001.mpls", mpls([play_item(5, 10.0)]))
    _write(src, "CLIPINF/00005.clpi", clpi([10.0]))
    fake_7zz(tmp_path, monkeypatch, f'case "$1" in x) /bin/cp -r {src}/. "$OUT"/ ;; l) exit 2 ;; esac')
    structure = await scan_structure("/dev/sr0")
    assert [p.name for p in structure.playlists] == ["00001.mpls"]
    assert structure.clips == [BdClip(number=5, seconds=10.0, size_bytes=None, mvc=False)]


async def test_disc_without_bdmv_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_7zz(tmp_path, monkeypatch, "exit 1")
    assert await scan_structure("/dev/sr0") == BdStructure()


async def test_hung_extraction_times_out_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    fake_7zz(tmp_path, monkeypatch, "exec /bin/sleep 5")
    monkeypatch.setattr(bd_structure, "STRUCTURE_TIMEOUT_SECONDS", 0.2)
    with caplog.at_level(logging.INFO, logger="arm_ripper.scan.bd_structure"):
        assert await scan_structure("/dev/sr0") == BdStructure()
    assert any(
        "playlists=0 clips=0" in r.getMessage() and r.getMessage().endswith("reason=timeout") for r in caplog.records
    )


async def test_hung_listing_times_out_but_keeps_the_extracted_structure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    src = tmp_path / "src"
    _write(src, "PLAYLIST/00001.mpls", mpls([play_item(5, 10.0)]))
    _write(src, "CLIPINF/00005.clpi", clpi([10.0]))
    fake_7zz(tmp_path, monkeypatch, f'case "$1" in x) /bin/cp -r {src}/. "$OUT"/ ;; l) exec /bin/sleep 5 ;; esac')
    monkeypatch.setattr(bd_structure, "STRUCTURE_TIMEOUT_SECONDS", 0.5)
    with caplog.at_level(logging.INFO, logger="arm_ripper.scan.bd_structure"):
        structure = await scan_structure("/dev/sr0")
    assert len(structure.playlists) == 1 and structure.clips[0].size_bytes is None
    assert any(r.getMessage().endswith("reason=timeout") for r in caplog.records)


async def test_without_7z_is_empty_and_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    with caplog.at_level(logging.INFO, logger="arm_ripper.scan.bd_structure"):
        assert await scan_structure("/dev/sr0") == BdStructure()
    assert any("reason=no-7z" in r.getMessage() for r in caplog.records)


async def test_never_raises(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    async def _boom(_p: str) -> tuple[BdStructure, str]:
        raise OSError("disc gone")

    monkeypatch.setattr(bd_structure, "_read_disc", _boom)
    with caplog.at_level(logging.INFO, logger="arm_ripper.scan.bd_structure"):
        assert await scan_structure("/dev/sr0") == BdStructure()
    assert any("reason=error" in r.getMessage() for r in caplog.records)


async def test_logs_counts_and_elapsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("PATH", "")
    _write(tmp_path, "PLAYLIST/00001.mpls", mpls([play_item(5, 10.0)]))
    _write(tmp_path, "CLIPINF/00005.clpi", clpi([10.0]))
    with caplog.at_level(logging.INFO, logger="arm_ripper.scan.bd_structure"):
        await scan_structure(str(tmp_path))
    assert any(
        r.getMessage().startswith(f"bd_structure device={tmp_path} playlists=1 clips=1 elapsed_ms=")
        and r.getMessage().endswith("reason=ok")
        for r in caplog.records
    )
