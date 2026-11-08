"""Readers of the disc-hint claims stored on a job."""

from __future__ import annotations

from collections.abc import Sequence

from arm_common import Job

from arm_backend.identity.proposals import claims_of
from arm_backend.identity.sources.base import Source
from arm_backend.identity.sources.registry import HINT_SOURCES


def hint_title(job: Job, sources: Sequence[Source] = HINT_SOURCES) -> str | None:
    """The cleaned search title from the best-ranked disc-hint source, if any."""
    claim_sources = claims_of(job).sources
    for source in sources:
        entry = claim_sources.get(source.id)
        if entry is not None and entry.status == "ok" and entry.job.title:
            return entry.job.title
    return None


def hint_season(job: Job, sources: Sequence[Source] = HINT_SOURCES) -> int | None:
    """The season of the first ok disc-hint source, in source order, that
    proposed one; None when none did."""
    claim_sources = claims_of(job).sources
    for source in sources:
        entry = claim_sources.get(source.id)
        if (
            entry is not None
            and entry.status == "ok"
            and "season" in entry.job.model_fields_set
            and entry.job.season is not None
        ):
            return entry.job.season
    return None


def hint_is_tv(job: Job, sources: Sequence[Source] = HINT_SOURCES) -> bool:
    """True when any ok disc-hint source proposed a `season` — the hint title
    is then TV-shaped (a season/box-set disc) and should be searched TMDb-TV
    first, not movie-first (a movie label ending in a season-shaped number,
    e.g. a real season disc, must not be mismatched to TMDb's top movie hit)."""
    return hint_season(job, sources) is not None
