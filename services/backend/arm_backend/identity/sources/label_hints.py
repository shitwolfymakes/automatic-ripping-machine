"""Volume-label disc hints (tier 4): season / disc number / disc total and a
cleaned search title, parsed from the ISO volume label.

Ported from neu arm/ripper/arm_matcher.py parse_label. Only trailing markers
count, and each needs an explicit S / D / P / DISC / SEASON prefix, so movie
titles that end in a number (APOLLO_13, BLADE_RUNNER_2049) yield no hint.
PART is deliberately not a disc marker: PART_2 is usually title content.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from arm_common import DiscType
from arm_common.schemas.identity import JobClaim, SourceClaims

from arm_backend.identity.sources.base import Capability, JobContext

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
# `\d*\b` (rather than the old bare `\w*`) requires SKU to be its own token,
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


def parse_label(raw: str) -> LabelHints:
    if not raw:
        return LabelHints("", None, None, None)
    # NFKC folds compatibility glyphs (e.g. "Blu-ray™" -> "Blu-rayTM") so the
    # Blu-ray-suffix strip below still matches after non-ASCII input.
    raw = unicodedata.normalize("NFKC", raw)
    s = raw.replace("_", " ")
    s = _ASPECT_RE.sub("", s)
    s = _SKU_RE.sub("", s)
    for suffix in _BLURAY_SUFFIXES:
        s = s.replace(suffix, "")
    s = s.replace(".", " ").rstrip()

    season: int | None = None
    disc: int | None = None
    total: int | None = None
    part_marker_only = False
    if m := _SEASON_DISC_RE.search(s):
        season, disc, s = _bounded(m.group(1), 0, _SEASON_MAX), _bounded(m.group(2), 1, _DISC_MAX), s[: m.start()]
    else:
        if m := _DISC_WORD_RE.search(s):
            disc, s = _WORD_NUMBERS[m.group(1).lower()], s[: m.start()]
        elif m := _DISC_RE.search(s):
            marker = m.group(1).upper()
            disc, s = _bounded(m.group(2), 1, _DISC_MAX), s[: m.start()]
            total = _bounded(m.group(3), 1, _DISC_MAX) if m.group(3) else None
            part_marker_only = marker == "P"
        if m := _SEASON_KEYWORD_RE.search(s) or _SEASON_RE.search(s):
            season, s = _bounded(m.group(1), 0, _SEASON_MAX), s[: m.start()]
            if season is not None:
                part_marker_only = False
    if total is not None and disc is not None and total < disc:
        total = None
    title = re.sub(r"\s+", " ", s.replace("-", " ")).strip().rstrip(" :,").lower()
    return LabelHints(title, season, disc, total, part_marker_only)


class LabelSource:
    id = "label"
    capability = Capability.DISC_HINT

    def applies_to(self, ctx: JobContext) -> str | None:
        if ctx.scan.disc_type not in (DiscType.DVD, DiscType.BLURAY):
            return "not a video disc"
        if not ctx.scan.volume_label:
            return "no volume label"
        return None

    def inputs(self, ctx: JobContext) -> dict[str, Any]:
        return {"volume_label": ctx.scan.volume_label or ""}

    def run(self, ctx: JobContext) -> SourceClaims:
        label = ctx.scan.volume_label or ""
        hints = parse_label(label)
        fields: dict[str, Any] = {}
        if hints.season is not None:
            fields["season"] = hints.season
        if hints.disc_number is not None:
            fields["disc_number"] = hints.disc_number
        if hints.disc_total is not None:
            fields["disc_total"] = hints.disc_total
        # A search-title hint is only worth proposing when parse_label actually
        # stripped a season/disc marker off the label — otherwise this is just
        # a cruder version of the dispatcher's own _normalize_volume_label
        # pass (which also strips NTSC/Blu-ray branding and keeps the year for
        # a filtered search), and running it first only risks a worse hit
        # ("THE_MATRIX_NTSC" -> "the matrix ntsc", "ALIEN_1979" -> "alien
        # 1979" instead of a year-filtered "alien"/1979).
        if (
            hints.title
            and not hints.part_marker_only
            and (hints.season is not None or hints.disc_number is not None or hints.disc_total is not None)
        ):
            fields["title"] = hints.title
        return SourceClaims(run_at=ctx.now, status="ok", inputs=self.inputs(ctx), job=JobClaim(**fields))


LABEL = LabelSource()
