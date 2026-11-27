"""Synthetic Blu-ray structure files (MPLS / CLPI) for the scan tests.

The byte layouts mirror the real discs the readers were checked against:
a multi-angle PlayItem with an angle table, 3D dependent-view SubPaths in the
MPLS ExtensionData (type 2, version 2) and a ProgramInfo_SS block (type 2,
version 5) in the dependent clip's CLPI. Nothing here is taken from a disc.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence
from pathlib import Path

import pytest

TICKS = 45000
SS_SUBPATHS = (2, 2)  # MPLS ExtensionData: SubPaths of the stereoscopic extension
PROGRAM_INFO_SS = (2, 5)  # CLPI ExtensionData: ProgramInfo of the dependent view
SUBPATH_MVC = 8
SUBPATH_TEXT_SUBTITLE = 4
CODING_AVC = 0x1B
CODING_MVC = 0x20


def play_item(clip: int, seconds: float, *, extra_angles: Sequence[int] = (), start: int = 0) -> bytes:
    """A PlayItem; `extra_angles` are the clips of angles 2, 3, ... (angle 1 is `clip`)."""
    body = f"{clip:05d}".encode() + b"M2TS"
    body += struct.pack(">H", 0x10 | 1 if extra_angles else 0x01)  # multi-angle bit / connection_condition
    body += b"\x00"  # ref_to_STC_id
    body += struct.pack(">II", start, start + int(seconds * TICKS))
    body += b"\x00" * 8 + b"\x00" + b"\x00" + b"\x00\x00"  # UO mask, random access, still mode, still time
    if extra_angles:
        body += bytes([len(extra_angles) + 1, 0])
        for angle_clip in extra_angles:
            body += f"{angle_clip:05d}".encode() + b"M2TS" + b"\x00"
    return struct.pack(">H", len(body)) + body


def sub_play_item(clip: int, *, extra_clips: Sequence[int] = ()) -> bytes:
    """A SubPlayItem; `extra_clips` make it a multi-clip entry (one clip per angle)."""
    body = f"{clip:05d}".encode() + b"M2TS"
    body += struct.pack(">I", (1 << 1) | bool(extra_clips))  # connection_condition, is_multi_clip
    body += b"\x00" + struct.pack(">II", 0x7FFF8, 0x7FFF8 + TICKS)  # STC id, IN, OUT
    body += struct.pack(">HI", 0, 0x7FFF8)  # sync PlayItem id, sync start PTS
    if extra_clips:
        body += bytes([len(extra_clips) + 1, 0])
        for extra in extra_clips:
            body += f"{extra:05d}".encode() + b"M2TS" + b"\x00"
    return struct.pack(">H", len(body)) + body


def sub_path(path_type: int, items: Sequence[bytes]) -> bytes:
    body = bytes([0, path_type]) + struct.pack(">H", 0) + bytes([0, len(items)]) + b"".join(items)
    return struct.pack(">I", len(body)) + body


def extension_data(blocks: dict[tuple[int, int], bytes]) -> bytes:
    """ExtensionData: header, one 12-byte entry per block, then the blocks (offsets from the start)."""
    first = 12 + 12 * len(blocks)
    entries = b""
    payload = b""
    for (ext_type, version), block in blocks.items():
        entries += struct.pack(">HHII", ext_type, version, first + len(payload), len(block))
        payload += block
    body = struct.pack(">I", first) + b"\x00" * 3 + bytes([len(blocks)]) + entries + payload
    return struct.pack(">I", len(body)) + body


def ss_sub_paths(paths: Sequence[bytes]) -> bytes:
    """The (2, 2) ExtensionData block: SubPaths of the stereoscopic extension."""
    body = struct.pack(">H", len(paths)) + b"".join(paths)
    return struct.pack(">I", len(body)) + body


def mpls(
    items: Sequence[bytes],
    marks: Sequence[int] | None = None,
    *,
    sub_paths: Sequence[bytes] = (),
    extension: bytes | None = None,
) -> bytes:
    """A minimal MPLS: header, PlayList (items + main SubPaths), PlayListMark, optional ExtensionData."""
    play_list = struct.pack(">HHH", 0, len(items), len(sub_paths)) + b"".join(items) + b"".join(sub_paths)
    play_list = struct.pack(">I", len(play_list)) + play_list
    mark_types = marks or []
    mark_block = struct.pack(">H", len(mark_types))
    for t in mark_types:
        mark_block += bytes([0, t]) + struct.pack(">HIHI", 0, 0, 0xFFFF, 0)
    mark_block = struct.pack(">I", len(mark_block)) + mark_block
    play_list_start = 40
    mark_start = play_list_start + len(play_list)
    ext_start = mark_start + len(mark_block) if extension is not None else 0
    header = b"MPLS0200" + struct.pack(">III", play_list_start, mark_start, ext_start)
    return header.ljust(play_list_start, b"\x00") + play_list + mark_block + (extension or b"")


def _sequence_info(stc_spans: Sequence[tuple[int, int]]) -> bytes:
    body = bytes([0, 1]) + struct.pack(">IBB", 0, len(stc_spans), 0)
    for start, end in stc_spans:
        body += struct.pack(">HIII", 0x1001, 0, start, end)
    return struct.pack(">I", len(body)) + body


def program_info(coding_types: Sequence[int]) -> bytes:
    """ProgramInfo / ProgramInfo_SS: one program with a stream per coding type."""
    body = bytes([0, 1]) + struct.pack(">IHBB", 0, 0x100, len(coding_types), 0)
    for pid, coding in enumerate(coding_types, start=0x1011):
        body += struct.pack(">HB", pid, 2) + bytes([coding, 0x61])
    return struct.pack(">I", len(body)) + body


def clpi(
    seconds: Sequence[float],
    coding_types: Sequence[int] = (CODING_AVC,),
    *,
    ss_coding_types: Sequence[int] | None = None,
) -> bytes:
    """A minimal CLPI: one ATC sequence with one STC span per entry of `seconds`, a ProgramInfo
    of `coding_types`, and a ProgramInfo_SS extension when `ss_coding_types` is given."""
    spans = []
    cursor = 1000
    for s in seconds:
        spans.append((cursor, cursor + int(s * TICKS)))
        cursor += int(s * TICKS) + 90
    sequence = _sequence_info(spans)
    program = program_info(coding_types)
    sequence_start = 40
    program_start = sequence_start + len(sequence)
    ext_start = program_start + len(program) if ss_coding_types is not None else 0
    header = b"HDMV0200" + struct.pack(">IIIII", sequence_start, program_start, 0, 0, ext_start)
    out = header.ljust(sequence_start, b"\x00") + sequence + program
    if ss_coding_types is not None:
        out += extension_data({PROGRAM_INFO_SS: program_info(ss_coding_types)})
    return out


def fake_7zz(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> Path:
    """A `7zz` shell script as the only executable on PATH; `body` runs with $OUT = the -o directory."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "7zz"
    script.write_text(
        '#!/bin/sh\nfor a in "$@"; do case "$a" in -o*) OUT="${a#-o}";; esac; done\n' + body + "\n",
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    return bin_dir
