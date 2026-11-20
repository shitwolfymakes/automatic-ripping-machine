"""The minimum title length shared by MakeMKV's scan and rip, so the disc's title list and its files always match."""

import logging

logger = logging.getLogger(__name__)

# MakeMKV's own default: the minimum when the backend supplies none.
DEFAULT_MIN_TITLE_LENGTH_SECONDS = 120


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
