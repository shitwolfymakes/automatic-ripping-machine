"""The 3D reference disc (genericized) as a structure scan and as MakeMKV's title list."""

from __future__ import annotations

import json
from pathlib import Path

from arm_common import DiscType
from arm_common.schemas import BdClip, BdPlaylist, ScanResult, ScanTitle

_FIXTURE = Path(__file__).resolve().parents[3] / "packages/arm_common/tests/fixtures/scan_titles/bd_3d_angles.json"

# Track keys of the four titles, in card order.
EXTRA = "00102.mpls"
PICK = "00334.mpls:1"
OTHER_ANGLE = "00334.mpls:2"
SUBSET = "00342.mpls"


def _playlist(name: str, clips: list[int], seconds: list[float], chapters: int, **kw: object) -> BdPlaylist:
    return BdPlaylist(
        name=name,
        clips=clips,
        clip_seconds=seconds,
        duration_seconds=round(sum(seconds)),
        chapter_count=chapters,
        **kw,  # type: ignore[arg-type]
    )


def br3d_structure_scan() -> ScanResult:
    """What the ripper posts: playlists and clips, no MakeMKV titles yet."""
    return ScanResult(
        disc_type=DiscType.BLURAY,
        volume_label="FEATURE_3D",
        playlists=[
            _playlist("00342.mpls", [368], [9698.0], 1, mvc_clips=[369]),
            _playlist("00102.mpls", [100], [287.0], 1),
            _playlist(
                "00334.mpls", [364, 368], [109.0, 9698.0], 16, angle_clips=[[366, 368]], mvc_clips=[365, 367, 369]
            ),
        ],
        clips=[
            BdClip(number=100, seconds=287.0, size_bytes=308_000_000),
            BdClip(number=364, seconds=109.0, size_bytes=1_000_000),
            BdClip(number=365, seconds=109.0, size_bytes=200_000, mvc=True),
            BdClip(number=366, seconds=109.0, size_bytes=900_000),
            BdClip(number=367, seconds=109.0, size_bytes=180_000, mvc=True),
            BdClip(number=368, seconds=9698.0, size_bytes=40_000_000_000),
            BdClip(number=369, seconds=9698.0, size_bytes=8_000_000_000, mvc=True),
        ],
    )


def br3d_makemkv_titles() -> list[ScanTitle]:
    """MakeMKV's list for the same disc (the shared fixture): numbers 0-3, angle 2 as its own title."""
    return [ScanTitle.model_validate(t) for t in json.loads(_FIXTURE.read_text())]
