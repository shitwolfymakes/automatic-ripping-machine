"""Read a release year out of the values metadata providers return."""


def year_from(text: str) -> int | None:
    """The year a date-like string starts with ("1973-03-01" -> 1973), or None."""
    return int(text[:4]) if text[:4].isdigit() else None


def year_from_any(value: object) -> int | None:
    """A year given as an int, or as a string `year_from` can read; None for anything else."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return year_from(value)
    return None
