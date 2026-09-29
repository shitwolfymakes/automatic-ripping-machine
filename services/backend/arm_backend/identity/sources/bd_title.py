"""Blu-ray BDMT disc-title hints (tier 4): the studio's disc name and set
position, sent by the ripper on ScanResult.bd_meta."""

from __future__ import annotations

from typing import Any

from arm_common import DiscType
from arm_common.schemas.identity import JobClaim, SourceClaims

from arm_backend.identity.sources.base import Capability, JobContext
from arm_backend.identity.sources.label_hints import parse_label


class BdTitleSource:
    id = "bd_title"
    capability = Capability.DISC_HINT

    def applies_to(self, ctx: JobContext) -> str | None:
        if ctx.scan.disc_type != DiscType.BLURAY:
            return "not a Blu-ray"
        if ctx.scan.bd_meta is None:
            return "no BDMT disc title"
        return None

    def run(self, ctx: JobContext) -> SourceClaims:
        meta = ctx.scan.bd_meta
        assert meta is not None  # applies_to guarantees it
        hints = parse_label(meta.name)
        fields: dict[str, Any] = {}
        if hints.season is not None:
            fields["season"] = hints.season
        disc = meta.set_number if meta.set_number is not None else hints.disc_number
        total = meta.num_sets if meta.num_sets is not None else hints.disc_total
        if disc is not None:
            fields["disc_number"] = disc
        if total is not None:
            fields["disc_total"] = total
        if hints.title:
            fields["title"] = hints.title
        inputs = {k: v for k, v in meta.model_dump().items() if v is not None}
        return SourceClaims(run_at=ctx.now, status="ok", inputs=inputs, job=JobClaim(**fields))


BD_TITLE = BdTitleSource()
