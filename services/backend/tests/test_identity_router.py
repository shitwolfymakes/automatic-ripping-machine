"""Identity, match, pin and episode-browse endpoints (design spec 2026-09-28-
identity-sources, section 7; plan Task 9): happy paths for all four routes,
the preview/apply(+pin) split, 404/409/502, and the reader-write gate."""

from __future__ import annotations

import asyncio
import copy
import secrets
from typing import Any

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import pytest  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import identity as identity_router  # noqa: E402
from arm_common import Config, DiscType, Job, JobStatus, Track, TrackKind  # noqa: E402
from arm_common.enums import MediaType  # noqa: E402
from arm_common.models.user import GUEST_ROLE  # noqa: E402
from arm_common.schemas import ExternalIds  # noqa: E402
from arm_common import User  # noqa: E402

from arm_backend.identity import episode_stage  # noqa: E402
from arm_backend.identity.episodes.model import Episode  # noqa: E402
from arm_backend.identity.http import SourceError, SourceMiss  # noqa: E402
from arm_backend.identity.proposals import claims_of  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402

CFG = Config(id=1)

# A season whose runtimes are distinct enough that a 4-title disc fits one place only.
DISTINCT = [1320, 2580, 1500, 2880, 1800, 2220, 3060, 1980, 2400, 1680]
# The disc: E3-E6 of DISTINCT.
DISC = [1500, 2880, 1800, 2220]

JOB_ID = "job_01JZXR7K3M5Q8N4VWA00000001"


def _season(number: int, runtimes: list[int]) -> list[Episode]:
    return [Episode(season=number, number=i, name=f"Name {i}", runtime_s=rt) for i, rt in enumerate(runtimes, start=1)]


class FakeHttp:
    def __init__(self, backing_off: bool = False) -> None:
        self._backing_off = backing_off

    def backing_off(self) -> bool:
        return self._backing_off


class FakeProvider:
    """In-memory `EpisodeListProvider` (mirrors test_stage_runner.py's)."""

    def __init__(
        self,
        source_id: str = "episodes_tmdb",
        id_field: str = "tmdb",
        *,
        seasons: dict[int, list[Episode]] | None = None,
        show_id: str | None = "100",
        error: Exception | None = None,
        configured_reason: str | None = None,
        backing_off: bool = False,
        resolve_error: Exception | None = None,
    ) -> None:
        self.source_id = source_id
        self.id_field = id_field
        self.http = FakeHttp(backing_off)
        self._seasons = seasons or {}
        self._show_id = show_id
        self.error = error
        self._configured_reason = configured_reason
        self._resolve_error = resolve_error
        self.calls: list[str] = []

    def configured(self, cfg: Config) -> str | None:
        return self._configured_reason

    async def resolve_show_id(self, ids: ExternalIds) -> str | None:
        self.calls.append("resolve_show_id")
        if self._resolve_error is not None:
            raise self._resolve_error
        return self._show_id

    async def seasons(self, show_id: str) -> list[int]:
        self.calls.append("seasons")
        return sorted(self._seasons)

    async def season(self, show_id: str, number: int) -> list[Episode]:
        if self.error is not None:
            raise self.error
        if number not in self._seasons:
            raise SourceMiss(f"no season {number}")
        return self._seasons[number]


class _Hub:
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
        self.events.append({"topic": topic, "event_type": event_type, "payload": payload})


class _FakeStageRunner:
    """Duck-typed `EpisodeStageRunner` double: only `providers()` matters
    here (controller ruling 1) -- the router never touches anything else on
    the runner."""

    def __init__(self, providers: list[Any]) -> None:
        self._providers = providers
        self.provider_calls: list[Config] = []
        self.invalidate_calls: list[str] = []

    def providers(self, cfg: Config) -> list[Any]:
        self.provider_calls.append(cfg)
        return self._providers

    def invalidate(self, job_id: str) -> None:
        self.invalidate_calls.append(job_id)


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _make_app(
    signing_key: bytes,
    db: FakeSession,
    *,
    hub: _Hub | None = None,
    stage_runner: _FakeStageRunner | None | Any = "__default__",
) -> tuple[FastAPI, str, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.ws_hub = hub or _Hub()
    if stage_runner != "__default__":
        app.state.episode_stage = stage_runner
    app.include_router(identity_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    db.rows.setdefault("users", []).extend(
        [
            User(id="usr_admin", username="admin", password_hash="x", password_must_change=False),
            User(id="usr_guest", username="guest", password_hash="x", password_must_change=False, role=GUEST_ROLE),
        ]
    )
    admin_token, _ = issue_access_token("usr_admin", "admin", signing_key)
    guest_token, _ = issue_access_token("usr_guest", "guest", signing_key)
    return app, admin_token, guest_token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _job(
    job_id: str = JOB_ID,
    *,
    season: int | None = 1,
    media_type: MediaType | None = MediaType.TV,
    meta: dict[str, Any] | None = None,
) -> Job:
    return Job(
        id=job_id,
        drive_id="d",
        disc_type=DiscType.DVD,
        status=JobStatus.IDENTIFIED,
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
    db.rows["tracks"] = tracks if tracks is not None else []
    db.rows["config"] = [cfg]
    return db


# --- GET /identity -----------------------------------------------------------


def test_get_identity_happy_path(signing_key: bytes) -> None:
    job = _job(
        meta={
            "identity": {"external_ids": {"imdb": "tt1"}},
            "identity_claims": {
                "sources": {
                    "episodes_tmdb": {
                        "status": "ok",
                        "suggestion": True,
                        "tracks": {"1": {"season": 1, "episode": 3}},
                    }
                },
                "pin": {"episode": "episodes_tmdb"},
            },
        }
    )
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job, tracks=tracks)
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=None)
    with TestClient(app) as client:
        r = client.get(f"/api/jobs/{JOB_ID}/identity", headers=_auth(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["pin"] == {"episode": "episodes_tmdb"}
    assert body["sources"]["episodes_tmdb"]["suggestion"] is True
    track_1 = next(t for t in body["tracks"] if t["source_ref"] == "1")
    assert track_1["proposals"]["episodes_tmdb"]["episode"] == 3


def test_get_identity_unknown_job_404(signing_key: bytes) -> None:
    db = _db()
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=None)
    with TestClient(app) as client:
        r = client.get(f"/api/jobs/{JOB_ID}/identity", headers=_auth(admin_token))
    assert r.status_code == 404


# --- POST /identity/match ------------------------------------------------------


def test_match_preview_writes_nothing(signing_key: bytes) -> None:
    job = _job()
    before = copy.deepcopy(job.metadata_json)
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job, tracks=tracks)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    hub = _Hub()
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, hub=hub, stage_runner=runner)

    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{JOB_ID}/identity/match", json={"apply": False}, headers=_auth(admin_token))

    assert r.status_code == 200
    body = r.json()
    outcome = next(o for o in body["outcomes"] if o["source_id"] == "episodes_tmdb")
    assert outcome["status"] == "ok"
    assert len(outcome["matches"]) == len(DISC)
    assert outcome["score"] is not None
    # Nothing WRITTEN: no emit, metadata_json byte-identical, no stored
    # claims. F6: a harmless commit (nothing dirty) ends the read
    # transaction before the provider round-trip -- `committed` ticks up by
    # one, but that alone writes no data.
    assert db.committed == 1
    assert db.expire_all_calls == 0  # F1 only matters on the apply path
    assert hub.events == []
    assert job.metadata_json == before
    assert claims_of(job).sources == {}
    assert runner.invalidate_calls == []  # only apply=True invalidates


def test_match_preview_miss_outcome_has_no_score(signing_key: bytes) -> None:
    job = _job()
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job, tracks=tracks)
    provider = FakeProvider(show_id=None)  # miss: no show id resolvable
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)

    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{JOB_ID}/identity/match", json={"apply": False}, headers=_auth(admin_token))

    assert r.status_code == 200
    outcome = next(o for o in r.json()["outcomes"] if o["source_id"] == "episodes_tmdb")
    assert outcome["status"] == "miss"
    assert outcome["score"] is None
    assert outcome["matches"] == []


@pytest.mark.parametrize("tolerance", [0, 1801])
def test_match_tolerance_out_of_range_422(signing_key: bytes, tolerance: int) -> None:
    job = _job()
    db = _db(job, tracks=[_track(job.id, i, s) for i, s in enumerate(DISC)])
    runner = _FakeStageRunner([FakeProvider(seasons={1: _season(1, DISTINCT)})])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.post(
            f"/api/jobs/{JOB_ID}/identity/match",
            json={"apply": False, "tolerance": tolerance},
            headers=_auth(admin_token),
        )
    assert r.status_code == 422


def test_match_apply_without_source_stores_claims_no_pin(signing_key: bytes) -> None:
    job = _job()  # metadata: imdb only -- tmdb gets newly resolved
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job, tracks=tracks)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)}, show_id="100")
    hub = _Hub()
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, hub=hub, stage_runner=runner)

    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{JOB_ID}/identity/match", json={"apply": True}, headers=_auth(admin_token))

    assert r.status_code == 200
    assert claims_of(job).sources["episodes_tmdb"].status == "ok"
    assert claims_of(job).pin == {}
    assert db.committed >= 1
    assert any(e["event_type"] == "job.identity_updated" for e in hub.events)
    assert any(e["event_type"] == "track.updated" for e in hub.events)
    assert runner.invalidate_calls == [JOB_ID]
    body = r.json()
    outcome = next(o for o in body["outcomes"] if o["source_id"] == "episodes_tmdb")
    assert outcome["status"] == "ok"
    # F2: `found_ids_from_outcomes` + `merge_new_ids` persisted the show id
    # this compute resolved onto the (fresh-reselected) job.
    assert job.metadata_json["identity"]["external_ids"]["tmdb"] == "100"
    assert job.metadata_json["identity"]["external_ids"]["imdb"] == "tt1"  # untouched


def test_match_apply_with_a_miss_outcome_merges_no_ids(signing_key: bytes) -> None:
    """`found_ids_from_outcomes` skips an outcome with no `show_id` in its
    inputs (a miss never got that far) -- applying still succeeds, storing
    the miss, without merging a bogus id."""
    job = _job()
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job, tracks=tracks)
    provider = FakeProvider(show_id=None)  # miss: no show id resolvable
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)

    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{JOB_ID}/identity/match", json={"apply": True}, headers=_auth(admin_token))

    assert r.status_code == 200
    assert claims_of(job).sources["episodes_tmdb"].status == "miss"
    assert "tmdb" not in job.metadata_json["identity"]["external_ids"]


def test_match_apply_expires_before_the_fresh_reselect(signing_key: bytes) -> None:
    """F1: `db.expire_all()` runs before the `with_for_update` re-select, so
    that re-select (and `resolve_job`'s own track re-select right after it)
    re-read current rows instead of diffing stale copies loaded before the
    provider round-trip."""
    job = _job()
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job, tracks=tracks)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)

    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{JOB_ID}/identity/match", json={"apply": True}, headers=_auth(admin_token))

    assert r.status_code == 200
    assert db.expire_all_calls == 1
    expire_idx = db.call_log.index("expire_all")
    assert db.call_log[expire_idx + 1] == "execute"  # ordered right before the fresh re-select


def test_match_apply_with_source_pins_and_survives_forced_suggestion(signing_key: bytes) -> None:
    """F4/F5: force every computed outcome to `suggestion=True`
    (`episode_auto_apply` off) and prove pinning still applies it -- the
    RESOLVER (Task 9 F4 round 2) lets a pinned "ok" source's suggestion
    through. The stored claims AND the response both keep the computed
    `suggestion=True` unchanged; the proof that it was actually applied
    (not merely proposed) is the track's `episode_number`."""
    job = _job()
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job, tracks=tracks, cfg=Config(id=1, episode_auto_apply=False))
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    hub = _Hub()
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, hub=hub, stage_runner=runner)

    with TestClient(app) as client:
        r = client.post(
            f"/api/jobs/{JOB_ID}/identity/match",
            json={"apply": True, "source": "tmdb"},
            headers=_auth(admin_token),
        )

    assert r.status_code == 200
    claims = claims_of(job)
    assert claims.pin == {"episode": "episodes_tmdb"}
    assert claims.sources["episodes_tmdb"].status == "ok"
    assert claims.sources["episodes_tmdb"].suggestion is True  # unchanged -- nothing forces it
    track_0 = next(t for t in db.rows["tracks"] if t.source_ref == "0")
    assert track_0.episode_number is not None  # actually applied, not just proposed
    body = r.json()
    outcome = next(o for o in body["outcomes"] if o["source_id"] == "episodes_tmdb")
    assert outcome["suggestion"] is True


def test_pin_then_unpin_reverts_tracks_and_emits_track_updated(signing_key: bytes) -> None:
    """End to end (Task 9 F4 round 2): pin-apply a forced suggestion via
    `/identity/match`, then `DELETE /identity/pin`. Nothing else claims these
    tracks, so they revert immediately (episode_number cleared), and
    `track.updated` fires for every track the resolver reverted."""
    job = _job()
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job, tracks=tracks, cfg=Config(id=1, episode_auto_apply=False))
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    hub = _Hub()
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, hub=hub, stage_runner=runner)

    with TestClient(app) as client:
        r = client.post(
            f"/api/jobs/{JOB_ID}/identity/match",
            json={"apply": True, "source": "tmdb"},
            headers=_auth(admin_token),
        )
    assert r.status_code == 200
    applied_track_ids = {t.id for t in db.rows["tracks"] if t.episode_number is not None}
    assert applied_track_ids == {t.id for t in tracks}  # sanity: the pinned apply wrote every track

    hub.events.clear()  # only the unpin's own events matter below

    with TestClient(app) as client:
        r = client.delete(f"/api/jobs/{JOB_ID}/identity/pin", headers=_auth(admin_token))

    assert r.status_code == 200
    assert claims_of(job).pin == {}
    assert all(t.episode_number is None for t in db.rows["tracks"])  # reverted: no other source claims them

    identity_events = [e for e in hub.events if e["event_type"] == "job.identity_updated"]
    assert len(identity_events) == 1
    track_events = {e["payload"]["track_id"] for e in hub.events if e["event_type"] == "track.updated"}
    assert track_events == applied_track_ids


def test_match_apply_persists_season_disc_and_tolerance_i3(signing_key: bytes) -> None:
    """I3: the operator's `/match` season and disc number become manual job
    claims, and the tolerance is kept in the pinned source's stored inputs,
    so a later background run with default options reuses all three: it
    matches season 3 disc 2 without scanning, at the same tolerance, and its
    inputs equal the stored ones (C7)."""
    job = _job(season=None)
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job, tracks=tracks)
    provider = FakeProvider(seasons={1: _season(1, [6010] * 10), 3: _season(3, DISTINCT)})
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)

    with TestClient(app) as client:
        r = client.post(
            f"/api/jobs/{JOB_ID}/identity/match",
            json={"apply": True, "source": "tmdb", "season": 3, "disc_number": 2, "tolerance": 400},
            headers=_auth(admin_token),
        )

    assert r.status_code == 200
    manual = claims_of(job).sources["manual"].job
    assert (manual.season, manual.disc_number) == (3, 2)
    assert (job.season, job.disc_number) == (3, 2)
    assert job.identity_provenance is not None
    assert job.identity_provenance["season"] == "manual"
    stored_inputs = claims_of(job).sources["episodes_tmdb"].inputs
    assert stored_inputs["tolerance"] == 400

    provider.calls.clear()
    [outcome], _ = asyncio.run(
        episode_stage.run_episode_stage(db, job, [provider], CFG, episode_stage.StageOptions())  # type: ignore[arg-type]
    )
    assert "seasons" not in provider.calls
    assert outcome.claims.inputs == stored_inputs
    assert (outcome.claims.inputs["season"], outcome.claims.inputs["disc_number"]) == (3, 2)


def test_match_apply_season_equal_to_a_scan_picked_season_is_still_manual_i3(signing_key: bytes) -> None:
    """A season the operator restates over one an episode source picked by
    scanning is still recorded: otherwise the next background run would
    scan again (F1 treats a stage-set season as unknown)."""
    job = _job(season=1)
    job.identity_provenance = {"season": "episodes_tmdb"}
    db = _db(job, tracks=[_track(job.id, i, s) for i, s in enumerate(DISC)])
    runner = _FakeStageRunner([FakeProvider(seasons={1: _season(1, DISTINCT)})])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.post(
            f"/api/jobs/{JOB_ID}/identity/match",
            json={"apply": True, "source": "tmdb", "season": 1},
            headers=_auth(admin_token),
        )
    assert r.status_code == 200
    assert claims_of(job).sources["manual"].job.season == 1
    assert job.identity_provenance is not None
    assert job.identity_provenance["season"] == "manual"


def test_match_apply_without_choices_records_no_manual_claims(signing_key: bytes) -> None:
    job = _job()
    db = _db(job, tracks=[_track(job.id, i, s) for i, s in enumerate(DISC)])
    runner = _FakeStageRunner([FakeProvider(seasons={1: _season(1, DISTINCT)})])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.post(
            f"/api/jobs/{JOB_ID}/identity/match", json={"apply": True, "source": "tmdb"}, headers=_auth(admin_token)
        )
    assert r.status_code == 200
    assert "manual" not in claims_of(job).sources
    assert claims_of(job).sources["episodes_tmdb"].inputs["tolerance"] == 300


def test_match_unknown_job_404(signing_key: bytes) -> None:
    db = _db()
    runner = _FakeStageRunner([FakeProvider()])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{JOB_ID}/identity/match", json={"apply": False}, headers=_auth(admin_token))
    assert r.status_code == 404


def test_match_works_on_a_non_tv_job_m4(signing_key: bytes) -> None:
    """M4 (spec 5): the manual match works on any job, TV or not; only the
    background stage is gated on a TV candidate."""
    job = _job(media_type=MediaType.MOVIE)
    db = _db(job, tracks=[_track(job.id, i, s) for i, s in enumerate(DISC)])
    runner = _FakeStageRunner([FakeProvider(seasons={1: _season(1, DISTINCT)})])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{JOB_ID}/identity/match", json={"apply": False}, headers=_auth(admin_token))
    assert r.status_code == 200
    outcome = next(o for o in r.json()["outcomes"] if o["source_id"] == "episodes_tmdb")
    assert outcome["status"] == "ok"


@pytest.mark.parametrize("body", [{"season": -1}, {"disc_number": 0}, {"disc_number": -2}])
def test_match_out_of_range_season_or_disc_422_m6(signing_key: bytes, body: dict[str, int]) -> None:
    job = _job()
    db = _db(job, tracks=[_track(job.id, i, s) for i, s in enumerate(DISC)])
    runner = _FakeStageRunner([FakeProvider(seasons={1: _season(1, DISTINCT)})])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{JOB_ID}/identity/match", json={"apply": False, **body}, headers=_auth(admin_token))
    assert r.status_code == 422


def test_match_season_zero_and_disc_one_are_valid_m6(signing_key: bytes) -> None:
    job = _job()
    db = _db(job, tracks=[_track(job.id, i, s) for i, s in enumerate(DISC)])
    runner = _FakeStageRunner([FakeProvider(seasons={0: _season(0, DISTINCT)})])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.post(
            f"/api/jobs/{JOB_ID}/identity/match",
            json={"apply": False, "season": 0, "disc_number": 1},
            headers=_auth(admin_token),
        )
    assert r.status_code == 200


def test_match_no_stage_runner_503(signing_key: bytes) -> None:
    job = _job()
    db = _db(job, tracks=[_track(job.id, i, s) for i, s in enumerate(DISC)])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=None)
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{JOB_ID}/identity/match", json={"apply": False}, headers=_auth(admin_token))
    assert r.status_code == 503


def test_match_reader_cannot_post_403(signing_key: bytes) -> None:
    job = _job()
    db = _db(job, tracks=[_track(job.id, i, s) for i, s in enumerate(DISC)])
    runner = _FakeStageRunner([FakeProvider(seasons={1: _season(1, DISTINCT)})])
    app, _, guest_token = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{JOB_ID}/identity/match", json={"apply": False}, headers=_auth(guest_token))
    assert r.status_code == 403


# --- DELETE /identity/pin -------------------------------------------------------


def test_clear_pin_removes_existing_pin(signing_key: bytes) -> None:
    job = _job(
        meta={
            "identity": {"external_ids": {"imdb": "tt1"}},
            "identity_claims": {
                "sources": {"episodes_tmdb": {"status": "ok", "suggestion": False}},
                "pin": {"episode": "episodes_tmdb"},
            },
        }
    )
    db = _db(job, tracks=[_track(job.id, i, s) for i, s in enumerate(DISC)])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=None)

    with TestClient(app) as client:
        r = client.delete(f"/api/jobs/{JOB_ID}/identity/pin", headers=_auth(admin_token))

    assert r.status_code == 200
    assert claims_of(job).pin == {}
    assert r.json()["pin"] == {}
    assert db.locked == ["jobs"]  # M2: the job row is locked before resolving


def test_clear_pin_emits_identity_updated_and_track_updated(signing_key: bytes) -> None:
    """F3: spec 7 requires `job.identity_updated` whenever the resolver
    changes anything, not only when `/identity/match` supplied fresh
    outcomes. Here the stored "ok" claims were never yet applied to the
    tracks -- clearing the pin still runs `resolve_job`, which applies them
    for the first time, so both events must fire."""
    job = _job(
        meta={
            "identity": {"external_ids": {"imdb": "tt1"}},
            "identity_claims": {
                "sources": {
                    "episodes_tmdb": {
                        "status": "ok",
                        "suggestion": False,
                        "tracks": {"0": {"role": "episode", "season": 1, "episode": 3, "episode_name": "Ep3"}},
                    }
                },
                "pin": {"episode": "episodes_tmdb"},
            },
        }
    )
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job, tracks=tracks)
    hub = _Hub()
    app, admin_token, _ = _make_app(signing_key, db, hub=hub, stage_runner=None)

    with TestClient(app) as client:
        r = client.delete(f"/api/jobs/{JOB_ID}/identity/pin", headers=_auth(admin_token))

    assert r.status_code == 200
    identity_events = [e for e in hub.events if e["event_type"] == "job.identity_updated"]
    assert len(identity_events) == 1
    assert identity_events[0]["payload"] == {"job_id": JOB_ID, "sources": {}}
    track_events = [e for e in hub.events if e["event_type"] == "track.updated"]
    assert any(e["payload"]["track_id"] == tracks[0].id for e in track_events)
    track_0 = next(t for t in db.rows["tracks"] if t.source_ref == "0")
    assert track_0.episode_number == 3


def test_clear_pin_when_nothing_pinned_is_a_noop(signing_key: bytes) -> None:
    job = _job()
    db = _db(job, tracks=[_track(job.id, i, s) for i, s in enumerate(DISC)])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=None)

    with TestClient(app) as client:
        r = client.delete(f"/api/jobs/{JOB_ID}/identity/pin", headers=_auth(admin_token))

    assert r.status_code == 200
    assert claims_of(job).pin == {}


def test_clear_pin_unknown_job_404(signing_key: bytes) -> None:
    db = _db()
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=None)
    with TestClient(app) as client:
        r = client.delete(f"/api/jobs/{JOB_ID}/identity/pin", headers=_auth(admin_token))
    assert r.status_code == 404


def test_clear_pin_reader_forbidden_403(signing_key: bytes) -> None:
    job = _job()
    db = _db(job, tracks=[_track(job.id, i, s) for i, s in enumerate(DISC)])
    app, _, guest_token = _make_app(signing_key, db, stage_runner=None)
    with TestClient(app) as client:
        r = client.delete(f"/api/jobs/{JOB_ID}/identity/pin", headers=_auth(guest_token))
    assert r.status_code == 403


# --- GET /identity/episodes ------------------------------------------------------


def test_episodes_browse_happy_path(signing_key: bytes) -> None:
    job = _job()
    db = _db(job)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)

    with TestClient(app) as client:
        r = client.get(
            f"/api/jobs/{JOB_ID}/identity/episodes",
            params={"source": "tmdb", "season": 1},
            headers=_auth(admin_token),
        )

    assert r.status_code == 200
    body = r.json()
    assert body["source_id"] == "episodes_tmdb"
    assert body["show_id"] == "100"
    assert body["season"] == 1
    assert len(body["episodes"]) == len(DISTINCT)
    assert body["episodes"][0]["number"] == 1


def test_episodes_browse_unknown_job_404(signing_key: bytes) -> None:
    db = _db()
    runner = _FakeStageRunner([FakeProvider()])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.get(
            f"/api/jobs/{JOB_ID}/identity/episodes",
            params={"source": "tmdb", "season": 1},
            headers=_auth(admin_token),
        )
    assert r.status_code == 404


def test_episodes_browse_no_stage_runner_503(signing_key: bytes) -> None:
    job = _job()
    db = _db(job)
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=None)
    with TestClient(app) as client:
        r = client.get(
            f"/api/jobs/{JOB_ID}/identity/episodes",
            params={"source": "tmdb", "season": 1},
            headers=_auth(admin_token),
        )
    assert r.status_code == 503


def test_episodes_browse_no_show_id_404(signing_key: bytes) -> None:
    """F7: no id cached (the job's metadata only has `imdb`), so
    `resolve_show_id` is called directly; it returns `None` -> 404."""
    job = _job()
    db = _db(job)
    provider = FakeProvider(show_id=None)
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.get(
            f"/api/jobs/{JOB_ID}/identity/episodes",
            params={"source": "tmdb", "season": 1},
            headers=_auth(admin_token),
        )
    assert r.status_code == 404
    assert "resolve_show_id" in provider.calls


def test_episodes_browse_uses_cached_id_skips_resolve_show_id(signing_key: bytes) -> None:
    """F7: when the id is already cached, `resolve_show_id` is never called."""
    job = _job(meta={"identity": {"external_ids": {"imdb": "tt1", "tmdb": "cached-100"}}})
    db = _db(job)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.get(
            f"/api/jobs/{JOB_ID}/identity/episodes",
            params={"source": "tmdb", "season": 1},
            headers=_auth(admin_token),
        )
    assert r.status_code == 200
    assert r.json()["show_id"] == "cached-100"
    assert "resolve_show_id" not in provider.calls


def test_episodes_browse_resolve_show_id_miss_404(signing_key: bytes) -> None:
    """F7: `resolve_show_id` raising `SourceMiss` (not just returning `None`)
    is also a 404, not a 502 -- it's a definitive "no such show", not a
    transient failure."""
    job = _job()
    db = _db(job)
    provider = FakeProvider(resolve_error=SourceMiss("no such show"))
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.get(
            f"/api/jobs/{JOB_ID}/identity/episodes",
            params={"source": "tmdb", "season": 1},
            headers=_auth(admin_token),
        )
    assert r.status_code == 404


def test_episodes_browse_resolve_show_id_source_error_502(signing_key: bytes) -> None:
    """F7: a transient failure resolving the show id (not yet cached) is a
    502 naming the provider, not a misleading 404."""
    job = _job()
    db = _db(job)
    provider = FakeProvider(resolve_error=SourceError("timeout"))
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.get(
            f"/api/jobs/{JOB_ID}/identity/episodes",
            params={"source": "tmdb", "season": 1},
            headers=_auth(admin_token),
        )
    assert r.status_code == 502
    assert "tmdb" in r.json()["detail"]


def test_episodes_browse_configured_reason_409(signing_key: bytes) -> None:
    job = _job()
    db = _db(job)
    provider = FakeProvider(configured_reason="no TMDb key")
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.get(
            f"/api/jobs/{JOB_ID}/identity/episodes",
            params={"source": "tmdb", "season": 1},
            headers=_auth(admin_token),
        )
    assert r.status_code == 409
    assert "no TMDb key" in r.json()["detail"]


def test_episodes_browse_backing_off_503(signing_key: bytes) -> None:
    job = _job()
    db = _db(job)
    provider = FakeProvider(backing_off=True)
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.get(
            f"/api/jobs/{JOB_ID}/identity/episodes",
            params={"source": "tmdb", "season": 1},
            headers=_auth(admin_token),
        )
    assert r.status_code == 503


def test_episodes_browse_season_miss_404(signing_key: bytes) -> None:
    job = _job()
    db = _db(job)
    provider = FakeProvider(seasons={})  # season 1 not present -> SourceMiss
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.get(
            f"/api/jobs/{JOB_ID}/identity/episodes",
            params={"source": "tmdb", "season": 1},
            headers=_auth(admin_token),
        )
    assert r.status_code == 404


def test_episodes_browse_source_error_502(signing_key: bytes) -> None:
    job = _job()
    db = _db(job)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)}, error=SourceError("timeout"))
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.get(
            f"/api/jobs/{JOB_ID}/identity/episodes",
            params={"source": "tmdb", "season": 1},
            headers=_auth(admin_token),
        )
    assert r.status_code == 502
    assert "tmdb" in r.json()["detail"]


@pytest.mark.parametrize("where", ["season", "resolve_show_id"])
def test_episodes_browse_unexpected_exception_502(
    signing_key: bytes, where: str, caplog: pytest.LogCaptureFixture
) -> None:
    """M1: any unexpected provider exception maps to 502, logged with its
    traceback, instead of a 500."""
    job = _job(meta={})  # no cached show id: resolve_show_id runs
    db = _db(job)
    if where == "season":
        provider = FakeProvider(seasons={1: _season(1, DISTINCT)}, error=RuntimeError("boom"))
    else:
        provider = FakeProvider(resolve_error=RuntimeError("boom"))
    runner = _FakeStageRunner([provider])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.get(
            f"/api/jobs/{JOB_ID}/identity/episodes",
            params={"source": "tmdb", "season": 1},
            headers=_auth(admin_token),
        )
    assert r.status_code == 502
    assert r.json()["detail"] == "tmdb: unexpected error"
    assert "Traceback" in caplog.text
