"""ISO file-name disc hints (tier 4): the ripped file's name, which collectors
often write as `Title_(Year)_[tags].iso`. Proposes a cleaned search title, the
season / disc markers and a bracketed release year.
"""

from __future__ import annotations

import re
from typing import Any

from arm_common.schemas.identity import JobClaim, SourceClaims

from arm_backend.identity.sources.base import Capability, JobContext
from arm_backend.identity.sources.label_parser import LabelHints, parse_label
from arm_backend.identity.sources.year_hint import bracketed_year

_BRACKET_GROUP_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)")


def parse_iso_name(name: str, *, max_year: int) -> tuple[LabelHints, int | None]:
    """The label hints of `name` with its bracketed tags removed, and its bracketed year."""
    return parse_label(_BRACKET_GROUP_RE.sub(" ", name)), bracketed_year(name, max_year=max_year)


class IsoNameSource:
    id = "iso_name"
    capability = Capability.DISC_HINT

    def applies_to(self, ctx: JobContext) -> str | None:
        if not ctx.source_name:
            return "not an ISO rip"
        return None

    def inputs(self, ctx: JobContext) -> dict[str, Any]:
        return {"source_name": ctx.source_name or ""}

    def run(self, ctx: JobContext) -> SourceClaims:
        hints, year = parse_iso_name(ctx.source_name or "", max_year=ctx.now.year + 1)
        fields: dict[str, Any] = {}
        if hints.season is not None:
            fields["season"] = hints.season
        if hints.disc_number is not None:
            fields["disc_number"] = hints.disc_number
        if hints.disc_total is not None:
            fields["disc_total"] = hints.disc_total
        if hints.title and not hints.part_marker_only:
            fields["title"] = hints.title
        if year is not None:
            fields["year"] = year
        return SourceClaims(run_at=ctx.now, status="ok", inputs=self.inputs(ctx), job=JobClaim(**fields))


ISO_NAME = IsoNameSource()
