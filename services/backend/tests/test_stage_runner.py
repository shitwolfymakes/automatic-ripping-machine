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
from arm_backend.identity.proposals import claims_of, record_manual_job  # noqa: E402
from arm_backend.identity import stage_runner as stage_runner_module  # noqa: E402
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


class _TrackingSession:
    """Session double for fix round 2's no-flush invariant: `FakeSession`
    has no identity map at all (a "fresh" re-select just returns the same
    live object with whatever it currently holds), so it cannot see the
    round-2 bug — a real SQLAlchemy session autoflushes a dirty *attached*
    object as a full-row UPDATE the moment ANY query runs on that same
    session, independent of what that query is even for.

    This models just that: every `Job` a query returns becomes "attached"
    to THIS session instance (mirroring a per-session identity map); every
    subsequent `execute`/`flush`/`commit` on it snapshots each attached
    job's CURRENT `metadata_json` into `flush_log` first — exactly the data
    a real autoflush's UPDATE would carry, however stale. Multiple
    `_TrackingSession` instances share one underlying `FakeSession` (a
    stand-in for the same on-disk table) but each has its OWN `_attached`
    set, exactly like separate SQLAlchemy sessions never see each other's
    identity maps.
    """

    def __init__(self, fake: FakeSession) -> None:
        self._fake = fake
        self._attached: dict[str, Job] = {}
        self.flush_log: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self) -> "_TrackingSession":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def _autoflush(self) -> None:
        for job_id, job in self._attached.items():
            self.flush_log.append((job_id, dict(job.metadata_json or {})))

    async def execute(self, stmt: Any) -> Any:
        self._autoflush()
        result = await self._fake.execute(stmt)
        for row in result.rows:
            if isinstance(row, Job):
                self._attached[row.id] = row
        return result

    async def commit(self) -> None:
        self._autoflush()
        await self._fake.commit()

    async def flush(self) -> None:
        self._autoflush()
        await self._fake.flush()

    def add(self, obj: Any) -> None:
        if isinstance(obj, Job):
            self._attached[obj.id] = obj
        self._fake.add(obj)

    async def refresh(self, obj: Any) -> None:
        await self._fake.refresh(obj)


class _TrackingSessionFactory:
    """`session_factory` double: a fresh `_TrackingSession` (its own
    identity map) per call, all backed by the same underlying table."""

    def __init__(self, fake: FakeSession) -> None:
        self.fake = fake
        self.sessions: list[_TrackingSession] = []

    def __call__(self) -> _TrackingSession:
        session = _TrackingSession(self.fake)
        self.sessions.append(session)
        return session


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


class _GatedSeasonProvider(FakeProvider):
    """A `FakeProvider` whose `season()` blocks on a distinct gate per call
    and signals `reached` right before blocking, so a test can wait
    deterministically for "the Nth network call has started" instead of
    guessing an `asyncio.sleep(0)` count."""

    def __init__(self, *, gates: list[asyncio.Event], reached: asyncio.Event, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._gates = gates
        self._reached = reached
        self._call_n = 0

    async def season(self, show_id: str, number: int) -> list[Episode]:
        gate = self._gates[self._call_n]
        self._call_n += 1
        self._reached.set()
        await gate.wait()
        return await super().season(show_id, number)


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
    """A second `schedule` call for a job whose task hasn't started yet is a
    pure no-op (not even a rerun mark): that run will read the current state
    once it starts, so a rerun would just be a wasted extra pass."""
    job = _job()
    db = _db(job, tracks=[_track(job.id, i, s) for i, s in enumerate(DISC)])
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    hub = _Hub()
    runner = _runner(db, hub, [provider])

    runner.schedule(job.id)
    runner.schedule(job.id)  # still pending (task hasn't started yet): dedup, not a second task

    assert len(runner._pending) == 1
    assert job.id not in runner._rerun

    await runner.drain()

    # Exactly one run happened — no wasted rerun-once.
    assert len([c for c in provider.calls if c[0] == "configured"]) == 1
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
# fetch/apply split (fix round 1): a run in flight must not clobber a
# concurrent edit with outcomes computed against a stale snapshot.
# ---------------------------------------------------------------------------


async def test_rerun_requested_mid_flight_writes_nothing_before_the_rerun() -> None:
    """A `schedule()` that arrives while a run is genuinely mid-network-phase
    must not let that run apply its (about-to-be-stale) outcomes: it writes,
    commits and emits nothing, and the queued rerun-once applies fresh
    outcomes instead."""
    job = _job()
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job, tracks=tracks)
    gate1, gate2 = asyncio.Event(), asyncio.Event()
    reached = asyncio.Event()
    provider = _GatedSeasonProvider(seasons={1: _season(1, DISTINCT)}, gates=[gate1, gate2], reached=reached)
    hub = _Hub()
    runner = _runner(db, hub, [provider])

    runner.schedule(job.id)
    await asyncio.wait_for(reached.wait(), timeout=1)  # run 1 is blocked in its network call
    reached.clear()

    runner.schedule(job.id)  # genuinely mid-flight: marks a rerun
    assert job.id in runner._rerun

    gate1.set()  # let run 1's network call finish
    # Run 1 finishes (sees the rerun flag and bails without writing), its
    # done-callback reschedules, and run 2 starts and reaches its own
    # network call — all before we get control back here.
    await asyncio.wait_for(reached.wait(), timeout=1)

    # Checkpoint: run 1 bailed before writing/committing/emitting anything.
    assert job.id not in runner._rerun
    assert db.committed == 0
    assert hub.events == []
    assert "episodes_tmdb" not in claims_of(job).sources

    gate2.set()
    await runner.drain()

    # The rerun applied fresh outcomes.
    assert claims_of(job).sources["episodes_tmdb"].status == "ok"
    assert any(e["event_type"] == "job.identity_updated" for e in hub.events)


async def test_operator_edit_committed_during_network_phase_survives() -> None:
    """A manual claim a PATCH/resolve commits while the runner is
    mid-network-phase must survive: the runner re-selects the job fresh
    right before applying outcomes, not the stale copy it read before the
    network wait. A show id newly resolved during that same network phase
    (fix round 2) still ends up on the fresh row, merged in rather than
    lost along with the detached snapshot it was resolved on."""
    job = _job(season=1)  # default metadata: imdb only — tmdb gets resolved
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job, tracks=tracks)
    gate = asyncio.Event()
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)}, gate=gate, show_id="999")
    hub = _Hub()
    runner = _runner(db, hub, [provider])

    runner.schedule(job.id)
    await asyncio.sleep(0)  # the task has started and is blocked in its network call

    # The "operator" commits a manual season edit concurrently, modelled as
    # a fresh Job row replacing the one the runner read at the top of its
    # run: a real DB session would see this via a fresh re-select of the
    # same row; the fake models the same effect by swapping the row object
    # the table holds out from under the runner's already-read reference.
    edited = _job(job.id, season=None)
    record_manual_job(edited, {"season": 2})
    db.rows["jobs"] = [edited]

    gate.set()
    await runner.drain()

    # Exactly one row, and it's the fresh one — the runner applied its
    # outcomes to the row it re-selected, not the stale one it captured
    # before the network wait (which would otherwise have been re-added by
    # `resolve_job`'s own `session.add`, duplicating the row).
    assert db.rows["jobs"] == [edited]
    assert edited.season == 2  # the manual edit was not reverted
    assert edited.identity_provenance == {"season": "manual"}
    assert edited.metadata_json["identity"]["external_ids"]["tmdb"] == "999"  # merged onto the fresh row
    assert edited.metadata_json["identity"]["external_ids"]["imdb"] == "tt1"  # nothing else clobbered
    assert claims_of(edited).sources["episodes_tmdb"].status == "ok"  # the stage still ran


async def test_in_flight_run_never_re_adds_a_cleared_id_i4() -> None:
    """I4: the runner merges only the ids its compute phase newly found. An
    id the snapshot already had, which a concurrent /resolve then cleared on
    the fresh row, stays cleared."""
    job = _job(season=1, meta={"identity": {"external_ids": {"imdb": "tt1", "tvmaze": "55"}}})
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job, tracks=tracks)
    gate = asyncio.Event()
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)}, gate=gate, show_id="999")
    runner = _runner(db, _Hub(), [provider])

    runner.schedule(job.id)
    await asyncio.sleep(0)  # blocked in its network call

    edited = _job(job.id, season=1, meta={"identity": {"external_ids": {"imdb": "tt2"}}})
    db.rows["jobs"] = [edited]

    gate.set()
    await runner.drain()

    assert edited.metadata_json["identity"]["external_ids"] == {"imdb": "tt2", "tmdb": "999"}


class _CountingProvider(FakeProvider):
    """Counts `season()` calls in flight at once, each held on `gate`."""

    def __init__(self, gate: asyncio.Event, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._hold = gate
        self.active = 0
        self.peak = 0

    async def season(self, show_id: str, number: int) -> list[Episode]:
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await self._hold.wait()
            return await super().season(show_id, number)
        finally:
            self.active -= 1


async def test_at_most_two_runs_compute_at_once_m5() -> None:
    """M5: the runner's semaphore lets two jobs compute and apply at a time;
    the third waits its turn, then runs."""
    jobs = [_job(f"job_{n}") for n in range(3)]
    tracks = [_track(j.id, i, s) for j in jobs for i, s in enumerate(DISC)]
    db = _db(*jobs, tracks=tracks)
    gate = asyncio.Event()
    provider = _CountingProvider(gate, seasons={1: _season(1, DISTINCT)})
    runner = _runner(db, _Hub(), [provider])

    for j in jobs:
        runner.schedule(j.id)
    for _ in range(20):
        await asyncio.sleep(0)
    assert provider.active == 2
    assert len(runner._pending) == 3  # the third is scheduled, just waiting

    gate.set()
    await runner.drain()

    assert provider.peak == 2
    assert all(claims_of(j).sources["episodes_tmdb"].status == "ok" for j in jobs)


async def test_invalidated_job_queued_behind_the_cap_writes_nothing_first_r1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R1: a job queued behind two gated runs is invalidated. Its first run,
    once it gets a slot, writes nothing; only the rerun applies."""
    jobs = [_job(f"job_{n}") for n in range(3)]
    tracks = [_track(j.id, i, s) for j in jobs for i, s in enumerate(DISC)]
    db = _db(*jobs, tracks=tracks)
    gate = asyncio.Event()
    provider = _CountingProvider(gate, seasons={1: _season(1, DISTINCT)})
    runner = _runner(db, _Hub(), [provider])
    applied: list[str] = []
    real_apply = stage_runner_module.apply_outcomes_and_emit

    async def recording_apply(session: Any, job: Job, outcomes: Any, hub: Any) -> Any:
        applied.append(job.id)
        return await real_apply(session, job, outcomes, hub)

    monkeypatch.setattr(stage_runner_module, "apply_outcomes_and_emit", recording_apply)
    computed: list[str] = []
    real_compute = stage_runner_module.compute_episode_claims

    async def recording_compute(session: Any, job: Job, *args: Any) -> Any:
        computed.append(job.id)
        return await real_compute(session, job, *args)

    monkeypatch.setattr(stage_runner_module, "compute_episode_claims", recording_compute)

    for j in jobs:
        runner.schedule(j.id)
    for _ in range(20):
        await asyncio.sleep(0)
    assert provider.active == 2
    assert "job_2" not in runner._started  # queued behind the cap

    runner.invalidate("job_2")
    gate.set()
    await runner.drain()

    assert computed.count("job_2") == 2  # the first run, then the rerun
    assert applied.count("job_2") == 1  # only the rerun wrote
    assert claims_of(jobs[2]).sources["episodes_tmdb"].status == "ok"


async def test_run_with_no_eligible_titles_writes_and_emits_nothing_c1() -> None:
    """C1 polish: an identify-time run with no tracks yet stops right after
    compute: no lock, no resolve, no event."""
    job = _job()
    db = _db(job, tracks=[])
    hub = _Hub()
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    runner = _runner(db, hub, [provider])

    runner.schedule(job.id)
    await runner.drain()

    assert hub.events == []
    assert db.locked == []
    assert db.committed == 0
    assert provider.calls == []


async def test_compute_phase_mutation_never_reaches_a_flush() -> None:
    """Fix round 2's core invariant: nothing the compute phase mutates can
    ever reach a flush. `resolve_show_ids` mutates the compute snapshot's
    `metadata_json` in memory (a newly resolved show id); this must never
    show up in any session's autoflush log, on any session, at any point —
    it can only land in the DB via the apply phase's own, deliberate
    `merge_new_ids` + commit onto the FRESH row (a separate check, made by
    `test_operator_edit_committed_during_network_phase_survives`).

    `FakeSession` alone can't see this bug (no identity map, no autoflush,
    a "fresh" re-select just returns the same live object) — `_TrackingSession`
    adds exactly the one behavior that matters: a query on a session with a
    dirty attached object autoflushes it first, using its current, possibly
    stale, in-memory state."""
    job = _job()  # default metadata: imdb only — tmdb gets newly resolved
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    fake = FakeSession()
    fake.rows["jobs"] = [job]
    fake.rows["tracks"] = tracks
    fake.rows["config"] = [CFG]
    factory = _TrackingSessionFactory(fake)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)}, show_id="999")
    hub = _Hub()
    runner = EpisodeStageRunner(
        factory,  # type: ignore[arg-type]
        httpx.AsyncClient(),
        hub,
        providers_factory=lambda http_map, cfg: [provider],
    )

    runner.schedule(job.id)
    await runner.drain()

    # The run did resolve a new id (sanity: the mutation this test guards
    # against actually happened).
    assert job.metadata_json["identity"]["external_ids"]["tmdb"] == "999"

    # `_run_once` opens exactly two sessions in order: compute, then apply.
    # The apply session committing the merged id onto the fresh row is the
    # intended write (covered by the operator-edit test above); what must
    # NEVER happen is the *compute* session ever autoflushing `job` with
    # that id already on it — that would mean the mutation reached a flush
    # before the apply phase ever decided, deliberately, to write it.
    assert len(factory.sessions) == 2
    compute_session, apply_session = factory.sessions
    assert apply_session is not compute_session

    compute_flushes_with_the_new_id = [
        meta
        for jid, meta in compute_session.flush_log
        if jid == job.id and "tmdb" in (meta.get("identity", {}) or {}).get("external_ids", {})
    ]
    assert compute_flushes_with_the_new_id == []


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
# invalidate (Task 9 F4 part 2): the identity router's `apply=True` path
# calls this before computing so an in-flight background run can't clobber
# the write it's about to commit.
# ---------------------------------------------------------------------------


async def test_invalidate_noop_when_nothing_pending() -> None:
    hub = _Hub()
    runner = _runner(_db(), hub, [FakeProvider()])

    runner.invalidate("job_missing")

    assert runner._rerun == set()


async def test_invalidate_marks_rerun_for_a_run_not_yet_started_r1() -> None:
    """Immediately after `schedule()`, before any `await` yields control,
    the task exists in `_pending` but hasn't started. R1: `invalidate` still
    marks a rerun, since a queued run can take its slot and compute while the
    caller computes, then apply after the caller commits."""
    job = _job()
    db = _db(job, tracks=[_track(job.id, i, s) for i, s in enumerate(DISC)])
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    hub = _Hub()
    runner = _runner(db, hub, [provider])

    runner.schedule(job.id)
    assert job.id in runner._pending
    assert job.id not in runner._started

    runner.invalidate(job.id)

    assert job.id in runner._rerun

    await runner.drain()
    assert claims_of(job).sources["episodes_tmdb"].status == "ok"  # the rerun applied


async def test_invalidate_marks_rerun_when_run_has_started() -> None:
    """Invalidating a genuinely in-flight run discards its outcome BEFORE it
    ever writes: it commits nothing, emits nothing, and the job's claims stay
    empty right up to the point the rerun-once it triggers applies fresh
    outcomes -- exactly the no-stale-write guarantee `schedule()`'s own
    mid-flight rerun gives (fix round 1), now reachable through
    `invalidate()` too. Only the SECOND run's `job.identity_updated` ever
    lands (exactly one), and the stored claims are that second run's."""
    job = _job()
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job, tracks=tracks)
    gate1, gate2 = asyncio.Event(), asyncio.Event()
    reached = asyncio.Event()
    provider = _GatedSeasonProvider(seasons={1: _season(1, DISTINCT)}, gates=[gate1, gate2], reached=reached)
    hub = _Hub()
    runner = _runner(db, hub, [provider])

    runner.schedule(job.id)
    await asyncio.wait_for(reached.wait(), timeout=1)  # run 1 is blocked in its network call
    reached.clear()

    runner.invalidate(job.id)  # genuinely mid-flight: marks a rerun
    assert job.id in runner._rerun

    gate1.set()  # let run 1's network call finish
    await asyncio.wait_for(reached.wait(), timeout=1)  # run 1 bailed; run 2 reached its own network call

    # Checkpoint: run 1 wrote, committed and emitted nothing at all.
    assert job.id not in runner._rerun
    assert db.committed == 0
    assert hub.events == []
    assert "episodes_tmdb" not in claims_of(job).sources

    gate2.set()
    await runner.drain()

    # Only run 2 ever wrote or emitted: exactly one job.identity_updated,
    # and the stored claims are run 2's (not a stale run-1 outcome).
    identity_events = [e for e in hub.events if e["event_type"] == "job.identity_updated"]
    assert len(identity_events) == 1
    assert claims_of(job).sources["episodes_tmdb"].status == "ok"


async def test_invalidate_after_shutdown_is_noop() -> None:
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
    runner.invalidate(job.id)  # no-op after shutdown

    assert runner._rerun == set()


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


async def test_run_swallows_a_commit_failure(caplog: pytest.LogCaptureFixture) -> None:
    """A DB error at commit time (e.g. a lost connection) is logged and
    swallowed the same way — no events leak out for a write that never
    landed."""
    job = _job()
    db = _db(job, tracks=[_track(job.id, i, s) for i, s in enumerate(DISC)])
    db.commit_raises = RuntimeError("connection reset")
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    hub = _Hub()
    runner = _runner(db, hub, [provider])

    with caplog.at_level(logging.ERROR, logger="arm_backend.identity.stage_runner"):
        runner.schedule(job.id)
        await runner.drain()

    assert "Traceback" in caplog.text
    assert runner._pending == {}
    assert hub.events == []


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


def test_public_providers_method_returns_the_cached_list() -> None:
    """`providers()` (controller ruling 1) is the identity router's only way
    to reach this runner's providers -- it must be the same cached list
    `_providers_for` hands the background stage, not a fresh build."""
    db = _db()
    hub = _Hub()
    build_calls: list[Config] = []
    provider = FakeProvider()

    def factory(http_map: Any, cfg: Config) -> list[Any]:
        build_calls.append(cfg)
        return [provider]

    runner = EpisodeStageRunner(lambda: db, httpx.AsyncClient(), hub, providers_factory=factory)

    result = runner.providers(CFG)

    assert result == [provider]
    assert len(build_calls) == 1
    # Same cfg key -> cached, not rebuilt.
    assert runner.providers(CFG) == [provider]
    assert len(build_calls) == 1


# ---------------------------------------------------------------------------
# sweep_startup (Review Focus 5)
# ---------------------------------------------------------------------------


async def test_sweep_startup_schedules_only_eligible_jobs_once() -> None:
    eligible = _job("job_eligible", status=JobStatus.IDENTIFIED)
    eligible_review = _job("job_review", status=JobStatus.AWAITING_REVIEW)
    eligible_user_id = _job("job_user_id", status=JobStatus.AWAITING_USER_ID)
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
        eligible_user_id,
        already_ran,
        not_tv,
        wrong_status,
        tracks=[_track(eligible.id, 0, 1500)],
    )
    hub = _Hub()
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    runner = _runner(db, hub, [provider])

    count = await runner.sweep_startup()

    assert count == 3
    assert set(runner._pending) == {"job_eligible", "job_review", "job_user_id"}

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
    assert len(good.tracks) > 0  # populated with season-1 episode claims, before the error
    assert all(c.episode is not None for c in good.tracks.values())

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

    # The second run's own `job.identity_updated` event reports the error,
    # not the season-1 "ok" it replaced.
    identity_events = [e for e in hub.events if e["event_type"] == "job.identity_updated"]
    assert len(identity_events) == 2
    assert identity_events[0]["payload"]["sources"]["episodes_tmdb"] == "ok"
    assert identity_events[1]["payload"]["sources"]["episodes_tmdb"] == "error"
