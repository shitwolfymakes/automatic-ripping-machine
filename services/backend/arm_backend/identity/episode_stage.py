"""The episode stage (design spec 5, 6.2, 6.3, 9): match a TV disc's titles
against each ranked provider's episode list and record the result as one
tier-3 `SourceClaims` per provider.

`compute_episode_claims` only reads: it never adds to the session or writes
the job, except that `resolve_show_ids` caches newly found show ids on the job
when `opts.apply` is set. `run_episode_stage` stores every outcome with
`put_source`, then runs the resolver; the caller commits.

A result the stage is not sure of (ambiguous positions, low coverage, low
confidence, two seasons that fit about equally, nominal broadcast-slot
runtimes) is stored with `suggestion=True`, which the resolver never applies.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_common import Config, Job, Track, TrackKind
from arm_common.enums import MediaType, TrackRole
from arm_common.schemas import ExternalIds
from arm_common.schemas.identity import JobClaim, SourceClaims, TrackClaim

from arm_backend.identity.episodes.continuity import SiblingDisc, align_runs, rank_seasons, start_anchor
from arm_backend.identity.episodes.matcher import _eff_tol
from arm_backend.identity.episodes.model import Episode, MatchResult, TitleIn
from arm_backend.identity.episodes.providers.base import EpisodeListProvider
from arm_backend.identity.http import SourceError, SourceMiss
from arm_backend.identity.ids import current_ids, resolve_show_ids
from arm_backend.identity.pipeline import ResolveOutcome, resolve_job
from arm_backend.identity.proposals import claims_of, put_source
from arm_backend.identity.sources.registry import (
    COVERAGE_STOP,
    DEFAULT_EPISODE_SOURCES,
    EPISODE_AUTO_APPLY,
    EPISODE_SOURCE_BY_SETTING,
    EPISODE_TOLERANCE_S,
    MAX_SEASON_SCAN,
)

logger = logging.getLogger(__name__)

# Nominal runtimes: a provider listing every episode at a whole number of
# 5-minute broadcast slots (e.g. TVmaze's 60 min for a 44-minute episode).
NOMINAL_SLOT_S = 300
# Suggestion thresholds (C2).
MIN_COVERAGE = 0.5
MIN_MEAN_CONFIDENCE = 0.4
NEAR_TIE_COST_RATIO = 0.1

_EPISODE_SOURCE_IDS = frozenset(EPISODE_SOURCE_BY_SETTING.values())


@dataclass(frozen=True)
class StageOptions:
    season: int | None = None
    disc_number: int | None = None
    tolerance: int = EPISODE_TOLERANCE_S
    only_source: str | None = None
    apply: bool = True


@dataclass(frozen=True)
class SourceOutcome:
    source_id: str
    claims: SourceClaims
    result: MatchResult | None


@dataclass(frozen=True)
class _SeasonFit:
    result: MatchResult
    nominal: bool


def is_tv_candidate(job: Job, tracks: Sequence[Track]) -> bool:
    """Spec 5 gate: the job is TV, or any track is already an episode."""
    return job.media_type == MediaType.TV or any(t.role == TrackRole.EPISODE for t in tracks)


def _length(track: Track) -> int | None:
    return track.duration_seconds or track.expected_duration_seconds or None


def _eligible(tracks: Sequence[Track]) -> list[TitleIn]:
    """Selected video titles with a length whose role is unknown or episode
    (C6). A role this stage itself set on an earlier run (provenance is an
    episode source, e.g. `extra` for a skipped title) does not count as known,
    so a re-run can still place that title."""
    out: list[TitleIn] = []
    for track in sorted(tracks, key=lambda t: t.index):
        if track.kind != TrackKind.VIDEO_TITLE or track.excluded:
            continue
        role_source = (track.identity_provenance or {}).get("role")
        if track.role not in (None, TrackRole.EPISODE) and role_source not in _EPISODE_SOURCE_IDS:
            continue
        length = _length(track)
        if length:
            out.append(TitleIn(ref=track.source_ref, seconds=length))
    return out


def _ordered_providers(
    job: Job, providers: Sequence[EpisodeListProvider], only_source: str | None
) -> list[EpisodeListProvider]:
    by_id = {p.source_id: p for p in providers}
    order = [EPISODE_SOURCE_BY_SETTING[s] for s in DEFAULT_EPISODE_SOURCES if s in EPISODE_SOURCE_BY_SETTING]
    ordered = [by_id[s] for s in order if s in by_id]
    pinned = claims_of(job).pin.get("episode")
    if pinned is not None and any(p.source_id == pinned for p in ordered):
        ordered = sorted(ordered, key=lambda p: p.source_id != pinned)
    if only_source is not None:
        ordered = [p for p in ordered if p.source_id == only_source]
    return ordered


async def _job_tracks(session: AsyncSession, job: Job) -> list[Track]:
    return list((await session.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all())


async def _sibling_rows(session: AsyncSession, job: Job) -> list[tuple[Job, list[Track]]]:
    """Other TV jobs with the same title, with their tracks. Season and shared
    show ids are checked per season / provider by `_siblings`."""
    if not job.title:
        return []
    stmt = select(Job).where(col(Job.title) == job.title, col(Job.media_type) == MediaType.TV)
    jobs = [j for j in (await session.execute(stmt)).scalars().all() if j.id != job.id]
    if not jobs:
        return []
    tracks = (await session.execute(select(Track).where(col(Track.job_id).in_([j.id for j in jobs])))).scalars().all()
    return [(j, [t for t in tracks if t.job_id == j.id]) for j in jobs]


def _shares_id(ids: ExternalIds, other: ExternalIds) -> bool:
    theirs = other.model_dump(exclude_none=True)
    return any(value and theirs.get(key) == value for key, value in ids.model_dump(exclude_none=True).items())


def _siblings(rows: Sequence[tuple[Job, list[Track]]], ids: ExternalIds, season: int) -> list[SiblingDisc]:
    """Sibling discs of the same show (a shared non-empty external id) and
    season, with every episode number their resolved tracks hold."""
    out: list[SiblingDisc] = []
    for sibling, tracks in rows:
        if not _shares_id(ids, current_ids(sibling)):
            continue
        if sibling.season != season and not any(t.season == season for t in tracks):
            continue
        numbers: set[int] = set()
        for t in tracks:
            track_season = t.season if t.season is not None else sibling.season
            if track_season != season or t.episode_number is None:
                continue
            end = max(t.episode_number_end or t.episode_number, t.episode_number)
            numbers.update(range(t.episode_number, end + 1))
        out.append(SiblingDisc(sibling.disc_number, frozenset(numbers)))
    return out


def _nominal(remaining: Sequence[Episode], titles: Sequence[TitleIn], tolerance: int) -> bool:
    """C4: every known runtime is a whole number of broadcast slots, and fewer
    than half the titles fit any of them."""
    known = {e.runtime_s for e in remaining if e.runtime_s}
    if not known or any(rt % NOMINAL_SLOT_S for rt in known):
        return False
    fitting = sum(1 for t in titles if any(abs(t.seconds - rt) <= _eff_tol(rt, tolerance) for rt in known))
    return fitting < len(titles) / 2


def _mean_cost(result: MatchResult) -> float:
    return result.cost / max(1, len(result.matches))


def _near_tie(first: MatchResult, second: MatchResult) -> bool:
    if first.coverage != second.coverage or len(first.matches) != len(second.matches):
        return False
    a, b = _mean_cost(first), _mean_cost(second)
    return abs(a - b) <= NEAR_TIE_COST_RATIO * max(a, b)


async def _fit_season(
    provider: EpisodeListProvider,
    show_id: str,
    season: int,
    *,
    titles: Sequence[TitleIn],
    rows: Sequence[tuple[Job, list[Track]]],
    ids: ExternalIds,
    disc_number: int | None,
    disc_total: int | None,
    tolerance: int,
) -> _SeasonFit | None:
    try:
        episodes = await provider.season(show_id, season)
    except SourceMiss:
        return None
    siblings = _siblings(rows, ids, season)
    remaining, anchor = start_anchor(
        episodes, disc_number=disc_number, disc_total=disc_total, n_titles=len(titles), siblings=siblings
    )
    nominal = _nominal(remaining, titles, tolerance)
    if nominal:
        remaining = [replace(e, runtime_s=None) for e in remaining]
    claimed = frozenset().union(*(s.episodes for s in siblings)) if siblings else frozenset()
    result = align_runs(titles, remaining, claimed=claimed, tolerance=tolerance, anchor=anchor)
    return _SeasonFit(result, nominal)


async def _match(
    provider: EpisodeListProvider,
    job: Job,
    cfg: Config,
    opts: StageOptions,
    *,
    titles: Sequence[TitleIn],
    rows: Sequence[tuple[Job, list[Track]]],
    now: datetime,
    inputs: dict[str, Any],
) -> SourceOutcome:
    """One provider's outcome. Fills `inputs` as soon as they are known so an
    error raised later still carries them (C7)."""
    source_id = provider.source_id
    reason = provider.configured(cfg)
    if reason is not None:
        return SourceOutcome(source_id, SourceClaims(run_at=now, status="skipped", detail=reason), None)
    if provider.http.backing_off():
        return SourceOutcome(source_id, SourceClaims(run_at=now, status="skipped", detail="backing off"), None)
    ids = await resolve_show_ids(job, [provider], persist=opts.apply)
    show_id = getattr(ids, provider.id_field, None)
    if not show_id:
        return SourceOutcome(source_id, SourceClaims(run_at=now, status="miss", detail="show not found"), None)

    known_season = opts.season if opts.season is not None else job.season
    disc_number = opts.disc_number if opts.disc_number is not None else job.disc_number
    inputs.update(show_id=show_id, season=known_season, disc_number=disc_number, tolerance=opts.tolerance)

    seasons = [known_season] if known_season is not None else (await provider.seasons(show_id))[:MAX_SEASON_SCAN]
    fits: dict[int, _SeasonFit] = {}
    for season in seasons:
        fit = await _fit_season(
            provider,
            show_id,
            season,
            titles=titles,
            rows=rows,
            ids=ids,
            disc_number=disc_number,
            disc_total=job.disc_total,
            tolerance=opts.tolerance,
        )
        if fit is not None:
            fits[season] = fit

    ranked = rank_seasons({s: f.result for s, f in fits.items()})
    if not ranked or not ranked[0][1].matches:
        claims = SourceClaims(run_at=now, status="miss", detail="no episodes matched", inputs=dict(inputs))
        return SourceOutcome(source_id, claims, ranked[0][1] if ranked else None)

    season, result = ranked[0]
    nominal = fits[season].nominal
    near_tie = len(ranked) > 1 and _near_tie(result, ranked[1][1])
    mean_conf = sum(m.confidence for m in result.matches) / len(result.matches)
    suggestion = (
        (not EPISODE_AUTO_APPLY)
        or result.ambiguous
        or result.coverage < MIN_COVERAGE
        or mean_conf < MIN_MEAN_CONFIDENCE
        or near_tie
        or nominal
    )

    tracks: dict[str, TrackClaim] = {
        m.ref: TrackClaim(
            role=TrackRole.EPISODE,
            season=season,
            episode=m.episode,
            episode_end=m.episode_end,
            episode_name=m.name or f"Episode {m.episode}",
            confidence=m.confidence,
        )
        for m in result.matches
    }
    for ref in (*result.skipped, *result.play_all):
        tracks[ref] = TrackClaim(role=TrackRole.EXTRA)

    inputs["nominal_runtimes"] = nominal
    claims = SourceClaims(
        run_at=now,
        status="ok",
        suggestion=suggestion,
        inputs=dict(inputs),
        job=JobClaim(season=season) if known_season is None else JobClaim(),
        tracks=tracks,
        alternatives=[
            {"season": s, "coverage": r.coverage, "matches": len(r.matches)} for s, r in ranked[1:] if r.matches
        ],
        extra={
            "coverage": result.coverage,
            "ambiguous": result.ambiguous,
            "near_tie": near_tie,
            "play_all": list(result.play_all),
            "skipped": list(result.skipped),
        },
    )
    return SourceOutcome(source_id, claims, result)


def _error(job: Job, source_id: str, e: Exception, inputs: dict[str, Any], now: datetime) -> SourceOutcome:
    """An error entry carrying the request inputs; `nominal_runtimes` (known
    only after a fetch) is carried from the last stored entry so put_source
    keeps the last good claims exactly when the request is unchanged (C7)."""
    if inputs:
        previous = claims_of(job).sources.get(source_id)
        inputs = {**inputs, "nominal_runtimes": previous.inputs.get("nominal_runtimes") if previous else None}
    claims = SourceClaims(run_at=now, status="error", detail=f"{type(e).__name__}: {e}", inputs=inputs)
    return SourceOutcome(source_id, claims, None)


def _stops(outcome: SourceOutcome) -> bool:
    claims = outcome.claims
    return (
        claims.status == "ok"
        and not claims.suggestion
        and outcome.result is not None
        and outcome.result.coverage >= COVERAGE_STOP
    )


async def compute_episode_claims(
    session: AsyncSession,
    job: Job,
    providers: Sequence[EpisodeListProvider],
    cfg: Config,
    opts: StageOptions,
) -> list[SourceOutcome]:
    """Every tried provider's outcome, in the order tried. Stops after the
    first confident, well-covered result (spec 5); later providers are not
    called. One provider failing never fails the stage (spec 9)."""
    titles = _eligible(await _job_tracks(session, job))
    rows = await _sibling_rows(session, job)
    now = datetime.now(UTC)
    outcomes: list[SourceOutcome] = []
    for provider in _ordered_providers(job, providers, opts.only_source):
        inputs: dict[str, Any] = {}
        try:
            outcome = await _match(provider, job, cfg, opts, titles=titles, rows=rows, now=now, inputs=inputs)
        except SourceError as e:
            logger.warning("episode stage: source %s failed job_id=%s: %s", provider.source_id, job.id, e)
            outcome = _error(job, provider.source_id, e, inputs, now)
        except Exception as e:
            logger.exception("episode stage: source %s raised job_id=%s", provider.source_id, job.id)
            outcome = _error(job, provider.source_id, e, inputs, now)
        outcomes.append(outcome)
        if _stops(outcome):
            break
    return outcomes


async def run_episode_stage(
    session: AsyncSession,
    job: Job,
    providers: Sequence[EpisodeListProvider],
    cfg: Config,
    opts: StageOptions,
) -> tuple[list[SourceOutcome], ResolveOutcome]:
    """Compute, store every outcome, resolve, flush. The caller commits."""
    outcomes = await compute_episode_claims(session, job, providers, cfg, opts)
    for outcome in outcomes:
        put_source(job, outcome.source_id, outcome.claims)
    resolved = await resolve_job(session, job)
    return outcomes, resolved
