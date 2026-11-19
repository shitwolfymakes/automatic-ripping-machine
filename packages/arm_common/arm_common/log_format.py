"""Pure formatters for the numbers that appear in job log messages."""

from __future__ import annotations

_SIZE_UNITS: tuple[tuple[str, int], ...] = (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024))
_QUARTERS: tuple[int, ...] = (100, 75, 50, 25)


def human_size(num_bytes: int | None) -> str:
    """Binary-unit size, one decimal above bytes (`41.1 MB`); `unknown size` when absent."""
    if num_bytes is None:
        return "unknown size"
    for unit, factor in _SIZE_UNITS:
        if num_bytes >= factor:
            return f"{num_bytes / factor:.1f} {unit}"
    return f"{num_bytes} B"


def human_duration(seconds: int | float | None) -> str:
    """Clock-style length: `m:ss` under an hour, `h:mm:ss` from an hour; `unknown length` when absent."""
    if seconds is None:
        return "unknown length"
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def elapsed(seconds: int | float) -> str:
    """Spoken-style elapsed time: `59s`, `6m42s`, `1h02m05s`."""
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def quarter_crossed(previous_pct: float | None, current_pct: float) -> int | None:
    """The highest of 25/50/75/100 with `previous < q <= current`, or None (also when there is no previous)."""
    if previous_pct is None:
        return None
    return next((q for q in _QUARTERS if previous_pct < q <= current_pct), None)
