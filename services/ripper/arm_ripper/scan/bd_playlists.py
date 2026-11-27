"""Blu-ray playlist structure: BDMV/PLAYLIST/*.mpls read without mounting.

Reading the disc is `playlist_extract`'s job (a killable 7-Zip subprocess into
a temp dir); this module decodes the extracted bytes (`parse_mpls`, pure) and
runs the async scan step (`scan_playlists`) that bounds, times and logs it.
Soft-fail: any error or timeout yields an empty list.
"""

from __future__ import annotations

import asyncio
import logging
import re
import struct
import tempfile
import time
from pathlib import Path

from arm_common.schemas import BdPlaylist

from arm_ripper.scan.playlist_extract import OK, extract_mpls
from arm_ripper.source import is_folder_source

logger = logging.getLogger("arm_ripper.scan.bd_playlists")

PLAYLIST_TIMEOUT_SECONDS = 60.0

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


def read_mpls_files(directory: Path) -> dict[str, bytes]:
    """{lower-cased name: bytes} of the .mpls files under `directory`; {} when it is missing."""
    if not directory.is_dir():
        return {}
    return {p.name.lower(): p.read_bytes() for p in directory.rglob("*") if p.is_file() and _MPLS_RE.match(p.name)}


def parse_playlists(files: dict[str, bytes]) -> list[BdPlaylist]:
    """Every parseable playlist, ordered by name."""
    parsed = (parse_mpls(data, name) for name, data in sorted(files.items()))
    return [playlist for playlist in parsed if playlist is not None]


async def _extract_and_read(source_path: str) -> tuple[dict[str, bytes], str]:
    """Run the extraction into a temp dir and read what it left. The files are a few KB each on local disk."""
    with tempfile.TemporaryDirectory(prefix="arm-mpls-") as tmp:
        reason = await extract_mpls(source_path, Path(tmp), PLAYLIST_TIMEOUT_SECONDS)
        return (read_mpls_files(Path(tmp)) if reason == OK else {}), reason


async def _read_files(source_path: str) -> tuple[dict[str, bytes], str]:
    """(files, reason). A disc folder is read directly (no drive behind it); anything else through 7-Zip."""
    if is_folder_source(source_path):
        return await asyncio.to_thread(read_mpls_files, Path(source_path) / "BDMV" / "PLAYLIST"), OK
    return await _extract_and_read(source_path)


async def scan_playlists(device_path: str) -> list[BdPlaylist]:
    """The disc's playlists, bounded by PLAYLIST_TIMEOUT_SECONDS; logs the count, elapsed time and outcome."""
    started = time.monotonic()
    try:
        files, reason = await _read_files(device_path)
    except Exception as e:  # noqa: BLE001 — soft-fail: this read is optional
        logger.debug("bd playlists read failed for %s: %s", device_path, e)
        files, reason = {}, "error"
    playlists = parse_playlists(files)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "bd_playlists device=%s count=%d elapsed_ms=%d reason=%s", device_path, len(playlists), elapsed_ms, reason
    )
    return playlists
