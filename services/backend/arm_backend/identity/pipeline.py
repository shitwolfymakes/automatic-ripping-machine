"""Session-facing entry points for the identity core."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_common import Config, Job, JobStatus, Track
from arm_common.schemas import ScanResult
from arm_common.schemas.identity import SourceClaims

from arm_backend.identity.proposals import claims_of, put_source, set_unsure
from arm_backend.identity.resolver import apply_resolution, resolve
from arm_backend.identity.sources.base import JobContext, Source
from arm_backend.identity.sources.registry import SOURCE_TIERS, HINT_SOURCES, disabled_source_ids, source_ranks

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolveOutcome:
    changed: int
    track_ids: frozenset[str]


async def resolve_job(session: AsyncSession, job: Job) -> ResolveOutcome:
    """Apply every stored proposal to the job and its tracks, ranked and
    filtered by the operator's source settings. Idempotent; returns the
    number of attributes changed and which tracks changed."""
    cfg = (await session.execute(select(Config).limit(1))).scalars().first()
    tracks = list((await session.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all())
    changed_ids: set[str] = set()
    resolution = resolve(claims_of(job), tiers=SOURCE_TIERS, ranks=source_ranks(cfg), disabled=disabled_source_ids(cfg))
    changed = apply_resolution(job, tracks, resolution, changed_track_ids=changed_ids)
    # A guess flips to sure (or back) only through the resolver, so the flag
    # counts as a change: callers emit `job.identity_updated` on it.
    if set_unsure(job, resolution.episode_unsure):
        changed += 1
        if not resolution.episode_unsure and job.status == JobStatus.AWAITING_REVIEW and job.wait_start_time:
            # The guess held the countdown, which kept running underneath:
            # restart it so the now-confident disc does not auto-rip at once.
            job.wait_start_time = datetime.now(timezone.utc)
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


def run_disc_hints(job: Job, scan: ScanResult, *, now: datetime, sources: Sequence[Source] = HINT_SOURCES) -> None:
    """Record every disc-hint source's proposals (or why it was skipped)."""
    ctx = JobContext(job=job, scan=scan, now=now)
    for source in sources:
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
