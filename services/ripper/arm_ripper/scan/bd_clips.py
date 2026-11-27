"""Blu-ray clips: BDMV/CLIPINF/*.clpi decoding and the per-clip list with STREAM sizes.

Pure: the bytes come from `bd_disc_files`. A CLPI gives a clip's whole
presentation time (SequenceInfo) and whether it carries MVC dependent-view
video (stream coding type 0x20), which a 3D dependent clip declares in the
ProgramInfo_SS extension block, not in its main ProgramInfo.

Layout (big-endian): magic "HDMV", version[4], SequenceInfo_start u32,
ProgramInfo_start u32, CPI_start u32, ClipMark_start u32, ExtensionData_start
u32. SequenceInfo = length u32, reserved u8, number_of_ATC_sequences u8, each
ATC sequence = SPN_ATC_start u32, number_of_STC_sequences u8, offset_STC_id u8,
each STC sequence = PCR_PID u16, SPN_STC_start u32, presentation start u32,
presentation end u32 (45 kHz). ProgramInfo = length u32, reserved u8,
number_of_programs u8, each program = SPN u32, PMT PID u16, number_of_streams
u8, number_of_groups u8, each stream = PID u16, coding-info length u8, then
the coding info whose first byte is the stream coding type.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

from arm_common.schemas import BdClip

from arm_ripper.scan.bd_extension_data import extension_block

CLIPINF_PATTERN = "BDMV/CLIPINF/*.clpi"
STREAM_PATTERN = "BDMV/STREAM/*.m2ts"
_CLPI_RE = re.compile(r"^(\d{5}\.clpi)(?:;\d+)?$", re.IGNORECASE)
_M2TS_RE = re.compile(r"^(\d{5}\.m2ts)(?:;\d+)?$", re.IGNORECASE)
_MAGIC = b"HDMV"
_TICKS_PER_SECOND = 45000
_CODING_MVC_DEPENDENT = 0x20
_BASE_VIDEO_CODINGS = frozenset({0x02, 0x1B, 0x24, 0xEA})  # MPEG-2, AVC, HEVC, VC-1
_PROGRAM_INFO_SS = (2, 5)  # ExtensionData type, version of the dependent view's ProgramInfo
_STC_SIZE = 14
_PROGRAM_HEADER = 8
_STREAM_HEADER = 3


def _clip_seconds(data: bytes, start: int) -> float:
    """Sum of every STC sequence's presentation span in the SequenceInfo at `start`."""
    (atc_count,) = struct.unpack_from(">B", data, start + 5)
    pos = start + 6
    ticks = 0
    for _ in range(atc_count):
        (stc_count,) = struct.unpack_from(">B", data, pos + 4)
        pos += 6
        for _ in range(stc_count):
            _pid, _spn, begin, end = struct.unpack_from(">HIII", data, pos)
            ticks += max(end - begin, 0)
            pos += _STC_SIZE
    return ticks / _TICKS_PER_SECOND


def _coding_types(data: bytes, start: int) -> set[int]:
    """Stream coding types of the ProgramInfo at `start`."""
    (program_count,) = struct.unpack_from(">B", data, start + 5)
    pos = start + 6
    types: set[int] = set()
    for _ in range(program_count):
        (stream_count,) = struct.unpack_from(">B", data, pos + 6)
        pos += _PROGRAM_HEADER
        for _ in range(stream_count):
            (info_length,) = struct.unpack_from(">B", data, pos + 2)
            types.add(data[pos + _STREAM_HEADER])
            pos += _STREAM_HEADER + info_length
    return types


def parse_clpi(data: bytes) -> tuple[float, bool] | None:
    """(clip seconds, is a dependent-view clip) of one .clpi; None when malformed or truncated.

    A dependent-view clip declares MVC video (in its ProgramInfo or, on the
    discs checked, the ProgramInfo_SS extension) and has no base-view video of
    its own. A 3D base clip can carry a ProgramInfo_SS naming the MVC stream of
    its pair, so the SS block alone does not mark a dependent clip.
    """
    if data[:4] != _MAGIC:
        return None
    try:
        sequence_start, program_start = struct.unpack_from(">II", data, 8)
        (ext_start,) = struct.unpack_from(">I", data, 24)
        seconds = _clip_seconds(data, sequence_start)
        own = _coding_types(data, program_start)
        ss_start = extension_block(data, ext_start, _PROGRAM_INFO_SS)
        declared = own | (_coding_types(data, ss_start) if ss_start is not None else set())
    except struct.error, IndexError:
        return None
    return seconds, _CODING_MVC_DEPENDENT in declared and not own & _BASE_VIDEO_CODINGS


def build_clips(clipinfo: dict[str, bytes], stream_sizes: dict[str, int]) -> list[BdClip]:
    """One BdClip per parseable CLPI (`00364.clpi`), ordered by clip number, sized from `stream_sizes`."""
    clips: list[BdClip] = []
    for name, data in sorted(clipinfo.items()):
        parsed = parse_clpi(data)
        if parsed is None:
            continue
        number = int(name[:5])
        clips.append(
            BdClip(number=number, seconds=parsed[0], size_bytes=stream_sizes.get(f"{number:05d}.m2ts"), mvc=parsed[1])
        )
    return clips


def read_clpi_files(directory: Path) -> dict[str, bytes]:
    """{lower-cased name: bytes} of the .clpi files under `directory`; {} when it is missing."""
    if not directory.is_dir():
        return {}
    return {p.name.lower(): p.read_bytes() for p in directory.rglob("*") if p.is_file() and _CLPI_RE.match(p.name)}


def folder_stream_sizes(directory: Path) -> dict[str, int]:
    """{lower-cased name: size} of the .m2ts files in a disc folder's STREAM directory; {} when it is missing."""
    if not directory.is_dir():
        return {}
    return {p.name.lower(): p.stat().st_size for p in directory.iterdir() if p.is_file() and _M2TS_RE.match(p.name)}
