"""Volume-label disc hints (tier 4): season / disc number / disc total and a
cleaned search title, parsed from the ISO volume label.

Ported from neu arm/ripper/arm_matcher.py parse_label. Only trailing markers
count, and each needs an explicit S / D / P / DISC / SEASON prefix, so movie
titles that end in a number (APOLLO_13, BLADE_RUNNER_2049) yield no hint.
PART is deliberately not a disc marker: PART_2 is usually title content.
"""

from __future__ import annotations

import re
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
_DISC_RE = re.compile(r"[\s-](?:P|D|DISC)[\s-]?(\d+)(?:[\s-]OF[\s-]?(\d+))?$", re.IGNORECASE)
_SEASON_KEYWORD_RE = re.compile(r"[\s-]SEASON[\s-]?(\d+)$", re.IGNORECASE)
_SEASON_RE = re.compile(r"[\s-]S(\d+)$", re.IGNORECASE)
# Bounded space run: an unbounded ` *` before SKU backtracks polynomially (ReDoS).
_SKU_RE = re.compile(r" {0,4}SKU\w*", re.IGNORECASE)
_ASPECT_RE = re.compile(r"\b16[xX]9\b")
_BLURAY_SUFFIXES = (" - Blu-rayTM", " Blu-rayTM", " - BLU-RAYTM", " - BLU-RAY", " - Blu-ray", " Blu-ray", " BLU-RAY")


@dataclass(frozen=True)
class LabelHints:
    title: str
    season: int | None
    disc_number: int | None
    disc_total: int | None


def parse_label(raw: str) -> LabelHints:
    if not raw:
        return LabelHints("", None, None, None)
    s = raw.replace("_", " ")
    s = _ASPECT_RE.sub("", s)
    s = _SKU_RE.sub("", s)
    for suffix in _BLURAY_SUFFIXES:
        s = s.replace(suffix, "")
    s = s.replace(".", " ").rstrip()

    season: int | None = None
    disc: int | None = None
    total: int | None = None
    if m := _SEASON_DISC_RE.search(s):
        season, disc, s = int(m.group(1)), int(m.group(2)), s[: m.start()]
    else:
        if m := _DISC_WORD_RE.search(s):
            disc, s = _WORD_NUMBERS[m.group(1).lower()], s[: m.start()]
        elif m := _DISC_RE.search(s):
            disc, s = int(m.group(1)), s[: m.start()]
            total = int(m.group(2)) if m.group(2) else None
        if m := _SEASON_KEYWORD_RE.search(s) or _SEASON_RE.search(s):
            season, s = int(m.group(1)), s[: m.start()]
    if total is not None and disc is not None and total < disc:
        total = None
    title = re.sub(r"\s+", " ", s.replace("-", " ")).strip().rstrip(" :,").lower()
    return LabelHints(title, season, disc, total)


class LabelSource:
    id = "label"
    capability = Capability.DISC_HINT

    def applies_to(self, ctx: JobContext) -> str | None:
        if ctx.scan.disc_type not in (DiscType.DVD, DiscType.BLURAY):
            return "not a video disc"
        if not ctx.scan.volume_label:
            return "no volume label"
        return None

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
        if hints.title:
            fields["title"] = hints.title
        return SourceClaims(run_at=ctx.now, status="ok", inputs={"volume_label": label}, job=JobClaim(**fields))


LABEL = LabelSource()
