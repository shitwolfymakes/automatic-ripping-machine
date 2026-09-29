"""Session-facing entry points for the identity core."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_common import Job, Track

from arm_backend.identity.proposals import claims_of
from arm_backend.identity.resolver import apply_resolution, resolve
from arm_backend.identity.sources.registry import DEFAULT_RANKS, SOURCE_TIERS

logger = logging.getLogger(__name__)


async def resolve_job(session: AsyncSession, job: Job) -> int:
    """Apply every stored proposal to the job and its tracks. Idempotent;
    returns the number of attributes changed."""
    tracks = list((await session.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all())
    changed = apply_resolution(job, tracks, resolve(claims_of(job), tiers=SOURCE_TIERS, ranks=DEFAULT_RANKS))
    for track in tracks:
        session.add(track)
    session.add(job)
    await session.flush()
    if changed:
        logger.info("identity: resolved job_id=%s changed=%d", job.id, changed)
    return changed
