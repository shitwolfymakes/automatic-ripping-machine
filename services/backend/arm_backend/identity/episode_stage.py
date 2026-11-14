"""The episode stage: match a TV disc's titles
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
`extra["hold_reasons"]` names every reason (`episode_holds.hold_reasons`).

With no known season, every season the provider lists is fetched, in
`season_scan_order`: the disc hint's season, then seasons sibling discs hold,
then the rest. Only a hint- or sibling-proposed season can stop the scan
early, and only when its fit would apply on its own.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_common import Config, Job, Track, TrackKind
from arm_common.enums import MediaType, TrackRole
from arm_common.schemas import ExternalIds
from arm_common.schemas.identity import JobClaim, SourceClaims, TrackClaim

from arm_backend.identity.episode_holds import SeasonFit, hold_reasons
from arm_backend.identity.episode_siblings import episode_range, sibling_discs, sibling_rows, sibling_seasons
from arm_backend.identity.episodes.continuity import SiblingDisc, align_runs, rank_seasons, start_anchor
from arm_backend.identity.episodes.matcher import effective_tolerance
from arm_backend.identity.episodes.model import Episode, MatchResult, TitleIn
from arm_backend.identity.episodes.providers.base import EpisodeListProvider
from arm_backend.identity.http import SourceError, SourceMiss
from arm_backend.identity.ids import resolve_show_ids
from arm_backend.identity.hints import hint_season
from arm_backend.identity.pipeline import ResolveOutcome, resolve_job
from arm_backend.identity.proposals import MANUAL, claims_of, put_source
from arm_backend.identity.sources.registry import (
    COVERAGE_STOP,
    EPISODE_SOURCE_IDS,
    enabled_episode_source_ids,
    episode_auto_apply,
    episode_tolerance,
)

logger = logging.getLogger(__name__)

# Nominal runtimes: a provider listing every episode at a whole number of
# 5-minute broadcast slots (e.g. TVmaze's 60 min for a 44-minute episode).
NOMINAL_SLOT_S = 300


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


def is_tv_candidate(job: Job, tracks: Sequence[Track]) -> bool:
    """Gate: the job is TV, or any track is already an episode."""
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
            held.setdefault(track.season, set()).update(episode_range(track.episode_number, track.episode_number_end))
    return {season: frozenset(numbers) for season, numbers in held.items()}


def _eligible(tracks: Sequence[Track]) -> list[TitleIn]:
    """Selected video titles with a length whose role is unknown or episode
    other than ones the operator placed by hand. A role this stage itself set on an earlier run (provenance is an
    episode source, e.g. `extra` for a skipped title) does not count as known,
    so a re-run can still place that title."""
    out: list[TitleIn] = []
    for track in sorted(tracks, key=lambda t: t.index):
        if track.kind != TrackKind.VIDEO_TITLE or track.excluded or _placed(track):
            continue
        role_source = (track.identity_provenance or {}).get("role")
        if track.role not in (None, TrackRole.EPISODE) and role_source not in EPISODE_SOURCE_IDS:
            continue
        length = _length(track)
        if length:
            out.append(TitleIn(ref=track.source_ref, seconds=length))
    return out


def _ordered_providers(
    job: Job, providers: Sequence[EpisodeListProvider], only_source: str | None, cfg: Config
) -> list[EpisodeListProvider]:
    """The operator's enabled sources in rank order. The job's pinned
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
    """Every known runtime is a whole number of broadcast slots, and fewer
    than half the episode-shaped titles fit any of them (extras never count; a
    disc with no episode-shaped title is judged on all of them)."""
    known = {e.runtime_s for e in remaining if e.runtime_s}
    if not known or any(rt % NOMINAL_SLOT_S for rt in known):
        return False
    # A disc with nothing episode-shaped is judged on all its titles: that is the
    # TVmaze case, a list of round runtimes no title comes near.
    shaped = _episode_shaped(titles, remaining, tolerance) or list(titles)
    fitting = sum(1 for t in shaped if any(abs(t.seconds - rt) <= effective_tolerance(rt, tolerance) for rt in known))
    return fitting < len(shaped) / 2


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


@dataclass(frozen=True)
class _StageContext:
    """The per-job values every provider's match shares."""

    job: Job
    cfg: Config
    opts: StageOptions
    titles: Sequence[TitleIn]
    rows: Sequence[tuple[Job, list[Track]]]
    placed: Mapping[int, frozenset[int]]
    now: datetime


async def _fit_season(provider: EpisodeListProvider, req: _Request, season: int) -> SeasonFit | None:
    try:
        episodes = await provider.season(req.show_id, season)
    except SourceMiss:
        return None
    siblings, conflict = sibling_discs(req.rows, req.ids, season, req.disc_number)
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
    return SeasonFit(result, nominal, conflict)


class _SeasonPick(NamedTuple):
    """The season `_pick_season` chose: its fit, the ranking of the seasons
    tried, and whether the scan stopped early (seasons were left untried)."""

    season: int
    fit: SeasonFit
    ranked: list[tuple[int, MatchResult]]
    stopped_early: bool


async def _pick_season(
    provider: EpisodeListProvider, req: _Request, order: Sequence[tuple[int, bool]]
) -> _SeasonPick | None:
    """The chosen season (`_SeasonPick`); None when no season could be fetched.

    Seasons are tried in `order`. A season with `from_hint` set stops the
    scan when it ranks first and nothing holds its fit (judged as if
    auto-apply were on: the stop is about confidence)."""
    fits: dict[int, SeasonFit] = {}
    ranked: list[tuple[int, MatchResult]] = []
    for i, (season, from_hint) in enumerate(order):
        fit = await _fit_season(provider, req, season)
        if fit is None:
            continue
        fits[season] = fit
        ranked = rank_seasons({s: f.result for s, f in fits.items()})
        if from_hint and ranked[0][0] == season and not hold_reasons(fit, ranked, scanned=True, auto_apply=True):
            return _SeasonPick(season, fit, ranked, i < len(order) - 1)
    if not ranked:
        return None
    season = ranked[0][0]
    return _SeasonPick(season, fits[season], ranked, False)


def _ok_claims(
    pick: _SeasonPick, *, scanned: bool, inputs: dict[str, Any], now: datetime, auto_apply: bool
) -> SourceClaims:
    season, fit, ranked, stopped_early = pick
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
    job's season unless this stage itself set it. A season an episode
    source picked by scanning stays a scan, so re-runs keep proposing it
    and their inputs stay the same."""
    if opts.scan_seasons:
        return None
    if opts.season is not None:
        return opts.season
    if (job.identity_provenance or {}).get("season") in EPISODE_SOURCE_IDS:
        return None
    return job.season


def _tolerance(job: Job, source_id: str, opts: StageOptions, cfg: Config) -> int:
    """The option when given; else, for the pinned episode source, the
    tolerance the operator's `/match` stored in its inputs, so a default
    background run asks the same question and the stored inputs compare equal."""
    if opts.tolerance is not None:
        return opts.tolerance
    claims = claims_of(job)
    stored = claims.sources.get(source_id)
    if claims.pin.get("episode") == source_id and stored is not None:
        tolerance = stored.inputs.get("tolerance")
        if isinstance(tolerance, int) and not isinstance(tolerance, bool):
            return tolerance
    return episode_tolerance(cfg)


def _kept_inputs(
    prior_inputs: Mapping[str, Any], known_season: int | None, disc_number: int | None, tolerance: int
) -> dict[str, Any]:
    """The keep-path inputs: when the provider cannot be asked,
    the show id is the one the last stored entry used, and the rest is this
    request's, so put_source keeps the last good claims only when the
    request is unchanged. With no known previous show id (none stored, or
    cleared by /resolve naming a different show) nothing can be kept, and
    this is empty."""
    prior_show_id = prior_inputs.get("show_id")
    return (
        {"show_id": prior_show_id, "season": known_season, "disc_number": disc_number, "tolerance": tolerance}
        if prior_show_id is not None
        else {}
    )


def _backoff_outcome(
    source_id: str, kept: dict[str, Any], prior_inputs: Mapping[str, Any], now: datetime
) -> SourceOutcome:
    """The error outcome while the provider backs off: the keep-path inputs and
    the last stored `nominal_runtimes`, so put_source keeps the last good claims."""
    backoff_inputs = {**kept, "nominal_runtimes": prior_inputs.get("nominal_runtimes")} if kept else {}
    claims = SourceClaims(run_at=now, status="error", detail="backing off", inputs=backoff_inputs)
    return SourceOutcome(source_id, claims, None)


def _miss_outcome(
    source_id: str,
    detail: str,
    inputs: Mapping[str, Any],
    now: datetime,
    result: MatchResult | None = None,
) -> SourceOutcome:
    """A miss outcome carrying a copy of this request's inputs."""
    return SourceOutcome(source_id, SourceClaims(run_at=now, status="miss", detail=detail, inputs=dict(inputs)), result)


async def _season_order(
    provider: EpisodeListProvider,
    ctx: _StageContext,
    show_id: str,
    ids: ExternalIds,
    known_season: int | None,
    inputs: Mapping[str, Any],
) -> list[tuple[int, bool]] | SourceOutcome:
    """The seasons to try, in order: the known season alone, else every listed
    season in `season_scan_order`; a miss outcome instead when the provider no
    longer knows the show or lists no seasons."""
    if known_season is not None:
        return [(known_season, False)]
    try:
        listed = await provider.seasons(show_id)
    except SourceMiss:
        # A stale cached show id: the provider no longer knows the show.
        return _miss_outcome(provider.source_id, "show not found", inputs, ctx.now)
    if not listed:
        return _miss_outcome(provider.source_id, "no seasons listed", inputs, ctx.now)
    return season_scan_order(listed, hint=hint_season(ctx.job), sibling_seasons=sibling_seasons(ctx.rows, ids))


async def _match(
    provider: EpisodeListProvider,
    ctx: _StageContext,
    inputs: dict[str, Any],
) -> SourceOutcome:
    """One provider's outcome. Fills `inputs` as soon as they are known so an
    error raised later still carries them."""
    source_id = provider.source_id
    reason = provider.configured(ctx.cfg)
    if reason is not None:
        return SourceOutcome(source_id, SourceClaims(run_at=ctx.now, status="skipped", detail=reason), None)
    previous = claims_of(ctx.job).sources.get(source_id)
    known_season = _known_season(ctx.job, ctx.opts)
    disc_number = ctx.opts.disc_number if ctx.opts.disc_number is not None else ctx.job.disc_number
    tolerance = _tolerance(ctx.job, source_id, ctx.opts, ctx.cfg)
    prior_inputs = previous.inputs if previous else {}
    kept = _kept_inputs(prior_inputs, known_season, disc_number, tolerance)
    if provider.http.backing_off():
        return _backoff_outcome(source_id, kept, prior_inputs, ctx.now)

    try:
        ids = await resolve_show_ids(ctx.job, [provider], persist=ctx.opts.apply, raise_errors=True)
    except SourceError:
        # A transient failure, not "show not found".
        inputs.update(kept)
        raise
    show_id = getattr(ids, provider.id_field, None)
    if not show_id:
        return SourceOutcome(source_id, SourceClaims(run_at=ctx.now, status="miss", detail="show not found"), None)

    inputs.update(show_id=show_id, season=known_season, disc_number=disc_number, tolerance=tolerance)

    order = await _season_order(provider, ctx, show_id, ids, known_season, inputs)
    if isinstance(order, SourceOutcome):
        return order

    req = _Request(show_id, ids, ctx.titles, ctx.rows, disc_number, ctx.job.disc_total, tolerance, ctx.placed)
    picked = await _pick_season(provider, req, order)
    if picked is None or not picked.fit.result.matches:
        return _miss_outcome(source_id, "no episodes matched", inputs, ctx.now, picked.fit.result if picked else None)
    claims = _ok_claims(
        picked,
        scanned=known_season is None,
        inputs=inputs,
        now=ctx.now,
        auto_apply=episode_auto_apply(ctx.cfg),
    )
    return SourceOutcome(source_id, claims, picked.fit.result)


def _error(job: Job, source_id: str, e: Exception, inputs: dict[str, Any], now: datetime) -> SourceOutcome:
    """An error entry carrying the request inputs; `nominal_runtimes` (known
    only after a fetch) is carried from the last stored entry so put_source
    keeps the last good claims exactly when the request is unchanged."""
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
    first confident, well-covered result; later providers are not
    called. One provider failing never fails the stage."""
    job_tracks = await _job_tracks(session, job)
    titles = _eligible(job_tracks)
    if not titles:
        # Nothing to match yet (e.g. identify without the review hold creates
        # no tracks; rip-start schedules the stage again). No outcome means
        # nothing is stored, so `sweep_startup` can still pick the job up.
        return []
    rows = await sibling_rows(session, job)
    placed = operator_placed(job_tracks)
    now = datetime.now(UTC)
    ctx = _StageContext(job, cfg, opts, titles, rows, placed, now)
    outcomes: list[SourceOutcome] = []
    for provider in _ordered_providers(job, providers, opts.only_source, cfg):
        inputs: dict[str, Any] = {}
        try:
            outcome = await _match(provider, ctx, inputs)
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

    Split out from `run_episode_stage` so a caller that
    runs `compute_episode_claims` off a snapshot taken before a slow network
    round-trip can re-select `job` fresh immediately before this call —
    applying stale outcomes to a row a concurrent PATCH/resolve has since
    changed would silently revert that edit.

    Stored claims always keep their computed `suggestion` flag: the RESOLVER
    (`resolver.resolve`) applies a held "ok" result as a guess and reports
    it through `episode_unsure`, rather than this stage rewriting the stored
    claim (and a same-inputs error that makes `put_source` keep the prior
    good "ok" entry stays applicable too)."""
    for outcome in outcomes:
        put_source(job, outcome.source_id, outcome.claims)
    return await resolve_job(session, job)


def found_ids_from_outcomes(outcomes: Sequence[SourceOutcome], providers: Sequence[EpisodeListProvider]) -> ExternalIds:
    """Every outcome's resolved show id, keyed by its provider's `id_field`.

    For a caller (the identity router's `/identity/match`) that computed
    with show-id persistence off (`StageOptions.apply=False`) and needs to
    fold newly found ids onto a job it re-selects and commits separately —
    see `ids.merge_new_ids` — rather than relying on an in-place mutation
    `compute_episode_claims` never made (`merge_new_ids(fresh_job,
    current_ids(job))` would be dead code when `job` and `fresh_job` are the same
    object and persistence is off — nothing is ever mutated to merge)."""
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
