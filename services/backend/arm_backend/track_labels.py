"""A track's "track N/M" position and the title the job's identity gives it, for job-log lines."""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

from arm_common import Job, Track


# Functional form: `index` shadows `tuple.index`, which the class form makes mypy reject.
TrackLabel = NamedTuple("TrackLabel", [("index", int), ("total", int), ("title", str | None)])


def _music_title(job: Job, track: Track) -> str | None:
    """The music track list's title for this track's 1-based index, or None."""
    music = (job.metadata_json or {}).get("music")
    listed = music.get("tracks") if isinstance(music, dict) else None
    if not isinstance(listed, list) or not 0 <= track.index - 1 < len(listed):
        return None
    entry = listed[track.index - 1]
    title = entry.get("title") if isinstance(entry, dict) else None
    return title if isinstance(title, str) else None


def _title(job: Job, track: Track) -> str | None:
    """The identified title: the music track list, else the track's episode name, title or label."""
    return _music_title(job, track) or track.episode_name or track.title or track.label


def track_label(job: Job, track: Track, tracks: Sequence[Track]) -> TrackLabel:
    """Position of `track` by index among all of the job's tracks (excluded ones count), with its title."""
    position = 1 + sum(1 for other in tracks if other.index < track.index)
    return TrackLabel(position, len(tracks), _title(job, track))
