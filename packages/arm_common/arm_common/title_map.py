"""Map the structure's title refs to MakeMKV title numbers (pure).

MakeMKV numbers its own titles. The structure read gives refs (`00334.mpls:2`); a MakeMKV title is
the same version when its source (TINFO 16) and angle (TINFO 15, 1 when absent) match and the
durations agree within `DURATION_TOLERANCE_SECONDS`. Anything MakeMKV lists that maps to no ref
(raw-stream `00294.m2ts` titles, a title whose length disagrees) is MakeMKV-only; a ref MakeMKV does
not list at all is unexposed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from arm_common.disc_titles import title_ref
from arm_common.schemas import ScanTitle

DURATION_TOLERANCE_SECONDS = 2


@dataclass(frozen=True)
class TitleMap:
    numbers: dict[str, int]  # title ref -> MakeMKV title number
    makemkv_only: list[int]  # MakeMKV titles that map to no ref, in MakeMKV order
    unexposed: list[str]  # refs with no MakeMKV title, in ref order


def _key(title: ScanTitle) -> tuple[str, int] | None:
    """(lower-cased source, angle with None as 1) or None when the title has no source."""
    if not title.source_file:
        return None
    return title.source_file.lower(), title.angle or 1


def _ref(title: ScanTitle) -> str:
    return title_ref(title.source_file or "", title.angle)


def _matching_ref(title: ScanTitle, wanted: dict[tuple[str, int], ScanTitle]) -> str | None:
    """The ref of our title that MakeMKV's `title` is, or None."""
    key = _key(title)
    match = wanted.get(key) if key is not None else None
    if match is None or abs(match.duration_seconds - title.duration_seconds) > DURATION_TOLERANCE_SECONDS:
        return None
    return _ref(match)


def map_titles(ours: Sequence[ScanTitle], makemkv: Sequence[ScanTitle]) -> TitleMap:
    """Match `ours` (from `titles_from_structure`) to MakeMKV's titles by source, angle and duration.

    The first MakeMKV title for a ref wins; a later one for the same ref is MakeMKV-only.
    """
    wanted = {key: title for title in ours if (key := _key(title)) is not None}
    numbers: dict[str, int] = {}
    makemkv_only: list[int] = []
    for title in makemkv:
        ref = _matching_ref(title, wanted)
        if ref is None or ref in numbers:
            makemkv_only.append(title.index)
        else:
            numbers[ref] = title.index
    unexposed = [_ref(title) for title in wanted.values() if _ref(title) not in numbers]
    return TitleMap(numbers, makemkv_only, unexposed)
