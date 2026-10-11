"""Session-facing entry points for the identity core."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_common import Job, Track
from arm_common.schemas import ScanResult
from arm_common.schemas.identity import SourceClaims

from arm_backend.identity.proposals import claims_of, put_source
from arm_backend.identity.resolver import apply_resolution, resolve
from arm_backend.identity.sources.base import JobContext, Source
from arm_backend.identity.sources.registry import DEFAULT_RANKS, SOURCE_TIERS, HINT_SOURCES

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolveOutcome:
    changed: int
    track_ids: frozenset[str]


async def resolve_job(session: AsyncSession, job: Job) -> ResolveOutcome:
    """Apply every stored proposal to the job and its tracks. Idempotent;
    returns the number of attributes changed and which tracks changed."""
    tracks = list((await session.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all())
    changed_ids: set[str] = set()
    changed = apply_resolution(
        job, tracks, resolve(claims_of(job), tiers=SOURCE_TIERS, ranks=DEFAULT_RANKS), changed_track_ids=changed_ids
    )
    for track in tracks:
        session.add(track)
    session.add(job)
    await session.flush()
    if changed:
        logger.info("identity: resolved job_id=%s changed=%d", job.id, changed)
    return ResolveOutcome(changed=changed, track_ids=frozenset(changed_ids))


def _error_claims(source: Source, ctx: JobContext, e: Exception) -> SourceClaims:
    """An error entry carrying the inputs the source would have used, so
    put_source keeps the last good claims only when they are for the same inputs."""
    logger.warning("identity: source %s failed job_id=%s: %s", source.id, ctx.job.id, e)
    try:
        inputs = source.inputs(ctx)
    except Exception:
        inputs = {}
    return SourceClaims(run_at=ctx.now, status="error", inputs=inputs, detail=f"{type(e).__name__}: {e}"[:200])


def run_disc_hints(job: Job, scan: ScanResult, *, now: datetime) -> None:
    """Record every disc-hint source's proposals (or why it was skipped)."""
    ctx = JobContext(job=job, scan=scan, now=now)
    for source in HINT_SOURCES:
        try:
            reason = source.applies_to(ctx)
        except Exception as e:
            put_source(job, source.id, _error_claims(source, ctx, e))
            continue
        if reason is None:
            try:
                claims = source.run(ctx)
            except Exception as e:
                claims = _error_claims(source, ctx, e)
        else:
            claims = SourceClaims(run_at=now, status="skipped", detail=reason)
        put_source(job, source.id, claims)


def hint_title(job: Job) -> str | None:
    """The cleaned search title from the best-ranked disc-hint source, if any."""
    sources = claims_of(job).sources
    for source in HINT_SOURCES:
        entry = sources.get(source.id)
        if entry is not None and entry.status == "ok" and entry.job.title:
            return entry.job.title
    return None


def hint_is_tv(job: Job) -> bool:
    """True when any ok disc-hint source proposed a `season` — the hint title
    is then TV-shaped (a season/box-set disc) and should be searched TMDb-TV
    first, not movie-first (a movie label ending in a season-shaped number,
    e.g. a real season disc, must not be mismatched to TMDb's top movie hit)."""
    sources = claims_of(job).sources
    for source in HINT_SOURCES:
        entry = sources.get(source.id)
        if (
            entry is not None
            and entry.status == "ok"
            and "season" in entry.job.model_fields_set
            and entry.job.season is not None
        ):
            return True
    return False
