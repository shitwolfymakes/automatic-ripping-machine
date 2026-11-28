"""A release year written inside brackets: `(2017)` or `[2017]`.

Only a bracketed number counts. A bare year is ambiguous (`ALIEN_1979` is a
release year, `WONDER_WOMAN_1984` and `1917` are titles), so it stays in the
title for the evidence reader to weigh.
"""

from __future__ import annotations

import re

_BRACKETED_YEAR_RE = re.compile(r"[(\[](\d{4})[)\]]")
# The first year cinema could have: nothing earlier is a release year.
_MIN_YEAR = 1888


def bracketed_year(text: str, *, max_year: int) -> int | None:
    """The first `(YYYY)` / `[YYYY]` in `text` between 1888 and `max_year`, else None."""
    for m in _BRACKETED_YEAR_RE.finditer(text):
        year = int(m.group(1))
        if _MIN_YEAR <= year <= max_year:
            return year
    return None
