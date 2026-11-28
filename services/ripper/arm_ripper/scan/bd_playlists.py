"""Blu-ray playlist structure: BDMV/PLAYLIST/*.mpls read without mounting.

Reading the disc is `bd_extract`'s job (a killable 7-Zip subprocess into a
temp dir); this module decodes the extracted bytes (`parse_mpls`, pure)
and `bd_structure` runs the async scan that bounds, times and logs it.

What is decoded: the PlayItems with every angle's clip, the chapter marks, and
the 3D dependent-view clips of type 8 (MVC) SubPaths, which a 3D disc keeps in
the ExtensionData's stereoscopic SubPath block (2, 2) and an older authoring
may keep in the main SubPath list.
"""

from __future__ import annotations

import logging
import re
import struct
from dataclasses import dataclass
from pathlib import Path

from arm_common.schemas import BdPlaylist

from arm_ripper.scan.bd_extension_data import extension_block

logger = logging.getLogger("arm_ripper.scan.bd_playlists")

PLAYLIST_TIMEOUT_SECONDS = 60.0

PLAYLIST_PATTERN = "BDMV/PLAYLIST/*.mpls"
_MPLS_RE = re.compile(r"^(\d{5}\.mpls)(?:;\d+)?$", re.IGNORECASE)
_TICKS_PER_SECOND = 45000
_MAGIC = b"MPLS"
_MARK_TYPE_ENTRY = 1  # PlayListMark entry mark = a chapter point
_MARK_SIZE = 14
_MULTI_ANGLE_FLAG = 0x10  # bit 4 of the u16 after the codec id; low 4 bits are connection_condition
_SUBPATH_TYPE_MVC = 8  # out-of-mux dependent-view (3D) video
_SS_SUBPATHS = (2, 2)  # ExtensionData type, version of the stereoscopic SubPath block
_ANGLE_COUNT_OFFSET = 32  # in a PlayItem body (after its u16 length): number_of_angles u8
_ANGLE_TABLE_OFFSET = 34  # then reserved u8 flags, then 10-byte entries for angles 2..n
_ANGLE_ENTRY_SIZE = 10  # clip name[5], codec[4], ref_to_STC_id u8
_SUBPLAYITEM_FIXED = 28  # SubPlayItem body before the multi-clip block
_MULTI_CLIP_TABLE_OFFSET = 30  # number_of_multi_clip_entries u8, reserved u8, then 10-byte entries


def _clip_number(name: bytes) -> int:
    """`00202` -> 202. Raises ValueError for a clip name that is not five digits."""
    text = name.decode("ascii")
    if len(text) != 5 or not text.isdigit():
        raise ValueError(f"clip name {text!r} is not numeric")
    return int(text)


def _sized(data: bytes, pos: int) -> tuple[bytes, int]:
    """(body, next position) of the u16-length-prefixed structure at `pos`; ValueError when it overruns the data."""
    (length,) = struct.unpack_from(">H", data, pos)
    body = data[pos + 2 : pos + 2 + length]
    if len(body) != length:
        raise ValueError("structure runs past the end of the file")
    return body, pos + 2 + length


@dataclass(frozen=True)
class _PlayItems:
    clips: list[int]
    ticks: list[int]
    extra_angles: list[list[int]]  # per item: the clips of angles 2..n (empty without angles)
    end: int


def _parse_play_item(body: bytes) -> tuple[int, int, list[int]]:
    """(clip, ticks, clips of angles 2..n) of one PlayItem body.

    Body: clip name[5], codec[4], flags u16, ref_to_STC_id u8, IN u32, OUT u32
    (45 kHz), UO mask[8], random access u8, still mode u8, still time u16;
    a multi-angle item continues with number_of_angles u8, a flags u8 and one
    10-byte entry per angle after the first.
    """
    (flags,) = struct.unpack_from(">H", body, 9)
    in_time, out_time = struct.unpack_from(">II", body, 12)
    extra: list[int] = []
    if flags & _MULTI_ANGLE_FLAG:
        angle_count = body[_ANGLE_COUNT_OFFSET]
        for i in range(angle_count - 1):
            at = _ANGLE_TABLE_OFFSET + i * _ANGLE_ENTRY_SIZE
            if len(body) < at + _ANGLE_ENTRY_SIZE:
                raise ValueError("angle table is truncated")
            extra.append(_clip_number(body[at : at + 5]))
    return _clip_number(body[:5]), max(out_time - in_time, 0), extra


def _parse_play_items(data: bytes, playlist_start: int) -> _PlayItems:
    """The PlayList at `playlist_start`: length u32, reserved u16, number_of_PlayItems u16,
    number_of_SubPaths u16, then the PlayItems (u16 length-prefixed)."""
    (count,) = struct.unpack_from(">H", data, playlist_start + 6)
    clips: list[int] = []
    ticks: list[int] = []
    extra_angles: list[list[int]] = []
    pos = playlist_start + 10
    for _ in range(count):
        body, pos = _sized(data, pos)
        clip, item_ticks, extra = _parse_play_item(body)
        clips.append(clip)
        ticks.append(item_ticks)
        extra_angles.append(extra)
    return _PlayItems(clips, ticks, extra_angles, pos)


def _angle_clips(clips: list[int], extra_angles: list[list[int]]) -> list[list[int]]:
    """One list per extra angle, parallel to `clips`; an item without that angle plays its own clip."""
    angle_total = max((len(extra) for extra in extra_angles), default=0)
    return [
        [extra[angle] if angle < len(extra) else clip for clip, extra in zip(clips, extra_angles, strict=True)]
        for angle in range(angle_total)
    ]


def _sub_play_item_clips(body: bytes) -> list[int]:
    """Clips of one SubPlayItem body: its own, plus one per extra multi-clip entry (one per angle).

    Body: clip name[5], codec[4], flags u32 (bit 0 = is_multi_clip), ref_to_STC_id u8,
    IN u32, OUT u32, sync_PlayItem_id u16, sync_start_PTS u32; a multi-clip entry
    continues with number_of_clip_entries u8, reserved u8 and 10-byte entries after the first.
    """
    clips = [_clip_number(body[:5])]
    (flags,) = struct.unpack_from(">I", body, 9)
    if flags & 1:
        entry_count = body[_SUBPLAYITEM_FIXED]
        for i in range(entry_count - 1):
            at = _MULTI_CLIP_TABLE_OFFSET + i * _ANGLE_ENTRY_SIZE
            if len(body) < at + _ANGLE_ENTRY_SIZE:
                raise ValueError("multi-clip table is truncated")
            clips.append(_clip_number(body[at : at + 5]))
    return clips


def _parse_sub_paths(data: bytes, pos: int, count: int) -> list[int]:
    """Clips of the type-8 (MVC dependent view) SubPaths among `count` SubPaths starting at `pos`.

    SubPath = length u32, reserved u8, SubPath_type u8, reserved u16 (is_repeat),
    reserved u8, number_of_SubPlayItems u8, then the u16 length-prefixed SubPlayItems.
    """
    found: list[int] = []
    for _ in range(count):
        (length,) = struct.unpack_from(">I", data, pos)
        if data[pos + 5] == _SUBPATH_TYPE_MVC:
            item_pos = pos + 10
            for _ in range(data[pos + 9]):
                body, item_pos = _sized(data, item_pos)
                found += _sub_play_item_clips(body)
        pos += 4 + length
    return found


def _extension_mvc_clips(data: bytes, ext_start: int) -> list[int]:
    """Dependent-view clips in the stereoscopic SubPath block of the ExtensionData: length u32,
    number_of_SubPaths u16, then the SubPaths."""
    block = extension_block(data, ext_start, _SS_SUBPATHS)
    if block is None:
        return []
    (count,) = struct.unpack_from(">H", data, block + 4)
    return _parse_sub_paths(data, block + 6, count)


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
        playlist_start, mark_start, ext_start = struct.unpack_from(">III", data, 8)
        items = _parse_play_items(data, playlist_start)
        (sub_path_count,) = struct.unpack_from(">H", data, playlist_start + 8)
        mvc_clips = _parse_sub_paths(data, items.end, sub_path_count) + _extension_mvc_clips(data, ext_start)
        chapters = _count_chapters(data, mark_start)
    except struct.error, ValueError, IndexError:
        return None
    if not items.clips:
        return None
    return BdPlaylist(
        name=name,
        clips=items.clips,
        clip_seconds=[t / _TICKS_PER_SECOND for t in items.ticks],
        duration_seconds=round(sum(items.ticks) / _TICKS_PER_SECOND),
        chapter_count=chapters,
        angle_clips=_angle_clips(items.clips, items.extra_angles),
        mvc_clips=mvc_clips,
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
