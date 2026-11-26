"""Parse an ISO volume label into a cleaned search title and its season / disc markers.

Only trailing markers
count, and each needs an explicit S / D / P / DISC / SEASON prefix, so movie
titles that end in a number (APOLLO_13, BLADE_RUNNER_2049) yield no hint.
PART is deliberately not a disc marker: PART_2 is usually title content.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_WORD_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_SEASON_DISC_RE = re.compile(r"[\s-]S(\d+)[\s-]?(?:D|DISC)[\s-]?(\d+)$", re.IGNORECASE)
_DISC_WORD_RE = re.compile(r"[\s-]DISC[\s-](" + "|".join(_WORD_NUMBERS) + r")$", re.IGNORECASE)
# Group 1 captures which marker matched (P vs D/DISC) so callers can tell a
# lone `P<n>` (often a movie-part split, e.g. `..._DEATHLY_HALLOWS_P2`) apart
# from an explicit disc marker (see `part_marker_only` below).
_DISC_RE = re.compile(r"[\s-](P|D|DISC)[\s-]?(\d+)(?:[\s-]OF[\s-]?(\d+))?$", re.IGNORECASE)
_SEASON_KEYWORD_RE = re.compile(r"[\s-]SEASON[\s-]?(\d+)$", re.IGNORECASE)
_SEASON_RE = re.compile(r"[\s-]S(\d+)$", re.IGNORECASE)
# Bounded space run: an unbounded ` *` before SKU backtracks polynomially (ReDoS).
# `\d*\b` (rather than a bare `\w*`) requires SKU to be its own token,
# optionally followed by digits — "SKU1234" still strips, but "Skull" (which
# begins with the same three letters) is left alone.
_SKU_RE = re.compile(r" {0,4}\bSKU\d*\b", re.IGNORECASE)
_ASPECT_RE = re.compile(r"\b16[xX]9\b")
_BLURAY_SUFFIXES = (" - Blu-rayTM", " Blu-rayTM", " - BLU-RAYTM", " - BLU-RAY", " - Blu-ray", " Blu-ray", " BLU-RAY")
# Postgres columns backing season/disc_number/disc_total are int4; a garbage
# volume label with an absurd digit run must not 500 the identify request.
_SEASON_MAX = 999
_DISC_MAX = 999


def _bounded(text: str, lo: int, hi: int) -> int | None:
    """Parse a digit string, dropping it (None) if out of [lo, hi]. Also
    guards int()'s digit-count limit (a pathological run of digits raises
    ValueError rather than returning an enormous int)."""
    try:
        value = int(text)
    except ValueError:
        return None
    return value if lo <= value <= hi else None


@dataclass(frozen=True)
class LabelHints:
    title: str
    season: int | None
    disc_number: int | None
    disc_total: int | None
    # True when the only marker parse_label matched was a bare `P<n>` (no
    # season / DISC / D marker) — e.g. `..._DEATHLY_HALLOWS_P2`. A `P`-only
    # split usually separates parts of ONE film; the text before it can match
    # the wrong part on a title search, so callers keep the disc claim but
    # must not emit `title` for it.
    part_marker_only: bool = False


def _clean_label(raw: str) -> str:
    """The label folded to NFKC with underscores as spaces, and the aspect,
    SKU, Blu-ray-suffix and dot noise removed."""
    # NFKC folds compatibility glyphs (e.g. "Blu-ray™" -> "Blu-rayTM") so the
    # Blu-ray-suffix strip below still matches after non-ASCII input.
    raw = unicodedata.normalize("NFKC", raw)
    s = raw.replace("_", " ")
    s = _ASPECT_RE.sub("", s)
    s = _SKU_RE.sub("", s)
    for suffix in _BLURAY_SUFFIXES:
        s = s.replace(suffix, "")
    s = s.replace(".", " ").rstrip()
    return s


def _split_season_disc(s: str) -> tuple[str, int | None, int | None] | None:
    """A combined `S<n>D<n>` marker: (the text before it, season, disc), or None without one."""
    m = _SEASON_DISC_RE.search(s)
    if m:
        return s[: m.start()], _bounded(m.group(1), 0, _SEASON_MAX), _bounded(m.group(2), 1, _DISC_MAX)
    return None


def _split_disc(s: str) -> tuple[str, int | None, int | None, bool]:
    """A trailing disc marker (`DISC <word>`, or `P` / `D` / `DISC <n>` with
    an optional `OF <n>`): (the text before it, disc, total, whether the
    marker was a bare `P`). With no marker: (s, None, None, False)."""
    if m := _DISC_WORD_RE.search(s):
        return s[: m.start()], _WORD_NUMBERS[m.group(1).lower()], None, False
    if m := _DISC_RE.search(s):
        marker = m.group(1).upper()
        total = _bounded(m.group(3), 1, _DISC_MAX) if m.group(3) else None
        return s[: m.start()], _bounded(m.group(2), 1, _DISC_MAX), total, marker == "P"
    return s, None, None, False


def _split_season(s: str) -> tuple[str, int | None]:
    """A trailing `SEASON <n>` or `S<n>` marker: (the text before it, season). With no marker: (s, None)."""
    if m := _SEASON_KEYWORD_RE.search(s) or _SEASON_RE.search(s):
        return s[: m.start()], _bounded(m.group(1), 0, _SEASON_MAX)
    return s, None


def _tidy_title(s: str) -> str:
    """The search title: hyphens as spaces, whitespace collapsed, trailing ` :,` trimmed, lower-cased."""
    return re.sub(r"\s+", " ", s.replace("-", " ")).strip().rstrip(" :,").lower()


def parse_label(raw: str) -> LabelHints:
    """Parse a volume label into its search title and season / disc markers (see the module docstring)."""
    if not raw:
        return LabelHints("", None, None, None)
    s = _clean_label(raw)
    season: int | None
    disc: int | None
    total: int | None = None
    part_marker_only = False
    if combined := _split_season_disc(s):
        s, season, disc = combined
    else:
        s, disc, total, part_marker_only = _split_disc(s)
        s, season = _split_season(s)
        if season is not None:
            part_marker_only = False
    if total is not None and disc is not None and total < disc:
        total = None
    return LabelHints(_tidy_title(s), season, disc, total, part_marker_only)
