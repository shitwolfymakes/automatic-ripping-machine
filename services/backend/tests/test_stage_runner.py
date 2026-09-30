"""The episode stage's background runner: scheduling/dedup/rerun-once,
provider caching, event emission, exception swallowing, and the startup
sweep (design spec 5, 6.2, 6.3, 9; plan Task 8)."""

import asyncio
import logging
import os
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import httpx  # noqa: E402
import pytest  # noqa: E402

from arm_common import Config, DiscType, Job, JobStatus, Track, TrackKind  # noqa: E402
from arm_common.enums import MediaType  # noqa: E402
from arm_common.schemas import ExternalIds  # noqa: E402

from arm_backend.identity.episodes.model import Episode  # noqa: E402
from arm_backend.identity.http import SourceError  # noqa: E402
from arm_backend.identity.proposals import claims_of  # noqa: E402
from arm_backend.identity.stage_runner import (  # noqa: E402
    EpisodeStageRunner,
    build_providers,
)
from tests._fakes import FakeSession  # noqa: E402

CFG = Config(id=1)

# A season whose runtimes are distinct enough that a 4-title disc fits one place only.
DISTINCT = [1320, 2580, 1500, 2880, 1800, 2220, 3060, 1980, 2400, 1680]
# The disc: E3-E6 of DISTINCT.
DISC = [1500, 2880, 1800, 2220]


def _season(number: int, runtimes: list[int]) -> list[Episode]:
    return [Episode(season=number, number=i, name=f"Name {i}", runtime_s=rt) for i, rt in enumerate(runtimes, start=1)]


class _Hub:
    """Recording fake WSHub (same shape the router tests use)."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(
        self,
        topic: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        persist: bool = True,
        job_id: str | None = None,
        track_id: str | None = None,
        session: Any = None,
    ) -> None:
        self.events.append({"topic": topic, "event_type": event_type, "payload": payload, "job_id": job_id})


class FakeHttp:
    def __init__(self, backing_off: bool = False) -> None:
        self._backing_off = backing_off

    def backing_off(self) -> bool:
        return self._backing_off


class FakeProvider:
    """In-memory EpisodeListProvider (mirrors test_episode_stage.py's)."""

    def __init__(
        self,
        source_id: str = "episodes_tmdb",
        id_field: str = "tmdb",
        *,
        seasons: dict[int, list[Episode]] | None = None,
        show_id: str | None = "100",
        error: Exception | None = None,
        gate: asyncio.Event | None = None,
    ) -> None:
        self.source_id = source_id
        self.id_field = id_field
        self.http = FakeHttp()
        self._seasons = seasons or {}
        self._show_id = show_id
        self.error = error
        self._gate = gate
        self.calls: list[tuple[str, Any]] = []

    def configured(self, cfg: Config) -> str | None:
        self.calls.append(("configured", None))
        return None

    async def resolve_show_id(self, ids: ExternalIds) -> str | None:
        self.calls.append(("resolve_show_id", ids))
        return self._show_id

    async def seasons(self, show_id: str) -> list[int]:
        self.calls.append(("seasons", show_id))
        return sorted(self._seasons)

    async def season(self, show_id: str, number: int) -> list[Episode]:
        if self._gate is not None:
            await self._gate.wait()
        self.calls.append(("season", number))
        if self.error is not None:
            raise self.error
        return self._seasons[number]


def _job(
    job_id: str = "job_1",
    *,
    season: int | None = 1,
    status: JobStatus = JobStatus.IDENTIFIED,
    media_type: MediaType | None = MediaType.TV,
    meta: dict[str, Any] | None = None,
) -> Job:
    return Job(
        id=job_id,
        drive_id="d",
        disc_type=DiscType.DVD,
        status=status,
        title="Show",
        media_type=media_type,
        season=season,
        metadata_json=meta if meta is not None else {"identity": {"external_ids": {"imdb": "tt1"}}},
    )


def _track(job_id: str, index: int, seconds: int | None, **kw: Any) -> Track:
    return Track(
        id=f"{job_id}_trk_{index}",
        job_id=job_id,
        kind=kw.pop("kind", TrackKind.VIDEO_TITLE),
        index=index,
        source_ref=str(index),
        duration_seconds=seconds,
        **kw,
    )


def _db(*jobs: Job, tracks: list[Track] | None = None, cfg: Config = CFG) -> FakeSession:
    db = FakeSession()
    db.rows["jobs"] = list(jobs)
    db.rows["tracks"] = tracks or []
    db.rows["config"] = [cfg]
    return db


def _runner(db: FakeSession, hub: _Hub, providers: list[Any]) -> EpisodeStageRunner:
    return EpisodeStageRunner(
        lambda: db,
        httpx.AsyncClient(),
        hub,
        providers_factory=lambda http_map, cfg: providers,
    )


# ---------------------------------------------------------------------------
# schedule: dedupe + re-run-once
# ---------------------------------------------------------------------------


async def test_schedule_dedupes_a_pending_job() -> None:
    """A second `schedule` call for a job already pending/running is a no-op
    on the task set (never queues a second concurrent run) — it only marks
    "run again once"."""
    job = _job()
    db = _db(job, tracks=[_track(job.id, i, s) for i, s in enumerate(DISC)])
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    hub = _Hub()
    runner = _runner(db, hub, [provider])

    runner.schedule(job.id)
    runner.schedule(job.id)  # still pending (task hasn't started yet): dedup, not a second task

    assert len(runner._pending) == 1
    assert job.id in runner._rerun

    await runner.drain()

    # Exactly two runs happened: the original + the one rerun-once.
    assert len([c for c in provider.calls if c[0] == "configured"]) == 2
    assert runner._pending == {}
    assert runner._rerun == set()


async def test_reschedule_while_a_run_is_in_flight_reruns_once() -> None:
    """`schedule` called genuinely mid-run (not just mid-event-loop-tick)
    still only produces one extra run."""
    job = _job()
    db = _db(job, tracks=[_track(job.id, i, s) for i, s in enumerate(DISC)])
    gate = asyncio.Event()
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)}, gate=gate)
    hub = _Hub()
    runner = _runner(db, hub, [provider])

    runner.schedule(job.id)
    await asyncio.sleep(0)  # let the task start and block on the gate
    assert job.id in runner._pending

    runner.schedule(job.id)  # marks rerun while genuinely in flight
    runner.schedule(job.id)  # a third call must not queue a second rerun
    assert job.id in runner._rerun

    gate.set()
    await runner.drain()

    assert len([c for c in provider.calls if c[0] == "configured"]) == 2


# ---------------------------------------------------------------------------
# shutdown
# ---------------------------------------------------------------------------


async def test_shutdown_with_nothing_pending_is_a_noop() -> None:
    hub = _Hub()
    runner = _runner(_db(), hub, [FakeProvider()])

    await runner.shutdown()  # no in-flight tasks to cancel/await

    assert runner._pending == {}
    runner.schedule("job_1")
    assert runner._pending == {}  # still disabled


async def test_shutdown_cancels_in_flight_and_disables_schedule() -> None:
    job = _job()
    db = _db(job, tracks=[_track(job.id, i, s) for i, s in enumerate(DISC)])
    gate = asyncio.Event()
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)}, gate=gate)
    hub = _Hub()
    runner = _runner(db, hub, [provider])

    runner.schedule(job.id)
    await asyncio.sleep(0)
    assert job.id in runner._pending

    await runner.shutdown()

    assert runner._pending == {}
    runner.schedule(job.id)  # no-op after shutdown
    assert runner._pending == {}


# ---------------------------------------------------------------------------
# one run: emits events, swallows exceptions
# ---------------------------------------------------------------------------


async def test_run_applies_claims_and_emits_job_and_track_updated() -> None:
    job = _job()
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job, tracks=tracks)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    hub = _Hub()
    runner = _runner(db, hub, [provider])

    runner.schedule(job.id)
    await runner.drain()

    assert claims_of(job).sources["episodes_tmdb"].status == "ok"
    assert db.committed >= 1

    identity_events = [e for e in hub.events if e["event_type"] == "job.identity_updated"]
    assert len(identity_events) == 1
    assert identity_events[0]["payload"] == {"job_id": job.id, "sources": {"episodes_tmdb": "ok"}}
    assert identity_events[0]["job_id"] == job.id

    track_events = [e for e in hub.events if e["event_type"] == "track.updated"]
    assert {e["payload"]["track_id"] for e in track_events} == {t.id for t in tracks}
    assert all(e["payload"]["job_id"] == job.id for e in track_events)


async def test_run_vanished_job_is_a_silent_noop() -> None:
    hub = _Hub()
    db = _db()  # no jobs at all
    runner = _runner(db, hub, [FakeProvider()])

    runner.schedule("job_missing")
    await runner.drain()

    assert hub.events == []


async def test_run_non_tv_candidate_is_a_silent_noop() -> None:
    job = _job(media_type=MediaType.MOVIE)
    db = _db(job, tracks=[_track(job.id, 0, 5400)])
    hub = _Hub()
    provider = FakeProvider()
    runner = _runner(db, hub, [provider])

    runner.schedule(job.id)
    await runner.drain()

    assert hub.events == []
    assert provider.calls == []


async def test_run_swallows_an_unexpected_exception(caplog: pytest.LogCaptureFixture) -> None:
    """A blown-up session factory (or anything else inside the run) is
    logged with a traceback and never crashes the loop."""

    def _boom() -> FakeSession:
        raise RuntimeError("db unavailable")

    hub = _Hub()
    runner = EpisodeStageRunner(_boom, httpx.AsyncClient(), hub, providers_factory=lambda hm, cfg: [])

    with caplog.at_level(logging.ERROR, logger="arm_backend.identity.stage_runner"):
        runner.schedule("job_1")
        await runner.drain()

    assert "Traceback" in caplog.text
    assert runner._pending == {}


# ---------------------------------------------------------------------------
# provider caching (controller ruling 1)
# ---------------------------------------------------------------------------


async def test_providers_are_cached_and_rebuilt_only_on_cfg_change() -> None:
    job1 = _job("job_1")
    job2 = _job("job_2")
    tracks = [_track(job1.id, i, s) for i, s in enumerate(DISC)] + [_track(job2.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job1, job2, tracks=tracks, cfg=Config(id=1, tmdb_api_key="key-a"))
    hub = _Hub()
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    build_calls: list[Config] = []

    def factory(http_map: Any, cfg: Config) -> list[Any]:
        build_calls.append(cfg)
        return [provider]

    runner = EpisodeStageRunner(lambda: db, httpx.AsyncClient(), hub, providers_factory=factory)

    runner.schedule(job1.id)
    await runner.drain()
    assert len(build_calls) == 1

    # Same cfg (same key) -> providers are reused, not rebuilt.
    runner.schedule(job2.id)
    await runner.drain()
    assert len(build_calls) == 1

    # The key changes -> rebuilt.
    db.rows["config"] = [Config(id=1, tmdb_api_key="key-b")]
    runner.schedule(job1.id)
    await runner.drain()
    assert len(build_calls) == 2


def test_build_providers_wires_http_map_and_api_keys() -> None:
    from arm_backend.identity.http import POLICIES, SourceHttp

    http = httpx.AsyncClient()
    http_map = {sid: SourceHttp(http, POLICIES[sid]) for sid in ("episodes_tmdb", "episodes_tvmaze", "episodes_tvdb")}
    cfg = Config(id=1, tmdb_api_key="tmdb-key", tvdb_api_key="tvdb-key")

    providers = build_providers(http_map, cfg)

    by_id = {p.source_id: p for p in providers}
    assert set(by_id) == {"episodes_tmdb", "episodes_tvmaze", "episodes_tvdb"}
    assert by_id["episodes_tmdb"].http is http_map["episodes_tmdb"]
    assert by_id["episodes_tvmaze"].http is http_map["episodes_tvmaze"]
    assert by_id["episodes_tvdb"].http is http_map["episodes_tvdb"]
    assert by_id["episodes_tmdb"].configured(cfg) is None
    assert by_id["episodes_tvdb"].configured(cfg) is None
    assert by_id["episodes_tvmaze"].configured(cfg) is None


# ---------------------------------------------------------------------------
# sweep_startup (Review Focus 5)
# ---------------------------------------------------------------------------


async def test_sweep_startup_schedules_only_eligible_jobs_once() -> None:
    eligible = _job("job_eligible", status=JobStatus.IDENTIFIED)
    eligible_review = _job("job_review", status=JobStatus.AWAITING_REVIEW)
    already_ran = _job(
        "job_has_source",
        status=JobStatus.IDENTIFIED,
        meta={"identity_claims": {"sources": {"episodes_tmdb": {}}}},
    )
    not_tv = _job("job_movie", status=JobStatus.IDENTIFIED, media_type=MediaType.MOVIE)
    wrong_status = _job("job_ripping", status=JobStatus.RIPPING)

    db = _db(
        eligible,
        eligible_review,
        already_ran,
        not_tv,
        wrong_status,
        tracks=[_track(eligible.id, 0, 1500)],
    )
    hub = _Hub()
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    runner = _runner(db, hub, [provider])

    count = await runner.sweep_startup()

    assert count == 2
    assert set(runner._pending) == {"job_eligible", "job_review"}

    await runner.drain()


async def test_sweep_startup_returns_zero_when_nothing_is_eligible() -> None:
    db = _db()
    hub = _Hub()
    runner = _runner(db, hub, [FakeProvider()])

    count = await runner.sweep_startup()

    assert count == 0
    assert runner._pending == {}


# ---------------------------------------------------------------------------
# Review Focus 4: a season change followed by a provider error must not
# resurrect the stale season's claims.
# ---------------------------------------------------------------------------


async def test_review_focus_4_season_change_then_error_drops_stale_claims() -> None:
    job = _job(season=1)
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job, tracks=tracks)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT), 2: _season(2, DISTINCT)})
    hub = _Hub()
    runner = _runner(db, hub, [provider])

    # 1. An ok run at season 1.
    runner.schedule(job.id)
    await runner.drain()

    good = claims_of(job).sources["episodes_tmdb"]
    assert good.status == "ok"
    assert good.inputs["season"] == 1
    assert good.tracks  # populated with season-1 episode claims

    # 2. The operator changes the season to 2.
    job.season = 2

    # 3. The re-run's provider raises SourceError (different inputs: season 2).
    provider.error = SourceError("timeout")
    runner.schedule(job.id)
    await runner.drain()

    # 4. The season-1 claims are NOT kept.
    after = claims_of(job).sources["episodes_tmdb"]
    assert after.status == "error"
    assert after.inputs["season"] == 2
    assert after.tracks == {}
    assert job.season == 2
