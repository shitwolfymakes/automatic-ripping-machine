"""Identity, match, pin and episode-browse endpoints (design spec 2026-09-28-
identity-sources, section 7; plan Task 9): happy paths for all four routes,
the preview/apply(+pin) split, 404/409/502, and the reader-write gate."""

from __future__ import annotations

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
    def backing_off(self) -> bool:
        return False


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
    ) -> None:
        self.source_id = source_id
        self.id_field = id_field
        self.http = FakeHttp()
        self._seasons = seasons or {}
        self._show_id = show_id
        self.error = error

    def configured(self, cfg: Config) -> str | None:
        return None

    async def resolve_show_id(self, ids: ExternalIds) -> str | None:
        return self._show_id

    async def seasons(self, show_id: str) -> list[int]:
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

    def providers(self, cfg: Config) -> list[Any]:
        self.provider_calls.append(cfg)
        return self._providers


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
    # Nothing written: no commit, no emit, metadata_json byte-identical.
    assert db.committed == 0
    assert hub.events == []
    assert job.metadata_json == before
    assert claims_of(job).sources == {}


def test_match_apply_without_source_stores_claims_no_pin(signing_key: bytes) -> None:
    job = _job()
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job, tracks=tracks)
    provider = FakeProvider(seasons={1: _season(1, DISTINCT)})
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
    body = r.json()
    outcome = next(o for o in body["outcomes"] if o["source_id"] == "episodes_tmdb")
    assert outcome["status"] == "ok"


def test_match_apply_with_source_pins_and_clears_suggestion(signing_key: bytes) -> None:
    job = _job()
    tracks = [_track(job.id, i, s) for i, s in enumerate(DISC)]
    db = _db(job, tracks=tracks)
    # EPISODE_AUTO_APPLY defaults suggestion True/False based on coverage etc.;
    # force a low-confidence-ish scenario is unnecessary -- what matters here is
    # that the OPERATOR's explicit source choice always clears `suggestion`.
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
    assert claims.sources["episodes_tmdb"].suggestion is False
    body = r.json()
    outcome = next(o for o in body["outcomes"] if o["source_id"] == "episodes_tmdb")
    assert outcome["suggestion"] is False


def test_match_unknown_job_404(signing_key: bytes) -> None:
    db = _db()
    runner = _FakeStageRunner([FakeProvider()])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{JOB_ID}/identity/match", json={"apply": False}, headers=_auth(admin_token))
    assert r.status_code == 404


def test_match_non_tv_candidate_409(signing_key: bytes) -> None:
    job = _job(media_type=MediaType.MOVIE)
    db = _db(job, tracks=[_track(job.id, 0, 5400)])
    runner = _FakeStageRunner([FakeProvider()])
    app, admin_token, _ = _make_app(signing_key, db, stage_runner=runner)
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{JOB_ID}/identity/match", json={"apply": False}, headers=_auth(admin_token))
    assert r.status_code == 409


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
