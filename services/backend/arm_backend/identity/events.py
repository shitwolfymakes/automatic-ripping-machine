"""The UI events for an identity change, and the store-then-emit step the
episode stage's callers share."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from arm_backend.identity.episode_stage import SourceOutcome, apply_episode_outcomes
from arm_backend.identity.pipeline import ResolveOutcome
from arm_backend.ws import WSHub
from arm_common import Job


async def emit_identity_resolved(
    session: AsyncSession,
    hub: WSHub,
    job: Job,
    resolved: ResolveOutcome,
    *,
    sources: dict[str, str],
) -> None:
    """Emit `job.identity_updated` (payload carries `sources`, a source id ->
    status map) plus one `track.updated` per track `resolved` says the
    resolver changed.

    Shared by the episode stage's apply path (`apply_outcomes_and_emit`) and
    the identity router's pin-clear, so every caller that runs
    the resolver and wants to tell the UI about it reports identically —
    `job.identity_updated` is emitted whenever the resolver changes
    anything, not just when the episode stage supplied new outcomes."""
    await hub.emit(
        topic="ripper.events",
        event_type="job.identity_updated",
        payload={"job_id": job.id, "sources": sources},
        job_id=job.id,
        session=session,
    )
    for track_id in sorted(resolved.track_ids):
        await hub.emit(
            topic="ripper.events",
            event_type="track.updated",
            payload={"track_id": track_id, "job_id": job.id},
            job_id=job.id,
            track_id=track_id,
            session=session,
        )


async def apply_outcomes_and_emit(
    session: AsyncSession,
    job: Job,
    outcomes: Sequence[SourceOutcome],
    hub: WSHub,
) -> ResolveOutcome:
    """Store `outcomes` (`apply_episode_outcomes`: put_source then resolve),
    commit, then emit via `emit_identity_resolved`, committing again. `job`
    must already be the freshly re-selected row the caller intends to write
    to.

    Shared by the background runner's apply phase and the identity router's
    `apply=True` path (controller ruling 2) so both commit and emit
    identically."""
    resolved = await apply_episode_outcomes(session, job, outcomes)
    await session.commit()
    await emit_identity_resolved(session, hub, job, resolved, sources={o.source_id: o.claims.status for o in outcomes})
    await session.commit()
    return resolved
