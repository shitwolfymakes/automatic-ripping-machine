"""The episode stage (design spec 5, 6.2, 6.3, 9): match a TV disc's titles
against each ranked provider's episode list and record the result as one
tier-3 `SourceClaims` per provider.

`compute_episode_claims` only reads: it never adds to the session or writes
the job, except that `resolve_show_ids` caches newly found show ids on the job
when `opts.apply` is set. `run_episode_stage` stores every outcome with
`put_source`, then runs the resolver; the caller commits.

A result the stage is not sure of (ambiguous positions, low coverage, low
confidence, two seasons that fit about equally, nominal broadcast-slot
runtimes) is stored with `suggestion=True`, which the resolver applies as a
guess (`Resolution.episode_unsure`, held countdown, amber in the UI), and
`extra["hold_reasons"]` names every reason (`hold_reasons`).

With no known season, every season the provider lists is fetched, in
`season_scan_order`: the disc hint's season, then seasons sibling discs hold,
then the rest. Only a hint- or sibling-proposed season can stop the scan
early, and only when its fit would apply on its own.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Mapping, Sequence
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
from arm_backend.identity.pipeline import ResolveOutcome, hint_season, resolve_job
from arm_backend.identity.proposals import MANUAL, claims_of, put_source
from arm_backend.identity.sources.registry import (
    COVERAGE_STOP,
    EPISODE_SOURCE_BY_SETTING,
    enabled_episode_source_ids,
    episode_auto_apply,
    episode_tolerance,
)

logger = logging.getLogger(__name__)

# Nominal runtimes: a provider listing every episode at a whole number of
# 5-minute broadcast slots (e.g. TVmaze's 60 min for a 44-minute episode).
NOMINAL_SLOT_S = 300
# Suggestion thresholds (C2).
MIN_COVERAGE = 0.5
MIN_MEAN_CONFIDENCE = 0.4
NEAR_TIE_COST_RATIO = 0.1
# I5: a scanned season wins thinly when the runner-up's mean cost is within
# max(THIN_WIN_RATIO * runner-up, THIN_WIN_MIN_S) seconds of the best.
THIN_WIN_RATIO = 0.1
THIN_WIN_MIN_S = 30

_EPISODE_SOURCE_IDS = frozenset(EPISODE_SOURCE_BY_SETTING.values())
# Jobs that never produced a disc's episodes; they are not siblings.
_DEAD_STATUSES = frozenset({JobStatus.FAILED, JobStatus.ABANDONED})


@dataclass(frozen=True)
class StageOptions:
    season: int | None = None
    disc_number: int | None = None
    # None: the pinned source's stored tolerance, else the config's tolerance.
    tolerance: int | None = None
    only_source: str | None = None
    apply: bool = True
    # Scan every season even when the job has one.
    scan_seasons: bool = False


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


def _placed(track: Track) -> bool:
    """The operator set this episode number by hand, in a season."""
    return (
        track.role == TrackRole.EPISODE
        and track.season is not None
        and track.episode_number is not None
        and (track.identity_provenance or {}).get("episode_number") == MANUAL
    )


def operator_placed(tracks: Sequence[Track]) -> dict[int, frozenset[int]]:
    """Season -> the episode numbers (a range expanded) the operator placed by
    hand. Matching leaves those tracks alone and keeps their numbers free of
    every other title."""
    held: dict[int, set[int]] = {}
    for track in tracks:
        if _placed(track) and track.season is not None and track.episode_number is not None:
            end = max(track.episode_number_end or track.episode_number, track.episode_number)
            held.setdefault(track.season, set()).update(range(track.episode_number, end + 1))
    return {season: frozenset(numbers) for season, numbers in held.items()}


def _eligible(tracks: Sequence[Track]) -> list[TitleIn]:
    """Selected video titles with a length whose role is unknown or episode
    (C6), other than ones the operator placed by hand. A role this stage itself set on an earlier run (provenance is an
    episode source, e.g. `extra` for a skipped title) does not count as known,
    so a re-run can still place that title."""
    out: list[TitleIn] = []
    for track in sorted(tracks, key=lambda t: t.index):
        if track.kind != TrackKind.VIDEO_TITLE or track.excluded or _placed(track):
            continue
        role_source = (track.identity_provenance or {}).get("role")
        if track.role not in (None, TrackRole.EPISODE) and role_source not in _EPISODE_SOURCE_IDS:
            continue
        length = _length(track)
        if length:
            out.append(TitleIn(ref=track.source_ref, seconds=length))
    return out


def _ordered_providers(
    job: Job, providers: Sequence[EpisodeListProvider], only_source: str | None, cfg: Config
) -> list[EpisodeListProvider]:
    """The operator's enabled sources in rank order (PR 4). The job's pinned
    source runs first even when unchecked, and an explicit `only_source`
    (a manual /match) runs regardless of the settings."""
    by_id = {p.source_id: p for p in providers}
    if only_source is not None:
        return [by_id[only_source]] if only_source in by_id else []
    order = list(enabled_episode_source_ids(cfg))
    pinned = claims_of(job).pin.get("episode")
    if pinned in by_id:
        order = [pinned, *[s for s in order if s != pinned]]
    return [by_id[s] for s in order if s in by_id]


async def _job_tracks(session: AsyncSession, job: Job) -> list[Track]:
    return list((await session.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all())


async def _sibling_rows(session: AsyncSession, job: Job) -> list[tuple[Job, list[Track]]]:
    """Other live TV jobs of the same show (a shared show id, not the title
    string), with their tracks; a job with no external ids has none. Failed
    and abandoned jobs never hold episodes. Tracks load only for these."""
    ids = current_ids(job)
    if not ids.model_dump(exclude_none=True):
        return []
    stmt = select(Job).where(col(Job.media_type) == MediaType.TV)
    jobs = [
        j
        for j in (await session.execute(stmt)).scalars().all()
        if j.id != job.id and j.status not in _DEAD_STATUSES and _shares_id(ids, current_ids(j))
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


def sibling_seasons(rows: Sequence[tuple[Job, list[Track]]], ids: ExternalIds) -> list[int]:
    """Seasons the sibling rows sharing an external id with `ids` hold (each
    job's season and every track's season), most frequent first, ties
    ascending."""
    counts: Counter[int] = Counter()
    for sibling, tracks in rows:
        if not _shares_id(ids, current_ids(sibling)):
            continue
        held = [sibling.season, *(t.season for t in tracks)]
        counts.update(season for season in held if season is not None)
    return sorted(counts, key=lambda season: (-counts[season], season))


def season_scan_order(
    seasons: Sequence[int], *, hint: int | None, sibling_seasons: Sequence[int]
) -> list[tuple[int, bool]]:
    """The listed `seasons` as `(season, from_hint)` pairs in scan order: the
    hint's season, then the listed sibling seasons nearest the hint first
    (ties and a missing hint ascending), then the rest ascending. `from_hint`
    marks the first two groups, the only seasons that may stop a scan."""
    listed = set(seasons)
    proposed = [hint] if hint is not None and hint in listed else []
    siblings = {s for s in sibling_seasons if s in listed and s not in proposed}
    proposed += sorted(siblings, key=lambda s: (abs(s - hint) if hint is not None else 0, s))
    rest = sorted(listed.difference(proposed))
    return [(s, True) for s in proposed] + [(s, False) for s in rest]


def _nominal(remaining: Sequence[Episode], titles: Sequence[TitleIn], tolerance: int) -> bool:
    """C4: every known runtime is a whole number of broadcast slots, and fewer
    than half the episode-shaped titles fit any of them (extras never count; a
    disc with no episode-shaped title is judged on all of them)."""
    known = {e.runtime_s for e in remaining if e.runtime_s}
    if not known or any(rt % NOMINAL_SLOT_S for rt in known):
        return False
    # A disc with nothing episode-shaped is judged on all its titles: that is the
    # TVmaze case, a list of round runtimes no title comes near.
    shaped = _episode_shaped(titles, remaining, tolerance) or list(titles)
    fitting = sum(1 for t in shaped if any(abs(t.seconds - rt) <= _eff_tol(rt, tolerance) for rt in known))
    return fitting < len(shaped) / 2


def _mean_cost(result: MatchResult) -> float:
    return result.cost / max(1, len(result.matches))


def _near_tie(first: MatchResult, second: MatchResult) -> bool:
    if first.coverage != second.coverage or len(first.matches) != len(second.matches):
        return False
    a, b = _mean_cost(first), _mean_cost(second)
    return abs(a - b) <= NEAR_TIE_COST_RATIO * max(a, b)


def _episode_shaped(titles: Sequence[TitleIn], episodes: Sequence[Episode], tolerance: int) -> list[TitleIn]:
    """Titles whose length could be an episode of this season, so menus, trailers
    and extras are left out. With no known runtime every title counts."""
    runtimes = [e.runtime_s for e in episodes if e.runtime_s]
    if not runtimes:
        return list(titles)
    low, high = min(runtimes) - tolerance, max(runtimes) + tolerance
    return [t for t in titles if low <= t.seconds <= high]


def episode_shaped_count(titles: Sequence[TitleIn], episodes: Sequence[Episode], tolerance: int) -> int:
    """How many titles are episode-shaped; this, not every title, anchors the disc."""
    return len(_episode_shaped(titles, episodes, tolerance))


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
    placed: Mapping[int, frozenset[int]]


async def _fit_season(provider: EpisodeListProvider, req: _Request, season: int) -> _SeasonFit | None:
    try:
        episodes = await provider.season(req.show_id, season)
    except SourceMiss:
        return None
    siblings, conflict = _siblings(req.rows, req.ids, season, req.disc_number)
    if held := req.placed.get(season):
        # Claims the operator's numbers without anchoring on a disc.
        siblings.append(SiblingDisc(None, held))
    remaining, anchor = start_anchor(
        episodes,
        disc_number=req.disc_number,
        disc_total=req.disc_total,
        n_titles=episode_shaped_count(req.titles, episodes, req.tolerance),
        siblings=siblings,
    )
    nominal = _nominal(remaining, req.titles, req.tolerance)
    if nominal:
        remaining = [replace(e, runtime_s=None) for e in remaining]
    claimed = frozenset().union(*(s.episodes for s in siblings)) if siblings else frozenset()
    result = align_runs(req.titles, remaining, claimed=claimed, tolerance=req.tolerance, anchor=anchor)
    return _SeasonFit(result, nominal, conflict)


def _thin_win(best: MatchResult, runner_up: MatchResult) -> bool:
    gap = _mean_cost(runner_up) - _mean_cost(best)
    return gap < max(THIN_WIN_RATIO * _mean_cost(runner_up), THIN_WIN_MIN_S)


def hold_reasons(
    fit: _SeasonFit, ranked: Sequence[tuple[int, MatchResult]], *, scanned: bool, auto_apply: bool
) -> list[str]:
    """Why `fit` (the best-ranked season's) is held as a suggestion, in a
    fixed order; empty when it applies on its own. `near_tie` and `thin_win`
    compare against the runner-up in `ranked`; `thin_win` only for a scanned
    season (I5)."""
    result = fit.result
    runner_up = ranked[1][1] if len(ranked) > 1 else None
    mean_conf = sum(m.confidence for m in result.matches) / max(1, len(result.matches))
    checks = (
        ("auto_apply_off", not auto_apply),
        ("ambiguous", result.ambiguous),
        ("low_coverage", result.coverage < MIN_COVERAGE),
        ("low_confidence", mean_conf < MIN_MEAN_CONFIDENCE),
        ("near_tie", runner_up is not None and _near_tie(result, runner_up)),
        ("thin_win", scanned and runner_up is not None and _thin_win(result, runner_up)),
        ("nominal_runtimes", fit.nominal),
        ("sibling_conflict", fit.sibling_conflict),
    )
    return [code for code, held in checks if held]


async def _pick_season(
    provider: EpisodeListProvider, req: _Request, order: Sequence[tuple[int, bool]]
) -> tuple[int, _SeasonFit, list[tuple[int, MatchResult]], bool] | None:
    """The best-ranked season's fit, the ranking of the seasons tried, and
    whether the scan stopped early (seasons were left untried); None when no
    season could be fetched.

    Seasons are tried in `order`. A season with `from_hint` set stops the
    scan when it ranks first and nothing holds its fit (judged as if
    auto-apply were on: the stop is about confidence)."""
    fits: dict[int, _SeasonFit] = {}
    ranked: list[tuple[int, MatchResult]] = []
    for i, (season, from_hint) in enumerate(order):
        fit = await _fit_season(provider, req, season)
        if fit is None:
            continue
        fits[season] = fit
        ranked = rank_seasons({s: f.result for s, f in fits.items()})
        if from_hint and ranked[0][0] == season and not hold_reasons(fit, ranked, scanned=True, auto_apply=True):
            return season, fit, ranked, i < len(order) - 1
    if not ranked:
        return None
    season = ranked[0][0]
    return season, fits[season], ranked, False


def _ok_claims(
    season: int,
    fit: _SeasonFit,
    ranked: Sequence[tuple[int, MatchResult]],
    *,
    scanned: bool,
    stopped_early: bool,
    inputs: dict[str, Any],
    now: datetime,
    auto_apply: bool,
) -> SourceClaims:
    result = fit.result
    reasons = hold_reasons(fit, ranked, scanned=scanned, auto_apply=auto_apply)
    near_tie = "near_tie" in reasons
    thin_win = "thin_win" in reasons
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
        suggestion=bool(reasons),
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
            **({"thin_win": True} if thin_win else {}),
            "hold_reasons": reasons,
            **({"scan_stopped_early": stopped_early} if scanned else {}),
        },
    )


def _known_season(job: Job, opts: StageOptions) -> int | None:
    """The season to match against without scanning: the option, else the
    job's season unless this stage itself set it (F1). A season an episode
    source picked by scanning stays a scan, so re-runs keep proposing it
    and their inputs stay the same."""
    if opts.scan_seasons:
        return None
    if opts.season is not None:
        return opts.season
    if (job.identity_provenance or {}).get("season") in _EPISODE_SOURCE_IDS:
        return None
    return job.season


def _tolerance(job: Job, source_id: str, opts: StageOptions, cfg: Config) -> int:
    """The option when given; else, for the pinned episode source, the
    tolerance the operator's `/match` stored in its inputs (I3), so a default
    background run asks the same question and C7 input equality holds."""
    if opts.tolerance is not None:
        return opts.tolerance
    claims = claims_of(job)
    stored = claims.sources.get(source_id)
    if claims.pin.get("episode") == source_id and stored is not None:
        tolerance = stored.inputs.get("tolerance")
        if isinstance(tolerance, int) and not isinstance(tolerance, bool):
            return tolerance
    return episode_tolerance(cfg)


async def _match(
    provider: EpisodeListProvider,
    job: Job,
    cfg: Config,
    opts: StageOptions,
    *,
    titles: Sequence[TitleIn],
    rows: Sequence[tuple[Job, list[Track]]],
    placed: Mapping[int, frozenset[int]],
    now: datetime,
    inputs: dict[str, Any],
) -> SourceOutcome:
    """One provider's outcome. Fills `inputs` as soon as they are known so an
    error raised later still carries them (C7)."""
    source_id = provider.source_id
    reason = provider.configured(cfg)
    if reason is not None:
        return SourceOutcome(source_id, SourceClaims(run_at=now, status="skipped", detail=reason), None)
    previous = claims_of(job).sources.get(source_id)
    known_season = _known_season(job, opts)
    disc_number = opts.disc_number if opts.disc_number is not None else job.disc_number
    tolerance = _tolerance(job, source_id, opts, cfg)
    # The keep-path inputs (I2, M3, R2): when the provider cannot be asked,
    # the show id is the one the last stored entry used, and the rest is this
    # request's, so put_source keeps the last good claims only when the
    # request is unchanged. With no known previous show id (none stored, or
    # cleared by /resolve naming a different show) nothing can be kept.
    prior_inputs = previous.inputs if previous else {}
    prior_show_id = prior_inputs.get("show_id")
    kept = (
        {"show_id": prior_show_id, "season": known_season, "disc_number": disc_number, "tolerance": tolerance}
        if prior_show_id is not None
        else {}
    )
    if provider.http.backing_off():
        backoff_inputs = {**kept, "nominal_runtimes": prior_inputs.get("nominal_runtimes")} if kept else {}
        claims = SourceClaims(run_at=now, status="error", detail="backing off", inputs=backoff_inputs)
        return SourceOutcome(source_id, claims, None)

    try:
        ids = await resolve_show_ids(job, [provider], persist=opts.apply, raise_errors=True)
    except SourceError:
        # M3: a transient failure, not "show not found".
        inputs.update(kept)
        raise
    show_id = getattr(ids, provider.id_field, None)
    if not show_id:
        return SourceOutcome(source_id, SourceClaims(run_at=now, status="miss", detail="show not found"), None)

    inputs.update(show_id=show_id, season=known_season, disc_number=disc_number, tolerance=tolerance)

    if known_season is not None:
        order = [(known_season, False)]
    else:
        try:
            listed = await provider.seasons(show_id)
        except SourceMiss:
            # A stale cached show id: the provider no longer knows the show.
            claims = SourceClaims(run_at=now, status="miss", detail="show not found", inputs=dict(inputs))
            return SourceOutcome(source_id, claims, None)
        if not listed:
            claims = SourceClaims(run_at=now, status="miss", detail="no seasons listed", inputs=dict(inputs))
            return SourceOutcome(source_id, claims, None)
        order = season_scan_order(listed, hint=hint_season(job), sibling_seasons=sibling_seasons(rows, ids))

    req = _Request(show_id, ids, titles, rows, disc_number, job.disc_total, tolerance, placed)
    picked = await _pick_season(provider, req, order)
    if picked is None or not picked[1].result.matches:
        claims = SourceClaims(run_at=now, status="miss", detail="no episodes matched", inputs=dict(inputs))
        return SourceOutcome(source_id, claims, picked[1].result if picked else None)
    season, fit, ranked, stopped_early = picked
    claims = _ok_claims(
        season,
        fit,
        ranked,
        scanned=known_season is None,
        stopped_early=stopped_early,
        inputs=inputs,
        now=now,
        auto_apply=episode_auto_apply(cfg),
    )
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
    job_tracks = await _job_tracks(session, job)
    titles = _eligible(job_tracks)
    if not titles:
        # Nothing to match yet (e.g. identify without the review hold creates
        # no tracks; rip-start schedules the stage again). No outcome means
        # nothing is stored, so `sweep_startup` can still pick the job up.
        return []
    rows = await _sibling_rows(session, job)
    placed = operator_placed(job_tracks)
    now = datetime.now(UTC)
    outcomes: list[SourceOutcome] = []
    for provider in _ordered_providers(job, providers, opts.only_source, cfg):
        inputs: dict[str, Any] = {}
        try:
            outcome = await _match(
                provider, job, cfg, opts, titles=titles, rows=rows, placed=placed, now=now, inputs=inputs
            )
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
    changed would silently revert that edit.

    Stored claims always keep their computed `suggestion` flag: the RESOLVER
    (`resolver.resolve`) applies a held "ok" result as a guess and reports
    it through `episode_unsure`, rather than this stage rewriting the stored
    claim (and a same-inputs error that makes `put_source` keep the prior
    good "ok" entry stays applicable too, per F8)."""
    for outcome in outcomes:
        put_source(job, outcome.source_id, outcome.claims)
    return await resolve_job(session, job)


def found_ids_from_outcomes(outcomes: Sequence[SourceOutcome], providers: Sequence[EpisodeListProvider]) -> ExternalIds:
    """Every outcome's resolved show id, keyed by its provider's `id_field`.

    For a caller (the identity router's `/identity/match`) that computed
    with show-id persistence off (`StageOptions.apply=False`) and needs to
    fold newly found ids onto a job it re-selects and commits separately —
    see `ids.merge_new_ids` — rather than relying on an in-place mutation
    `compute_episode_claims` never made (Task 9 F2: `merge_new_ids(fresh_job,
    current_ids(job))` was dead code once `job` and `fresh_job` are the same
    object and persistence was off — nothing was ever mutated to merge)."""
    id_field_by_source = {p.source_id: p.id_field for p in providers}
    found: dict[str, str] = {}
    for outcome in outcomes:
        show_id = outcome.claims.inputs.get("show_id")
        field = id_field_by_source.get(outcome.source_id)
        if show_id and field:
            found[field] = show_id
            if field == "tmdb":
                # A resolved TMDb show id is TV-kind, which lets `merge_new_ids`
                # replace a stored movie-kind id with it.
                found["tmdb_kind"] = "tv"
    return ExternalIds.model_validate(found)


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
