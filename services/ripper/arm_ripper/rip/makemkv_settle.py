"""Tells whether a makemkvcon run is finished writing, without waiting for it to exit.

A run that has said it is complete may still be closing its file. These checks read the process's open file
descriptors and the output sizes, so makemkvcon is only ended once nothing it wrote can still change.
"""

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("arm_ripper.rip.makemkv")

# After the run says it is complete, makemkvcon gets this long to exit on its own before it is ended.
COMPLETION_GRACE_SECONDS = 10.0
# An output file must hold the same size across this gap to count as closed.
SIZE_STABLE_SECONDS = 2.0
# Between SIGTERM and SIGKILL of an ended run.
TERMINATE_WAIT_SECONDS = 5.0
# How often a run that has said it is complete, but is not yet provably closed, is checked again.
SETTLE_POLL_SECONDS = 2.0
# An output smaller than this share of the scan's expected size is logged as suspect.
TRUNCATION_RATIO = 0.9

_PROC = Path("/proc")
_EBML_MAGIC = 0x1A45DFA3
_SEGMENT_ID = 0x18538067
_HEAD_BYTES = 512

Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class RunWatch:
    """What a makemkvcon run is watched against: its output folder, the files it should leave, and whether it may be
    ended once those are provably closed."""

    output_dir: Path
    outputs: Callable[[], list[Path]]
    expected_files: int
    end_on_completion: bool = False


def open_files_under(pid: int, root: Path, proc_root: Path = _PROC) -> set[Path] | None:
    """The files process `pid` holds open under `root`; None when its descriptors cannot be read, which is not the
    same as holding none."""
    try:
        entries = list(proc_root.joinpath(str(pid), "fd").iterdir())
    except OSError:
        return None
    base = root.resolve()
    held: set[Path] = set()
    for entry in entries:
        try:
            target = Path(os.readlink(entry))
        except OSError:
            continue  # the descriptor closed between the listing and the read
        if target.is_relative_to(base):
            held.add(target)
    return held


def _sizes(paths: list[Path]) -> dict[Path, int] | None:
    try:
        return {p: p.stat().st_size for p in paths}
    except OSError:
        return None


async def sizes_stable(paths: list[Path], wait: float, sleep: Sleep = asyncio.sleep) -> bool:
    """True when every path exists and none changes size across `wait` seconds."""
    before = _sizes(paths)
    if before is None:
        return False
    await sleep(wait)
    return _sizes(paths) == before


async def run_is_settled(
    watch: RunWatch,
    pid: int,
    saved: int | None,
    *,
    proc_root: Path = _PROC,
    wait: float = SIZE_STABLE_SECONDS,
    sleep: Sleep = asyncio.sleep,
) -> bool:
    """True when the run holds no file open in its output folder, has left exactly the files it was to, and those
    files have stopped growing. `saved` is the count the run reported saving, when it reported one."""
    held = open_files_under(pid, watch.output_dir, proc_root)
    if held is None or held:
        return False
    files = watch.outputs()
    if len(files) != watch.expected_files or (saved is not None and saved != watch.expected_files):
        return False
    return await sizes_stable(files, wait, sleep)


def _vint(data: bytes, pos: int) -> tuple[int, int] | None:
    """The EBML variable-length integer at `pos` as (raw bytes value, length); None when it does not fit."""
    if pos >= len(data) or data[pos] == 0:
        return None
    length = 9 - data[pos].bit_length()
    if pos + length > len(data):
        return None
    return int.from_bytes(data[pos : pos + length], "big"), length


def _element_size(raw: int, length: int) -> int | None:
    """An element's size from its raw vint; None when it is the all-ones "unknown size"."""
    mask = (1 << (7 * length)) - 1
    value = raw & mask
    return None if value == mask else value


def _element(head: bytes, pos: int) -> tuple[int, int, int | None] | None:
    """The EBML element header at `pos` as (id, header length, size); the size is None when unknown."""
    ident = _vint(head, pos)
    if ident is None:
        return None
    size = _vint(head, pos + ident[1])
    if size is None:
        return None
    return ident[0], ident[1] + size[1], _element_size(*size)


def _segment_end(head: bytes) -> int | None:
    """Where the Segment ends, from the EBML header and Segment headers at the start of `head`; None when either is
    missing or the Segment's size is unknown."""
    ebml = _element(head, 0)
    if ebml is None or ebml[0] != _EBML_MAGIC or ebml[2] is None:
        return None
    segment_at = ebml[1] + ebml[2]
    segment = _element(head, segment_at)
    if segment is None or segment[0] != _SEGMENT_ID or segment[2] is None:
        return None
    return segment_at + segment[1] + segment[2]


def mkv_segment_complete(path: Path) -> bool:
    """True when the MKV's Segment element carries a known size that ends exactly at the end of the file, which is
    what a closed MakeMKV output looks like. Reads only the head of the file."""
    try:
        with path.open("rb") as f:
            head = f.read(_HEAD_BYTES)
        file_size = path.stat().st_size
    except OSError:
        return False
    return _segment_end(head) == file_size


def suspect_output(path: Path, size: int, expected_size: int | None) -> list[str]:
    """Why a finished output looks wrong: much smaller than the scan expected, or an MKV header never finalised.
    Empty when nothing looks wrong. Only ever logged."""
    problems: list[str] = []
    if expected_size and size < expected_size * TRUNCATION_RATIO:
        problems.append(f"{size} bytes is under 90% of the {expected_size} the scan expected")
    if not mkv_segment_complete(path):
        problems.append("its MKV Segment header is not finalised")
    return problems
