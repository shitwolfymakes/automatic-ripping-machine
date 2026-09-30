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

from arm_common import Config, Job, JobStatus, Track, TrackKind
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
# Jobs that never produced a disc's episodes; they are not siblings.
_DEAD_STATUSES = frozenset({JobStatus.FAILED, JobStatus.ABANDONED})


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
    sibling_conflict: bool


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
    """Other live TV jobs with the same title, with their tracks. Season and
    shared show ids are checked per season / provider by `_siblings`. Failed
    and abandoned jobs never hold episodes."""
    if not job.title:
        return []
    stmt = select(Job).where(col(Job.title) == job.title, col(Job.media_type) == MediaType.TV)
    jobs = [
        j for j in (await session.execute(stmt)).scalars().all() if j.id != job.id and j.status not in _DEAD_STATUSES
    ]
    if not jobs:
        return []
    tracks = (await session.execute(select(Track).where(col(Track.job_id).in_([j.id for j in jobs])))).scalars().all()
    return [(j, [t for t in tracks if t.job_id == j.id]) for j in jobs]


def _shares_id(ids: ExternalIds, other: ExternalIds) -> bool:
    theirs = other.model_dump(exclude_none=True)
    return any(value and theirs.get(key) == value for key, value in ids.model_dump(exclude_none=True).items())


def _held_numbers(sibling: Job, tracks: Sequence[Track], season: int) -> frozenset[int]:
    numbers: set[int] = set()
    for t in tracks:
        track_season = t.season if t.season is not None else sibling.season
        if track_season != season or t.episode_number is None:
            continue
        end = max(t.episode_number_end or t.episode_number, t.episode_number)
        numbers.update(range(t.episode_number, end + 1))
    return frozenset(numbers)


def _siblings(
    rows: Sequence[tuple[Job, list[Track]]], ids: ExternalIds, season: int, disc_number: int | None
) -> tuple[list[SiblingDisc], bool]:
    """Sibling discs of the same show (a shared non-empty external id) and
    season, with every episode number their resolved tracks hold.

    Only a sibling that is provably a different disc (both disc numbers known
    and different) claims its episodes. A sibling holding episodes that may be
    this same disc (an earlier rip of it, or either disc number unknown) is a
    conflict: returned as True so the result becomes a suggestion."""
    out: list[SiblingDisc] = []
    conflict = False
    for sibling, tracks in rows:
        if not _shares_id(ids, current_ids(sibling)):
            continue
        if sibling.season != season and not any(t.season == season for t in tracks):
            continue
        numbers = _held_numbers(sibling, tracks, season)
        if not numbers:
            continue
        if disc_number is not None and sibling.disc_number is not None and sibling.disc_number != disc_number:
            out.append(SiblingDisc(sibling.disc_number, numbers))
        else:
            conflict = True
    return out, conflict


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


@dataclass(frozen=True)
class _Request:
    """One provider's matching inputs."""

    show_id: str
    ids: ExternalIds
    titles: Sequence[TitleIn]
    rows: Sequence[tuple[Job, list[Track]]]
    disc_number: int | None
    disc_total: int | None
    tolerance: int


async def _fit_season(provider: EpisodeListProvider, req: _Request, season: int) -> _SeasonFit | None:
    try:
        episodes = await provider.season(req.show_id, season)
    except SourceMiss:
        return None
    siblings, conflict = _siblings(req.rows, req.ids, season, req.disc_number)
    remaining, anchor = start_anchor(
        episodes,
        disc_number=req.disc_number,
        disc_total=req.disc_total,
        n_titles=len(req.titles),
        siblings=siblings,
    )
    nominal = _nominal(remaining, req.titles, req.tolerance)
    if nominal:
        remaining = [replace(e, runtime_s=None) for e in remaining]
    claimed = frozenset().union(*(s.episodes for s in siblings)) if siblings else frozenset()
    result = align_runs(req.titles, remaining, claimed=claimed, tolerance=req.tolerance, anchor=anchor)
    return _SeasonFit(result, nominal, conflict)


async def _pick_season(
    provider: EpisodeListProvider, req: _Request, seasons: Sequence[int]
) -> tuple[int, _SeasonFit, list[tuple[int, MatchResult]]] | None:
    """The best-ranked season's fit, with the full ranking; None when no
    season could be fetched."""
    fits: dict[int, _SeasonFit] = {}
    for season in seasons:
        fit = await _fit_season(provider, req, season)
        if fit is not None:
            fits[season] = fit
    ranked = rank_seasons({s: f.result for s, f in fits.items()})
    if not ranked:
        return None
    season = ranked[0][0]
    return season, fits[season], ranked


def _ok_claims(
    season: int,
    fit: _SeasonFit,
    ranked: Sequence[tuple[int, MatchResult]],
    *,
    scanned: bool,
    inputs: dict[str, Any],
    now: datetime,
) -> SourceClaims:
    result = fit.result
    near_tie = len(ranked) > 1 and _near_tie(result, ranked[1][1])
    mean_conf = sum(m.confidence for m in result.matches) / len(result.matches)
    suggestion = (
        (not EPISODE_AUTO_APPLY)
        or result.ambiguous
        or result.coverage < MIN_COVERAGE
        or mean_conf < MIN_MEAN_CONFIDENCE
        or near_tie
        or fit.nominal
        or fit.sibling_conflict
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
    return SourceClaims(
        run_at=now,
        status="ok",
        suggestion=suggestion,
        inputs={**inputs, "nominal_runtimes": fit.nominal},
        job=JobClaim(season=season) if scanned else JobClaim(),
        tracks=tracks,
        alternatives=[
            {"season": s, "coverage": r.coverage, "matches": len(r.matches)} for s, r in ranked[1:] if r.matches
        ],
        extra={
            "coverage": result.coverage,
            "ambiguous": result.ambiguous,
            "near_tie": near_tie,
            "sibling_conflict": fit.sibling_conflict,
            "play_all": list(result.play_all),
            "skipped": list(result.skipped),
        },
    )


def _known_season(job: Job, opts: StageOptions) -> int | None:
    """The season to match against without scanning: the option, else the
    job's season unless this stage itself set it (F1). A season an episode
    source picked by scanning stays a scan, so re-runs keep proposing it
    and their inputs stay the same."""
    if opts.season is not None:
        return opts.season
    if (job.identity_provenance or {}).get("season") in _EPISODE_SOURCE_IDS:
        return None
    return job.season


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

    known_season = _known_season(job, opts)
    disc_number = opts.disc_number if opts.disc_number is not None else job.disc_number
    inputs.update(show_id=show_id, season=known_season, disc_number=disc_number, tolerance=opts.tolerance)

    if known_season is not None:
        seasons = [known_season]
    else:
        try:
            seasons = (await provider.seasons(show_id))[:MAX_SEASON_SCAN]
        except SourceMiss:
            # A stale cached show id: the provider no longer knows the show.
            claims = SourceClaims(run_at=now, status="miss", detail="show not found", inputs=dict(inputs))
            return SourceOutcome(source_id, claims, None)

    req = _Request(show_id, ids, titles, rows, disc_number, job.disc_total, opts.tolerance)
    picked = await _pick_season(provider, req, seasons)
    if picked is None or not picked[1].result.matches:
        claims = SourceClaims(run_at=now, status="miss", detail="no episodes matched", inputs=dict(inputs))
        return SourceOutcome(source_id, claims, picked[1].result if picked else None)
    season, fit, ranked = picked
    claims = _ok_claims(season, fit, ranked, scanned=known_season is None, inputs=inputs, now=now)
    return SourceOutcome(source_id, claims, fit.result)


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


async def apply_episode_outcomes(session: AsyncSession, job: Job, outcomes: Sequence[SourceOutcome]) -> ResolveOutcome:
    """Store every outcome with `put_source`, then resolve. Flushes; the
    caller commits.

    Split out from `run_episode_stage` (Task 8 fix round 1) so a caller that
    runs `compute_episode_claims` off a snapshot taken before a slow network
    round-trip can re-select `job` fresh immediately before this call —
    applying stale outcomes to a row a concurrent PATCH/resolve has since
    changed would silently revert that edit."""
    for outcome in outcomes:
        put_source(job, outcome.source_id, outcome.claims)
    return await resolve_job(session, job)


async def run_episode_stage(
    session: AsyncSession,
    job: Job,
    providers: Sequence[EpisodeListProvider],
    cfg: Config,
    opts: StageOptions,
) -> tuple[list[SourceOutcome], ResolveOutcome]:
    """Compute, store every outcome, resolve, flush. The caller commits."""
    outcomes = await compute_episode_claims(session, job, providers, cfg, opts)
    resolved = await apply_episode_outcomes(session, job, outcomes)
    return outcomes, resolved
