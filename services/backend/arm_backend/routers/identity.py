"""Identity, match, pin and episode-browse endpoints (design spec 2026-09-28-
identity-sources, section 7; plan Task 9).

`/identity` is a read-shaped view of the stored `identity_claims`.
`/identity/match` runs the episode stage on demand: `apply=False` is a pure
preview (nothing written); `apply=True` follows the background runner's
two-phase, no-stale-write discipline (controller ruling 2) -- compute with
show-id persistence off, then re-select the job fresh (`with_for_update` +
`populate_existing`) before writing, so a slow provider round-trip can never
clobber a concurrent PATCH/resolve with stale outcomes. `/identity/pin`
clears the operator's pinned episode source. `/identity/episodes` browses one
season of a provider's episode list, using the SAME providers (rate limits,
caches, TVDB login token) as the background stage (controller ruling 1).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt, require_writer
from arm_backend.db import get_session
from arm_backend.identity.episode_stage import SourceOutcome, StageOptions, compute_episode_claims, is_tv_candidate
from arm_backend.identity.http import SourceError, SourceMiss
from arm_backend.identity.ids import current_ids, merge_new_ids, resolve_show_ids
from arm_backend.identity.pipeline import resolve_job
from arm_backend.identity.proposals import claims_of, clear_pin, set_pin
from arm_backend.identity.sources.registry import EPISODE_SOURCE_BY_SETTING, EPISODE_TOLERANCE_S
from arm_backend.identity.stage_runner import EpisodeStageRunner, apply_outcomes_and_emit
from arm_backend.routers._params import JobIdParam
from arm_backend.routers.jobs import _get_hub, _get_stage_runner
from arm_backend.seeders import CONFIG_SINGLETON_ID
from arm_backend.ws import WSHub
from arm_common import Config, Job, User
from arm_common.models import Track
from arm_common.schemas.identity import SourceClaims
from arm_common.schemas.identity_api import (
    EpisodeListView,
    EpisodeSourceSetting,
    EpisodeSummary,
    IdentityView,
    MatchEntryView,
    MatchOutcomeView,
    MatchPreview,
    MatchRequest,
    SourceSummary,
    TrackIdentityView,
)

logger = logging.getLogger("arm_backend.routers.identity")

router = APIRouter(prefix="/api/jobs", tags=["identity"])

# The pin capability this PR uses (spec 7: "a named source sets pin.episode").
_EPISODE_PIN = "episode"


async def _get_job(db: AsyncSession, job_id: str) -> Job:
    job = (await db.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    return job


async def _get_tracks(db: AsyncSession, job_id: str) -> list[Track]:
    return list((await db.execute(select(Track).where(col(Track.job_id) == job_id))).scalars().all())


async def _get_config(db: AsyncSession) -> Config:
    return (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one()


def _identity_view(job: Job, tracks: Sequence[Track]) -> IdentityView:
    claims = claims_of(job)
    sources = {
        source_id: SourceSummary(
            status=c.status,
            detail=c.detail,
            run_at=c.run_at,
            suggestion=c.suggestion,
            inputs=c.inputs,
            alternatives=c.alternatives,
            extra=c.extra,
        )
        for source_id, c in claims.sources.items()
    }
    track_views = [
        TrackIdentityView(
            track_id=t.id,
            source_ref=t.source_ref,
            role=t.role,
            title=t.title,
            season=t.season,
            episode_number=t.episode_number,
            episode_number_end=t.episode_number_end,
            episode_name=t.episode_name,
            custom_filename=t.custom_filename,
            excluded=t.excluded,
            identity_provenance=t.identity_provenance,
            proposals={
                source_id: c.tracks[t.source_ref] for source_id, c in claims.sources.items() if t.source_ref in c.tracks
            },
        )
        for t in sorted(tracks, key=lambda t: t.index)
    ]
    return IdentityView(sources=sources, pin=claims.pin, tracks=track_views)


def _match_entries(claims: SourceClaims) -> list[MatchEntryView]:
    return [
        MatchEntryView(
            source_ref=ref,
            season=c.season,
            episode=c.episode,
            episode_end=c.episode_end,
            episode_name=c.episode_name,
            confidence=c.confidence,
        )
        for ref, c in claims.tracks.items()
        if c.episode is not None
    ]


def _outcome_view(source_id: str, claims: SourceClaims) -> MatchOutcomeView:
    return MatchOutcomeView(
        source_id=source_id,
        status=claims.status,
        detail=claims.detail,
        suggestion=claims.suggestion,
        coverage=claims.extra.get("coverage"),
        matches=_match_entries(claims),
        alternatives=claims.alternatives,
    )


@router.get("/{job_id}/identity", response_model=IdentityView)
async def get_identity(
    job_id: JobIdParam,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> IdentityView:
    job = await _get_job(db, job_id)
    tracks = await _get_tracks(db, job_id)
    return _identity_view(job, tracks)


@router.post("/{job_id}/identity/match", response_model=MatchPreview)
async def match_identity(
    job_id: JobIdParam,
    req: MatchRequest,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
    hub: WSHub = Depends(_get_hub),
    stage_runner: EpisodeStageRunner | None = Depends(_get_stage_runner),
) -> MatchPreview:
    job = await _get_job(db, job_id)
    tracks = await _get_tracks(db, job_id)
    if not is_tv_candidate(job, tracks):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job {job_id} is not a TV candidate",
        )
    if stage_runner is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="episode stage runner not available",
        )

    cfg = await _get_config(db)
    providers = stage_runner.providers(cfg)
    source_id = EPISODE_SOURCE_BY_SETTING[req.source] if req.source is not None else None
    opts = StageOptions(
        season=req.season,
        disc_number=req.disc_number,
        tolerance=req.tolerance if req.tolerance is not None else EPISODE_TOLERANCE_S,
        only_source=source_id,
        # Never persist a show id resolved during THIS compute onto the job
        # object we're about to re-select fresh (controller ruling 2) -- an
        # in-place mutation here, left on an attached object, is exactly the
        # stale-write autoflush hazard the background runner's two-phase
        # split exists to avoid.
        apply=False,
    )
    outcomes: list[SourceOutcome] = await compute_episode_claims(db, job, providers, cfg, opts)

    if not req.apply:
        return MatchPreview(outcomes=[_outcome_view(o.source_id, o.claims) for o in outcomes])

    fresh_job = (
        await db.execute(
            select(Job).where(col(Job.id) == job_id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one()
    merge_new_ids(fresh_job, current_ids(job))
    if source_id is not None:
        # `only_source` restricted compute to this one provider, so every
        # outcome here already belongs to it: the operator explicitly chose
        # this source, so its claims are no longer a suggestion the resolver
        # would otherwise ignore.
        for outcome in outcomes:
            outcome.claims.suggestion = False
        set_pin(fresh_job, _EPISODE_PIN, source_id)

    await apply_outcomes_and_emit(db, fresh_job, outcomes, hub)

    stored = claims_of(fresh_job).sources
    return MatchPreview(outcomes=[_outcome_view(o.source_id, stored.get(o.source_id, o.claims)) for o in outcomes])


@router.delete("/{job_id}/identity/pin", response_model=IdentityView)
async def clear_identity_pin(
    job_id: JobIdParam,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> IdentityView:
    job = await _get_job(db, job_id)
    clear_pin(job, _EPISODE_PIN)
    await resolve_job(db, job)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    tracks = await _get_tracks(db, job_id)
    return _identity_view(job, tracks)


@router.get("/{job_id}/identity/episodes", response_model=EpisodeListView)
async def browse_episodes(
    job_id: JobIdParam,
    source: EpisodeSourceSetting,
    season: int = Query(..., ge=0),
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
    stage_runner: EpisodeStageRunner | None = Depends(_get_stage_runner),
) -> EpisodeListView:
    job = await _get_job(db, job_id)
    if stage_runner is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="episode stage runner not available",
        )

    cfg = await _get_config(db)
    providers = stage_runner.providers(cfg)
    source_id = EPISODE_SOURCE_BY_SETTING[source]
    provider = {p.source_id: p for p in providers}[source_id]

    ids = await resolve_show_ids(job, [provider], persist=False)
    show_id = getattr(ids, provider.id_field, None)
    if not show_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no {source} show id known for job {job_id}",
        )
    try:
        episodes = await provider.season(show_id, season)
    except SourceMiss as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{source}: season {season} not found",
        ) from e
    except SourceError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{source}: {e}",
        ) from e

    return EpisodeListView(
        source_id=source_id,
        show_id=show_id,
        season=season,
        episodes=[
            EpisodeSummary(number=e.number, name=e.name, runtime_s=e.runtime_s, special=e.special) for e in episodes
        ],
    )
