"""The callbacks a rip reports each track's lifecycle through, and the byte-level detail a progress report can carry."""

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
