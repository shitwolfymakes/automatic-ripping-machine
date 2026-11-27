"""The whole Blu-ray structure read: playlists (MPLS) and clips (CLPI + STREAM sizes) from one disc.

Orchestration only. The disc is read by `bd_extract`'s killable 7-Zip children
(one extraction of PLAYLIST + CLIPINF into a temp dir, one metadata listing of
STREAM); a disc folder is read directly. Decoding is `bd_playlists.parse_playlists`
and `bd_clips.build_clips`. Soft-fail: any error or timeout yields an empty
structure.
"""

from __future__ import annotations

import logging
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from arm_common.schemas import BdClip, BdPlaylist

from arm_ripper.scan.bd_clips import (
    CLIPINF_PATTERN,
    STREAM_PATTERN,
    build_clips,
    folder_stream_sizes,
    read_clpi_files,
)
from arm_ripper.scan.bd_extract import OK, extract_files, list_file_sizes
from arm_ripper.scan.bd_playlists import PLAYLIST_PATTERN, parse_playlists, read_mpls_files
from arm_ripper.source import is_folder_source

logger = logging.getLogger("arm_ripper.scan.bd_structure")

STRUCTURE_TIMEOUT_SECONDS = 60.0  # per 7-Zip child (the extraction, then the listing)


@dataclass(frozen=True)
class BdStructure:
    playlists: list[BdPlaylist] = field(default_factory=list)
    clips: list[BdClip] = field(default_factory=list)


def _read_folder(folder: Path) -> BdStructure:
    """A disc folder has no drive behind it: read it directly."""
    bdmv = folder / "BDMV"
    return BdStructure(
        parse_playlists(read_mpls_files(bdmv / "PLAYLIST")),
        build_clips(read_clpi_files(bdmv / "CLIPINF"), folder_stream_sizes(bdmv / "STREAM")),
    )


async def _read_disc(source_path: str) -> tuple[BdStructure, str]:
    """(structure, outcome): extract PLAYLIST + CLIPINF, then list STREAM; the first failed outcome is reported."""
    with tempfile.TemporaryDirectory(prefix="arm-bd-") as tmp:
        reason = await extract_files(
            source_path, Path(tmp), STRUCTURE_TIMEOUT_SECONDS, [PLAYLIST_PATTERN, CLIPINF_PATTERN]
        )
        if reason != OK:
            return BdStructure(), reason
        playlists = parse_playlists(read_mpls_files(Path(tmp)))
        clipinfo = read_clpi_files(Path(tmp))
    sizes, reason = await list_file_sizes(source_path, STRUCTURE_TIMEOUT_SECONDS, STREAM_PATTERN)
    return BdStructure(playlists, build_clips(clipinfo, sizes)), reason


async def scan_structure(device_path: str) -> BdStructure:
    """The disc's playlists and clips; logs the counts, elapsed time and outcome. Never raises."""
    started = time.monotonic()
    try:
        if is_folder_source(device_path):
            structure, reason = _read_folder(Path(device_path)), OK
        else:
            structure, reason = await _read_disc(device_path)
    except Exception as e:  # noqa: BLE001 — soft-fail: this read is optional
        logger.debug("bd structure read failed for %s: %s", device_path, e)
        structure, reason = BdStructure(), "error"
    elapsed_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "bd_structure device=%s playlists=%d clips=%d elapsed_ms=%d reason=%s",
        device_path,
        len(structure.playlists),
        len(structure.clips),
        elapsed_ms,
        reason,
    )
    return structure
