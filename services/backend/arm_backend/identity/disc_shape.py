"""The disc's title structure as a movie-vs-TV signal.

Identify searches TMDb movies first unless something says TV. A season number
in the label used to be the only such signal, so a series disc labelled just
"Kolchak The Night Stalker Disc 1" matched a placeholder TMDb *movie* while the
1974 series sat one search away. The scan already knows better: a movie disc is
one feature plus short extras, a TV disc is several episodes of about the same
length.

`looks_episodic` reads only the scan's title durations. Pure; no I/O.
"""

from __future__ import annotations

from collections.abc import Sequence
from statistics import median

from arm_common.schemas import ScanTitle

# An episode runs from a half-hour sitcom without ads to an hour drama.
EPISODE_MIN_SECONDS = 18 * 60
EPISODE_MAX_SECONDS = 70 * 60
# Anything this long is a feature, unless it is a "play all" of the episodes.
FEATURE_MIN_SECONDS = 75 * 60
MIN_EPISODES = 3
# Episodes of one series vary a little; unrelated featurettes vary a lot.
SIMILARITY = 0.15
# A "play all" title is the episodes' total, give or take menus and gaps.
PLAY_ALL_TOLERANCE = 0.10


def looks_episodic(titles: Sequence[ScanTitle]) -> bool:
    """True for a disc of at least three episode-length titles within 15% of
    their median length, and no feature-length title other than a "play all"
    (one roughly equal to the episodes' total)."""
    durations = [t.duration_seconds for t in titles if t.duration_seconds and t.duration_seconds > 0]
    in_range = [d for d in durations if EPISODE_MIN_SECONDS <= d <= EPISODE_MAX_SECONDS]
    if len(in_range) < MIN_EPISODES:
        return False
    mid = median(in_range)
    episodes = [d for d in in_range if abs(d - mid) <= SIMILARITY * mid]
    if len(episodes) < MIN_EPISODES:
        return False
    total = sum(episodes)
    for d in durations:
        if d >= FEATURE_MIN_SECONDS and abs(d - total) > PLAY_ALL_TOLERANCE * total:
            return False
    return True
