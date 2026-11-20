"""A rip's outcome counted over the tracks it is for: every track the selection did not exclude."""

from collections.abc import Sequence

from arm_common import Track, TrackStatus


def kept_tracks(tracks: Sequence[Track]) -> list[Track]:
    """The tracks the rip is for: every track the selection did not exclude."""
    return [t for t in tracks if not t.excluded]


def rip_outcome_counts(tracks: Sequence[Track]) -> tuple[int, int, int]:
    """Done, failed and total among the kept tracks: an excluded title is ripped
    and kept on disk, but it neither makes the rip partial nor counts toward it."""
    kept = kept_tracks(tracks)
    done = sum(1 for t in kept if t.status == TrackStatus.DONE)
    failed = sum(1 for t in kept if t.status == TrackStatus.FAILED)
    return done, failed, len(kept)
