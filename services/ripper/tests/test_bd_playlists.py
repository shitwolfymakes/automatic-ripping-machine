"""BD playlist reader: MPLS parsing from in-memory bytes, disc reads from a pycdlib image in tmp_path."""

from __future__ import annotations

import io
import logging
import struct
from pathlib import Path
from typing import Any

import pytest
from arm_common.schemas import BdPlaylist

from arm_ripper.scan import bd_playlists, udf_image
from arm_ripper.scan.bd_playlists import parse_mpls, probe_bd_playlists, scan_playlists

TICKS = 45000


def _item(clip: str, seconds: float, *, angles: int = 1, start: int = 0) -> bytes:
    body = clip.encode().ljust(5, b"0") + b"M2TS"
    body += struct.pack(">H", 0x10 if angles > 1 else 0x01)  # multi-angle bit / connection_condition
    body += b"\x00"  # ref_to_STC_id
    body += struct.pack(">II", start, start + int(seconds * TICKS))
    body += b"\x00" * 8 + b"\x00" + b"\x00" + b"\x00\x00"  # UO mask, flags, still mode, still time
    if angles > 1:
        body += bytes([angles, 0])
        for n in range(angles - 1):
            body += f"{n + 90:05d}".encode() + b"M2TS" + b"\x00"
    return struct.pack(">H", len(body)) + body


def mpls(items: list[bytes], marks: list[int] | None = None) -> bytes:
    """A minimal MPLS: header, PlayList of `items`, PlayListMark with mark types `marks`."""
    play_list = struct.pack(">HHH", 0, len(items), 0) + b"".join(items)
    play_list = struct.pack(">I", len(play_list)) + play_list
    mark_types = marks or []
    mark_block = struct.pack(">H", len(mark_types))
    for t in mark_types:
        mark_block += bytes([0, t]) + struct.pack(">HIHI", 0, 0, 0xFFFF, 0)
    mark_block = struct.pack(">I", len(mark_block)) + mark_block
    play_list_start = 40
    mark_start = play_list_start + len(play_list)
    header = b"MPLS0200" + struct.pack(">III", play_list_start, mark_start, 0)
    return header.ljust(play_list_start, b"\x00") + play_list + mark_block


# --- parse_mpls -----------------------------------------------------------------


def test_parse_durations_clip_order_and_chapters() -> None:
    data = mpls([_item("00005", 600.0), _item("00002", 90.5, start=1000)], marks=[1, 2, 1, 1])
    playlist = parse_mpls(data, "00202.mpls")
    assert playlist == BdPlaylist(
        name="00202.mpls",
        clips=[5, 2],
        clip_seconds=[600.0, 90.5],
        duration_seconds=round(690.5),
        chapter_count=3,
        multi_angle=False,
    )


def test_parse_multi_angle_records_primary_clip_only() -> None:
    data = mpls([_item("00010", 100.0, angles=3), _item("00011", 50.0)])
    playlist = parse_mpls(data, "00001.mpls")
    assert playlist is not None
    assert playlist.clips == [10, 11]
    assert playlist.multi_angle is True


def test_parse_reversed_times_count_as_zero() -> None:
    item = bytearray(_item("00001", 10.0))
    item[14:22] = struct.pack(">II", 900, 100)
    playlist = parse_mpls(mpls([bytes(item)]), "00001.mpls")
    assert playlist is not None
    assert playlist.clip_seconds == [0.0]


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"NOPE" + b"\x00" * 60,
        mpls([_item("00001", 1.0)])[:30],  # cut inside the header offsets' target
        mpls([_item("00001", 1.0)])[:60],  # cut inside the PlayItem
        mpls([_item("00001", 1.0)], marks=[1])[:-13],  # cut inside the marks
        mpls([]),  # no PlayItems
        mpls([_item("ABCDE", 1.0)]),  # non-numeric clip name
    ],
)
def test_parse_garbage_or_truncated_is_none(data: bytes) -> None:
    assert parse_mpls(data, "00001.mpls") is None


def test_parse_non_ascii_clip_name_is_none() -> None:
    item = bytearray(_item("00001", 1.0))
    item[2] = 0xFF
    assert parse_mpls(mpls([bytes(item)]), "00001.mpls") is None


# --- disc reads -------------------------------------------------------------------


def _write_image(path: Path, files: dict[str, bytes]) -> None:
    import pycdlib

    iso = pycdlib.PyCdlib()
    iso.new(udf="2.60")
    iso.add_directory("/BDMV", udf_path="/BDMV")
    iso.add_directory("/BDMV/PLAYLIST", udf_path="/BDMV/PLAYLIST")
    iso.add_directory("/BDMV/PLAYLIST/SUB", udf_path="/BDMV/PLAYLIST/sub")
    for i, (name, data) in enumerate(files.items()):
        iso.add_fp(io.BytesIO(data), len(data), f"/BDMV/PLAYLIST/F{i:07d}.;1", udf_path=f"/BDMV/PLAYLIST/{name}")
    iso.write(str(path))
    iso.close()


def test_probe_reads_playlists_from_a_udf_image(tmp_path: Path) -> None:
    image = tmp_path / "disc.iso"
    _write_image(
        image,
        {
            "00800.mpls": mpls([_item("00001", 120.0)], marks=[1]),
            "00001.mpls": mpls([_item("00002", 30.0)]),
            "notes.txt": b"not a playlist",
            "00003.mpls": b"garbage",
        },
    )
    playlists = probe_bd_playlists(str(image))
    assert [p.name for p in playlists] == ["00001.mpls", "00800.mpls"]
    assert playlists[1].chapter_count == 1
    assert playlists[1].duration_seconds == 120


def test_probe_image_without_bdmv_is_empty(tmp_path: Path) -> None:
    import pycdlib

    image = tmp_path / "dvd.iso"
    iso = pycdlib.PyCdlib()
    iso.new(udf="2.60")
    iso.add_directory("/VIDEO_TS", udf_path="/VIDEO_TS")
    iso.write(str(image))
    iso.close()
    assert probe_bd_playlists(str(image)) == []


def test_probe_reads_a_disc_folder(tmp_path: Path) -> None:
    folder = tmp_path / "disc"
    (folder / "BDMV" / "PLAYLIST").mkdir(parents=True)
    (folder / "BDMV" / "PLAYLIST" / "00001.MPLS").write_bytes(mpls([_item("00004", 10.0)]))
    (folder / "BDMV" / "PLAYLIST" / "readme.txt").write_bytes(b"x")
    playlists = probe_bd_playlists(str(folder))
    assert [(p.name, p.clips) for p in playlists] == [("00001.mpls", [4])]


def test_probe_folder_without_playlist_dir_is_empty(tmp_path: Path) -> None:
    (tmp_path / "BDMV").mkdir()
    assert probe_bd_playlists(str(tmp_path)) == []


def _pycdlib_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    import pycdlib

    def _open(self: Any, *_a: Any, **_k: Any) -> None:
        raise pycdlib.pycdlibexception.PyCdlibInvalidISO("Valid ISO9660 filesystems must have at least one PVD")

    monkeypatch.setattr(pycdlib.PyCdlib, "open", _open)


def test_probe_uses_7z_when_pycdlib_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    _pycdlib_refuses(monkeypatch)
    data = mpls([_item("00009", 60.0)])
    monkeypatch.setattr(
        udf_image,
        "list_files",
        lambda _p: [("BDMV/index.bdmv", 4), ("BDMV/PLAYLIST/00100.mpls", len(data)), ("BDMV/PLAYLIST/00101.mpls", 1)],
    )
    monkeypatch.setattr(udf_image, "read_file", lambda _p, inner: data if inner.endswith("00100.mpls") else None)
    playlists = probe_bd_playlists("/source/x.iso")
    assert [p.name for p in playlists] == ["00100.mpls"]


def test_probe_empty_when_7z_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _pycdlib_refuses(monkeypatch)
    monkeypatch.setattr(udf_image, "list_files", lambda _p: None)
    assert probe_bd_playlists("/source/x.iso") == []


def test_probe_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_p: str) -> dict[str, bytes]:
        raise OSError("disc gone")

    monkeypatch.setattr(bd_playlists, "_read_playlist_files", _boom)
    assert probe_bd_playlists("/dev/sr0") == []


# --- scan_playlists ---------------------------------------------------------------


async def test_scan_playlists_logs_count_and_elapsed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    found = [BdPlaylist(name="00001.mpls", clips=[1], clip_seconds=[1.0], duration_seconds=1, chapter_count=0)]
    monkeypatch.setattr(bd_playlists, "probe_bd_playlists", lambda _p: found)
    with caplog.at_level(logging.INFO, logger="arm_ripper.scan.bd_playlists"):
        assert await scan_playlists("/dev/sr0") == found
    assert any(r.getMessage().startswith("bd_playlists device=/dev/sr0 count=1 elapsed_ms=") for r in caplog.records)


async def test_scan_playlists_times_out_to_empty(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import threading

    release = threading.Event()
    monkeypatch.setattr(bd_playlists, "probe_bd_playlists", lambda _p: release.wait(5) and [])
    monkeypatch.setattr(bd_playlists, "PLAYLIST_TIMEOUT_SECONDS", 0.05)
    with caplog.at_level(logging.INFO, logger="arm_ripper.scan.bd_playlists"):
        assert await scan_playlists("/dev/sr0") == []
    release.set()
    assert any("count=0" in r.getMessage() for r in caplog.records)
