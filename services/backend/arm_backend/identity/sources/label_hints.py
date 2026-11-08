"""Volume-label disc hints (tier 4): season / disc number / disc total and a
cleaned search title, parsed from the ISO volume label by
`label_parser.parse_label`.
"""

from __future__ import annotations

from typing import Any

from arm_common import DiscType
from arm_common.schemas.identity import JobClaim, SourceClaims

from arm_backend.identity.sources.base import Capability, JobContext
from arm_backend.identity.sources.label_parser import parse_label


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
        # a cruder version of the dispatcher's volume-label pass
        # (`metadata.volume_label.normalize_volume_label`, which also strips
        # NTSC/Blu-ray branding and keeps the year for a filtered search), and
        # running it first only risks a worse hit
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
