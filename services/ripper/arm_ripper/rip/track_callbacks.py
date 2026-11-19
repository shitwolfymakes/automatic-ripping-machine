"""The callbacks a rip reports each track's lifecycle through, the byte-level detail a progress report can carry, and
the adapter that turns a byte count into a track's progress."""

import time
from collections.abc import Awaitable, Callable
from typing import NotRequired, Protocol, TypedDict

from arm_common.schemas import TrackView

from arm_ripper.rip.result import RipResult

OnTrackStart = Callable[[TrackView], Awaitable[None]]
OnTrackDone = Callable[[TrackView, RipResult], Awaitable[None]]


class TransferStats(TypedDict):
    """Byte-level detail for a copy whose size is known (the full-disc dump)."""

    bytes_done: int
    bytes_total: int | None
    rate_bps: float | None
    # "verifying" while the ripped files are hashed after makemkvcon exits.
    phase: NotRequired[str]


class OnTrackProgress(Protocol):
    def __call__(self, track: TrackView, fraction: float, stats: TransferStats | None = None, /) -> Awaitable[None]: ...


# (bytes copied so far, total bytes or None when the size is not known in advance)
OnByteProgress = Callable[[int, int | None], Awaitable[None]]


def track_byte_progress(track: TrackView, on_track_progress: OnTrackProgress | None) -> OnByteProgress:
    """An OnByteProgress that reports each byte count as `track`'s progress, with the average rate since this call.

    The fraction is the share of the total copied, or 0 when the total is unknown. Does nothing without a listener.
    """
    started = time.monotonic()

    async def report(done: int, total: int | None) -> None:
        if on_track_progress is None:
            return
        elapsed = time.monotonic() - started
        stats: TransferStats = {
            "bytes_done": done,
            "bytes_total": total,
            "rate_bps": done / elapsed if elapsed > 0 else None,
        }
        await on_track_progress(track, min(done / total, 1.0) if total else 0.0, stats)

    return report
