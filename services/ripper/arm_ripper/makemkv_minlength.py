"""The shortest title MakeMKV lists, shared by the scan and the rip so they agree on the disc's titles."""

# MakeMKV's own default minimum. The scan's `makemkvcon info` passes it
# explicitly, so the titles the Backend stores are exactly the ones a rip at
# this minimum or above can write.
MAKEMKV_SCAN_MIN_LENGTH_SECONDS = 120


def rip_min_length_seconds(session_min_length_seconds: int) -> int:
    """The rip's `--minlength`: the session's minimum, never below the scan's, so the rip writes no title the scan
    did not list."""
    return max(session_min_length_seconds, MAKEMKV_SCAN_MIN_LENGTH_SECONDS)
