"""The minimum title length shared by MakeMKV's scan and rip, so the disc's title list and its files always match."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

logger = logging.getLogger(__name__)

# MakeMKV's own default: the minimum when the backend supplies none.
DEFAULT_MIN_TITLE_LENGTH_SECONDS = 120

# The minimum the current scan lists titles down to. Set around a scan by the
# job controller from the backend's setting; read by `makemkvcon info`.
_scan_minimum: ContextVar[int] = ContextVar("scan_min_title_length_seconds", default=DEFAULT_MIN_TITLE_LENGTH_SECONDS)


@contextmanager
def scanning_with_min_title_length(seconds: int) -> Iterator[None]:
    """Scan with `seconds` as the minimum title length inside the block."""
    token = _scan_minimum.set(seconds)
    try:
        yield
    finally:
        _scan_minimum.reset(token)


def scan_min_title_length() -> int:
    """The minimum title length the current scan lists titles down to."""
    return _scan_minimum.get()


def rip_min_length_seconds(session_min_length_seconds: int | None, floor_seconds: int) -> int:
    """The rip's `--minlength`: the session's minimum, never below the minimum the scan listed titles with, so the
    rip writes no title the scan did not list. With no session minimum it is that floor."""
    if session_min_length_seconds is None:
        return floor_seconds
    if session_min_length_seconds < floor_seconds:
        logger.info(
            "minlength raised from %ds to the configured minimum title length of %ds: "
            "the rip may not write a title the scan did not list",
            session_min_length_seconds,
            floor_seconds,
        )
        return floor_seconds
    return session_min_length_seconds
