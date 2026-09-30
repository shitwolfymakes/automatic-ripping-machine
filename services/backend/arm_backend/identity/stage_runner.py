"""Background runner for the episode stage (design spec 5, 6.2, 6.3, 9;
plan Task 8): runs the episode stage off the request path so identify /
resolve / PATCH never block on a provider round-trip.

`EpisodeStageRunner.schedule(job_id)` is the only trigger surface routers
use. It is idempotent while a run for that job is pending or in flight: a
second `schedule` call for a run that has actually started marks "run again
once" so the operator's latest edit is never lost to an in-flight run
started on stale inputs, without ever running the stage twice concurrently
for the same job or piling up more than one extra run. A second call for a
run that is merely queued (not yet started) is a no-op.

Each run splits fetch from apply (fix round 1): `compute_episode_claims`
runs the network phase against a snapshot of the job, then the job is
re-selected fresh (`populate_existing=True`) immediately before writing —
never applying outcomes computed against a copy a concurrent PATCH/resolve
may have since changed. If the job vanished, or another `schedule()` for it
arrived while the network phase was in flight, the run writes, commits and
emits nothing and lets the queued rerun-once apply fresh outcomes instead.

One `SourceHttp` per episode source id is built once, at construction, and
kept for the runner's whole lifetime (`_http_map`): that is where rate
limits, TTL caches and backoff state live, and TVDB's login token lives on
the *provider* instance built from it — rebuilding providers on every run
would re-login every time. Providers are rebuilt only when the Config
values they were built from (the TMDb / TVDB API keys) change.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import col, select

from arm_backend.identity.episode_stage import (
    StageOptions,
    apply_episode_outcomes,
    compute_episode_claims,
    is_tv_candidate,
)
from arm_backend.identity.episodes.providers.base import EpisodeListProvider
from arm_backend.identity.episodes.providers.tmdb import TmdbEpisodes
from arm_backend.identity.episodes.providers.tvdb import TvdbEpisodes
from arm_backend.identity.episodes.providers.tvmaze import TvmazeEpisodes
from arm_backend.identity.http import POLICIES, SourceHttp
from arm_backend.identity.proposals import claims_of
from arm_backend.identity.sources.registry import EPISODE_SOURCE_BY_SETTING
from arm_backend.seeders import CONFIG_SINGLETON_ID
from arm_backend.ws import WSHub
from arm_common import Config, Job, JobStatus, Track

logger = logging.getLogger("arm_backend.identity.stage_runner")

# Every episode-match source id (independent of the sources.registry rank/
# tier maps, which PR 4 will make operator-configurable).
_EPISODE_SOURCE_IDS: tuple[str, ...] = tuple(EPISODE_SOURCE_BY_SETTING.values())

# Statuses `sweep_startup` considers (Review Focus 5): a job that has been
# identified but never had a chance to run the episode stage in-process
# (e.g. the backend restarted between identify and the runner picking it
# up, or PR 3b lands on a deployment with jobs already sitting here).
_SWEEP_STATUSES: frozenset[JobStatus] = frozenset(
    {JobStatus.IDENTIFIED, JobStatus.AWAITING_REVIEW, JobStatus.AWAITING_USER_ID}
)


def build_providers(http_map: dict[str, SourceHttp], cfg: Config) -> list[EpisodeListProvider]:
    """One provider per episode source id, wired to its own `SourceHttp`
    (`http_map`, built once by the runner) and this Config's API keys."""
    return [
        TmdbEpisodes(http_map["episodes_tmdb"], cfg.tmdb_api_key),
        TvmazeEpisodes(http_map["episodes_tvmaze"]),
        TvdbEpisodes(http_map["episodes_tvdb"], cfg.tvdb_api_key),
    ]


class EpisodeStageRunner:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        http: httpx.AsyncClient,
        hub: WSHub,
        *,
        providers_factory: Callable[[dict[str, SourceHttp], Config], list[EpisodeListProvider]] = build_providers,
    ) -> None:
        self._session_factory = session_factory
        self._hub = hub
        self._providers_factory = providers_factory
        # Built once, kept for the runner's lifetime: state (rate limit,
        # cache, backoff) is per-instance and must survive across runs.
        self._http_map: dict[str, SourceHttp] = {
            source_id: SourceHttp(http, POLICIES[source_id]) for source_id in _EPISODE_SOURCE_IDS
        }
        self._providers: list[EpisodeListProvider] | None = None
        self._providers_key: tuple[str | None, str | None] | None = None
        self._pending: dict[str, asyncio.Task[None]] = {}
        # job ids whose current run has actually started (past the top of
        # `_run_once`) — only these need a rerun-once when re-scheduled; a
        # job still sitting in `_pending` but not yet started will pick up
        # the latest state on its own once it does start.
        self._started: set[str] = set()
        self._rerun: set[str] = set()
        self._shutdown = False

    def _providers_for(self, cfg: Config) -> list[EpisodeListProvider]:
        key = (cfg.tmdb_api_key, cfg.tvdb_api_key)
        if self._providers is None or self._providers_key != key:
            self._providers = self._providers_factory(self._http_map, cfg)
            self._providers_key = key
        return self._providers

    # -- trigger ----------------------------------------------------------

    def schedule(self, job_id: str) -> None:
        """Run the episode stage for `job_id` in the background. Idempotent
        while a run for this job is already pending/running: a second call
        for a run that has actually started marks "run again once" (never
        queues more than one extra run); a second call for a run that is
        merely queued (its task hasn't started yet) is a pure no-op — that
        run will read the current state once it starts, so a rerun would
        just be a wasted extra pass. A no-op once `shutdown` has been
        called."""
        if self._shutdown:
            return
        if job_id in self._pending:
            if job_id in self._started:
                self._rerun.add(job_id)
            return
        task = asyncio.create_task(self._run_once(job_id))
        self._pending[job_id] = task

        def _done(done: asyncio.Task[None]) -> None:
            # A done-callback rather than `finally` inside `_run_once`: a
            # task cancelled before its first step never enters the
            # coroutine at all, and would otherwise never clear `_pending`.
            self._pending.pop(job_id, None)
            self._started.discard(job_id)
            if job_id in self._rerun and not self._shutdown:
                self._rerun.discard(job_id)
                self.schedule(job_id)

        task.add_done_callback(_done)

    async def drain(self) -> None:
        """Wait for every scheduled run to finish, including any
        re-run-once each triggers. Tests only."""
        while self._pending:
            # Gather only the *live* tasks — as of 3.14, `gather()` can
            # resolve an already-done task's future eagerly inside its own
            # constructor, ahead of that same task's *other* done-callback
            # (the one above that updates `_pending`/`_rerun`) getting its
            # turn on the ready queue. Handing it an already-done task risks
            # exactly that race. `gather()` with an empty list (every
            # pending task already done, awaiting only its own callback)
            # just resolves immediately — never re-triggers it.
            live = [t for t in self._pending.values() if not t.done()]
            await asyncio.gather(*live, return_exceptions=True)
            # Yielding once here lets a just-finished task's own done-
            # callback run before we re-check `_pending` — without it, a
            # fast rerun-once can live-lock this loop forever.
            await asyncio.sleep(0)

    async def shutdown(self) -> None:
        """Cancel every in-flight run. `schedule` is a no-op after this."""
        self._shutdown = True
        tasks = list(self._pending.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._pending.clear()
        self._started.clear()
        self._rerun.clear()

    # -- one run ------------------------------------------------------------

    async def _run_once(self, job_id: str) -> None:
        self._started.add(job_id)
        try:
            async with self._session_factory() as session:
                job = (await session.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
                if job is None:
                    # Vanished (deleted) between scheduling and running.
                    return
                tracks = list((await session.execute(select(Track).where(col(Track.job_id) == job_id))).scalars().all())
                if not is_tv_candidate(job, tracks):
                    return
                cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one()
                providers = self._providers_for(cfg)

                # Network phase (can take seconds): compute against this
                # snapshot only. No write yet — a PATCH or /resolve is free
                # to commit its own edit to this same job while we wait.
                outcomes = await compute_episode_claims(session, job, providers, cfg, StageOptions())

                # Re-select the job fresh (locked) right before writing.
                # `populate_existing` forces this session's identity map to
                # refresh `job`'s attributes from the current row rather
                # than handing back the snapshot we already read above (the
                # lost-update bug: applying outcomes computed from a stale
                # copy would silently clobber a manual claim a concurrent
                # request committed during the network phase).
                # `with_for_update` is a no-op against SQLite/FakeSession.
                fresh_job = (
                    await session.execute(
                        select(Job)
                        .where(col(Job.id) == job_id)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                ).scalar_one_or_none()
                if fresh_job is None or job_id in self._rerun:
                    # Vanished meanwhile, or another `schedule()` for this
                    # job arrived while we were waiting on providers: write
                    # nothing, commit nothing, emit nothing. The queued
                    # rerun-once (if any) will apply fresh outcomes against
                    # the current state instead.
                    return

                resolved = await apply_episode_outcomes(session, fresh_job, outcomes)
                await session.commit()
                await self._hub.emit(
                    topic="ripper.events",
                    event_type="job.identity_updated",
                    payload={
                        "job_id": fresh_job.id,
                        "sources": {o.source_id: o.claims.status for o in outcomes},
                    },
                    job_id=fresh_job.id,
                    session=session,
                )
                for track_id in sorted(resolved.track_ids):
                    await self._hub.emit(
                        topic="ripper.events",
                        event_type="track.updated",
                        payload={"track_id": track_id, "job_id": fresh_job.id},
                        job_id=fresh_job.id,
                        track_id=track_id,
                        session=session,
                    )
                await session.commit()
        except Exception:
            # Never crash the loop: a provider outage or a DB hiccup on one
            # job must not take down every other job's background stage.
            logger.exception("episode stage: background run failed job_id=%s", job_id)

    # -- startup sweep --------------------------------------------------

    async def sweep_startup(self) -> int:
        """Schedule every eligible job once: identified / awaiting review /
        awaiting user id, a TV candidate, with no episode source entry at
        all yet in its identity claims (Review Focus 5). Returns how many
        were scheduled."""
        count = 0
        async with self._session_factory() as session:
            jobs = list(
                (await session.execute(select(Job).where(col(Job.status).in_(tuple(_SWEEP_STATUSES))))).scalars().all()
            )
            job_ids = [j.id for j in jobs]
            tracks_by_job: dict[str, list[Track]] = {}
            if job_ids:
                rows = (await session.execute(select(Track).where(col(Track.job_id).in_(job_ids)))).scalars().all()
                for t in rows:
                    tracks_by_job.setdefault(t.job_id, []).append(t)
            for job in jobs:
                if not is_tv_candidate(job, tracks_by_job.get(job.id, [])):
                    continue
                if any(source_id in claims_of(job).sources for source_id in _EPISODE_SOURCE_IDS):
                    continue
                self.schedule(job.id)
                count += 1
        return count
