"""Blu-ray playlist structure: BDMV/PLAYLIST/*.mpls read without mounting.

Disc I/O (`_read_playlist_files`, the same no-mount pycdlib open path as
`bd_meta`, with the 7-Zip UDF fallback and direct reads of a disc folder) is
kept apart from the pure MPLS decoding (`parse_mpls`) and from the async scan
step (`scan_playlists`) that bounds and times the read. Soft-fail: any error
yields an empty list.
"""

from __future__ import annotations

import asyncio
import logging
import re
import struct
import time
from io import BytesIO
from pathlib import Path

from arm_common.schemas import BdPlaylist

from arm_ripper.source import is_folder_source

logger = logging.getLogger("arm_ripper.scan.bd_playlists")

PLAYLIST_TIMEOUT_SECONDS = 60.0

_PLAYLIST_DIR = "/BDMV/PLAYLIST"
_MPLS_RE = re.compile(r"^(\d{5}\.mpls)(?:;\d+)?$", re.IGNORECASE)
_TICKS_PER_SECOND = 45000
_MAGIC = b"MPLS"
_MARK_TYPE_ENTRY = 1  # PlayListMark entry mark = a chapter point
_MARK_SIZE = 14
_MULTI_ANGLE_FLAG = 0x10  # bit 4 of the u16 after the codec id; low 4 bits are connection_condition
_PLAYITEM_HEADER = 2  # a PlayItem's own `length` field is not counted in it


def _clip_number(name: bytes) -> int:
    """`00202` -> 202. Raises ValueError for a clip name that is not five digits."""
    text = name.decode("ascii")
    if not text.isdigit():
        raise ValueError(f"clip name {text!r} is not numeric")
    return int(text)


def _parse_play_items(data: bytes, playlist_start: int) -> tuple[list[int], list[int], bool]:
    """(clip numbers, per-item ticks, any multi-angle) of the PlayList at `playlist_start`.

    Layout: PlayList = length u32, reserved u16, number_of_PlayItems u16,
    number_of_SubPaths u16, then the PlayItems. PlayItem = length u16, clip
    name[5], codec[4], flags u16, ref_to_STC_id u8, IN u32, OUT u32 (45 kHz).
    The next item is found from `length`, so the angle list that follows a
    multi-angle item is skipped; only the primary angle's clip is recorded.
    """
    (count,) = struct.unpack_from(">H", data, playlist_start + 6)
    clips: list[int] = []
    ticks: list[int] = []
    multi_angle = False
    pos = playlist_start + 10
    for _ in range(count):
        (length,) = struct.unpack_from(">H", data, pos)
        clips.append(_clip_number(data[pos + 2 : pos + 7]))
        (flags,) = struct.unpack_from(">H", data, pos + 11)
        multi_angle = multi_angle or bool(flags & _MULTI_ANGLE_FLAG)
        in_time, out_time = struct.unpack_from(">II", data, pos + 14)
        ticks.append(max(out_time - in_time, 0))
        pos += _PLAYITEM_HEADER + length
    return clips, ticks, multi_angle


def _count_chapters(data: bytes, mark_start: int) -> int:
    """Entry marks in the PlayListMark block: length u32, count u16, then 14-byte marks
    (reserved u8, mark_type u8, ref_to_PlayItem u16, time u32, es_pid u16, duration u32)."""
    (count,) = struct.unpack_from(">H", data, mark_start + 4)
    first = mark_start + 6
    return sum(1 for i in range(count) if data[first + i * _MARK_SIZE + 1] == _MARK_TYPE_ENTRY)


def parse_mpls(data: bytes, name: str) -> BdPlaylist | None:
    """Decode one .mpls file (big-endian); None when it is truncated, malformed or empty."""
    if data[:4] != _MAGIC:
        return None
    try:
        playlist_start, mark_start = struct.unpack_from(">II", data, 8)
        clips, ticks, multi_angle = _parse_play_items(data, playlist_start)
        chapters = _count_chapters(data, mark_start)
    except struct.error, ValueError, IndexError:
        return None
    if not clips:
        return None
    return BdPlaylist(
        name=name,
        clips=clips,
        clip_seconds=[t / _TICKS_PER_SECOND for t in ticks],
        duration_seconds=round(sum(ticks) / _TICKS_PER_SECOND),
        chapter_count=chapters,
        multi_angle=multi_angle,
    )


def _mpls_names(names: list[str]) -> dict[str, str]:
    """{lower-cased playlist name: original identifier} for the .mpls entries in `names`."""
    return {m.group(1).lower(): n for n in names if (m := _MPLS_RE.match(n))}


def _read_playlists_pycdlib(source_path: str) -> dict[str, bytes]:
    """Raises when pycdlib cannot open the image; {} when it has no /BDMV/PLAYLIST."""
    from pycdlib import PyCdlib  # lazy: keep import cost off the hot path
    from pycdlib.pycdlibexception import PyCdlibException

    iso = PyCdlib()
    iso.open(source_path)
    try:
        try:
            names = [
                child.file_identifier().decode("utf-8", "replace")
                for child in iso.list_children(udf_path=_PLAYLIST_DIR)
                if child is not None and not child.is_dir()
            ]
        except PyCdlibException:
            return {}  # a DVD / CD: no BDMV tree, nothing to read
        files: dict[str, bytes] = {}
        for name, identifier in _mpls_names(names).items():
            buf = BytesIO()
            iso.get_file_from_iso_fp(buf, udf_path=f"{_PLAYLIST_DIR}/{identifier}")
            files[name] = buf.getvalue()
        return files
    finally:
        iso.close()


def _read_playlists_udf(source_path: str) -> dict[str, bytes]:
    """7-Zip fallback for a UDF-only image PyCdlib refuses (no ISO 9660 PVD)."""
    from arm_ripper.scan import udf_image

    prefix = _PLAYLIST_DIR.lstrip("/") + "/"
    listing = udf_image.list_files(source_path) or []
    inside = [path[len(prefix) :] for path, _size in listing if path.startswith(prefix)]
    files: dict[str, bytes] = {}
    for name, identifier in _mpls_names(inside).items():
        data = udf_image.read_file(source_path, f"{prefix}{identifier}")
        if data is not None:
            files[name] = data
    return files


def _read_playlists_folder(folder: str) -> dict[str, bytes]:
    """Read BDMV/PLAYLIST of a disc folder directly."""
    directory = Path(folder) / "BDMV" / "PLAYLIST"
    if not directory.is_dir():
        return {}
    return {p.name.lower(): p.read_bytes() for p in directory.iterdir() if _MPLS_RE.match(p.name)}


def _read_playlist_files(source_path: str) -> dict[str, bytes]:
    """{playlist name: raw bytes} for every .mpls on the disc; {} when there is none. Raises on I/O failure."""
    if is_folder_source(source_path):
        return _read_playlists_folder(source_path)
    try:
        return _read_playlists_pycdlib(source_path)
    except Exception as e:  # noqa: BLE001 — pycdlib raises several flavours on an image it cannot open
        logger.debug("bd playlists via pycdlib failed for %s: %s; trying 7z", source_path, e)
        return _read_playlists_udf(source_path)


def probe_bd_playlists(source_path: str) -> list[BdPlaylist]:
    """Every parseable playlist on the disc, ordered by name. Never raises."""
    try:
        files = _read_playlist_files(source_path)
    except Exception as e:  # noqa: BLE001
        logger.debug("bd playlists probe failed for %s: %s", source_path, e)
        return []
    parsed = (parse_mpls(data, name) for name, data in sorted(files.items()))
    return [playlist for playlist in parsed if playlist is not None]


async def scan_playlists(device_path: str) -> list[BdPlaylist]:
    """Read the disc's playlists in a thread under PLAYLIST_TIMEOUT_SECONDS; log the count and elapsed time."""
    started = time.monotonic()
    try:
        playlists = await asyncio.wait_for(asyncio.to_thread(probe_bd_playlists, device_path), PLAYLIST_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        playlists = []
    elapsed_ms = int((time.monotonic() - started) * 1000)
    logger.info("bd_playlists device=%s count=%d elapsed_ms=%d", device_path, len(playlists), elapsed_ms)
    return playlists
