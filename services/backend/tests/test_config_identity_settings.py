"""Identity settings (episode_sources, disc_hint_sources, episode_match_tolerance_seconds,
episode_auto_apply) on the config API: view defaults + PATCH validation."""

from __future__ import annotations

import os
import secrets

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import pytest  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import config as config_router  # noqa: E402
from arm_backend.seeders import CONFIG_SINGLETON_ID  # noqa: E402
from arm_common import Config, RetentionPolicy, User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession) -> None:
    db.rows["config"] = [
        Config(
            id=CONFIG_SINGLETON_ID,
            tmdb_api_key=None,
            omdb_api_key=None,
            musicbrainz_user_agent=None,
            auto_transcode_on_idle=False,
            auto_rip_on_insert=True,
            block_on_miss=True,
            default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
            notification_apprise_urls=[],
            notifications_enabled=False,
            metadata_provider="tmdb",
        )
    ]
    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(config_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _patch(client: TestClient, token: str, body: dict) -> object:
    return client.patch("/api/config", json=body, headers=_auth(token))


def _row(db: FakeSession) -> Config:
    return db.rows["config"][0]


def test_config_view_includes_identity_settings(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/config", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["episode_sources"] == ["tmdb", "tvmaze", "tvdb"]
    assert body["disc_hint_sources"] == ["bd_title", "label"]
    assert body["episode_match_tolerance_seconds"] == 300
    assert body["episode_auto_apply"] is True


def test_config_view_defaults_for_none_columns(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    row = _row(db)
    row.episode_sources = None
    row.disc_hint_sources = None
    row.episode_match_tolerance_seconds = None
    row.episode_auto_apply = None
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        body = client.get("/api/config", headers=_auth(token)).json()
    assert body["episode_sources"] == ["tmdb", "tvmaze", "tvdb"]
    assert body["disc_hint_sources"] == ["bd_title", "label"]
    assert body["episode_match_tolerance_seconds"] == 300
    assert body["episode_auto_apply"] is True


def test_patch_keeps_the_sent_order(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = _patch(client, token, {"episode_sources": ["tvdb", "tmdb"], "disc_hint_sources": []})
    assert r.status_code == 200, r.text
    assert r.json()["episode_sources"] == ["tvdb", "tmdb"]
    assert _row(db).disc_hint_sources == []


@pytest.mark.parametrize(
    "body",
    [
        {"episode_sources": ["tmdb", "anidb"]},
        {"episode_sources": ["tmdb", "tmdb"]},
        {"episode_sources": None},
        {"disc_hint_sources": ["label", "label"]},
        {"episode_match_tolerance_seconds": 0},
        {"episode_match_tolerance_seconds": 1801},
        {"episode_match_tolerance_seconds": None},
        {"episode_match_tolerance_seconds": True},
        {"episode_auto_apply": None},
    ],
)
def test_patch_rejects_bad_identity_settings(signing_key: bytes, body: dict) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        before = (
            list(_row(db).episode_sources),
            list(_row(db).disc_hint_sources),
            _row(db).episode_match_tolerance_seconds,
        )
        r = _patch(client, token, body)
        assert r.status_code == 400, r.text
        after = (
            list(_row(db).episode_sources),
            list(_row(db).disc_hint_sources),
            _row(db).episode_match_tolerance_seconds,
        )
    assert after == before


def test_patch_non_list_ranked_value_is_rejected(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = _patch(client, token, {"episode_sources": "tmdb"})
    assert r.status_code in (400, 422), r.text


def test_patch_tolerance_and_auto_apply(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = _patch(client, token, {"episode_match_tolerance_seconds": 90, "episode_auto_apply": False})
    assert r.status_code == 200, r.text
    assert (r.json()["episode_match_tolerance_seconds"], r.json()["episode_auto_apply"]) == (90, False)


def _identity_jobs(db: FakeSession) -> None:
    from arm_common import DiscType, Job, JobStatus, SessionApplication, SessionApplicationStatus

    db.rows["jobs"] = [
        Job(id="job_live", drive_id="d", disc_type=DiscType.DVD, status=JobStatus.AWAITING_REVIEW),
        Job(id="job_ripped_unapplied", drive_id="d", disc_type=DiscType.DVD, status=JobStatus.RIPPED),
        Job(id="job_ripped_applied", drive_id="d", disc_type=DiscType.DVD, status=JobStatus.RIPPED),
        Job(id="job_failed", drive_id="d", disc_type=DiscType.DVD, status=JobStatus.FAILED),
    ]
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_1", session_id="ses_x", job_id="job_ripped_applied", status=SessionApplicationStatus.DONE
        )
    ]


class _Stage:
    def __init__(self) -> None:
        self.scheduled: list[str] = []

    def schedule(self, job_id: str) -> None:
        self.scheduled.append(job_id)


@pytest.mark.parametrize("key", ["episode_sources", "disc_hint_sources"])
def test_changing_identity_sources_re_resolves_live_jobs(
    signing_key: bytes, monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    """D-097: the resolver reads the source settings only when it runs, so a
    change re-runs it (and the episode stage) for live jobs and for ripped
    jobs no session has been applied to yet; finished work is left alone."""
    db = FakeSession()
    _seed(db)
    _identity_jobs(db)
    resolved: list[str] = []

    async def fake_resolve(_session, job):  # type: ignore[no-untyped-def]
        from arm_backend.identity.pipeline import ResolveOutcome

        resolved.append(job.id)
        return ResolveOutcome(changed=0, track_ids=frozenset())

    monkeypatch.setattr(config_router, "resolve_job", fake_resolve)
    app, token = _make_app(signing_key, db)
    stage = _Stage()
    app.state.episode_stage = stage
    body = {"episode_sources": ["tvmaze"]} if key == "episode_sources" else {"disc_hint_sources": ["label"]}
    with TestClient(app) as client:
        r = _patch(client, token, body)
    assert r.status_code == 200, r.text  # type: ignore[attr-defined]
    assert sorted(resolved) == ["job_live", "job_ripped_unapplied"]
    assert sorted(stage.scheduled) == ["job_live", "job_ripped_unapplied"]


def test_identity_sources_patch_without_a_change_resolves_nothing(
    signing_key: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = FakeSession()
    _seed(db)
    _row(db).episode_sources = ["tvmaze"]
    _identity_jobs(db)
    resolved: list[str] = []

    async def fake_resolve(_session, job):  # type: ignore[no-untyped-def]
        resolved.append(job.id)

    monkeypatch.setattr(config_router, "resolve_job", fake_resolve)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = _patch(client, token, {"episode_sources": ["tvmaze"], "episode_auto_apply": False})
    assert r.status_code == 200, r.text  # type: ignore[attr-defined]
    assert resolved == []


def test_a_failing_re_resolve_never_fails_the_patch(signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSession()
    _seed(db)
    _identity_jobs(db)
    seen: list[str] = []

    async def boom(_session, job):  # type: ignore[no-untyped-def]
        seen.append(job.id)
        raise RuntimeError("db exploded")

    monkeypatch.setattr(config_router, "resolve_job", boom)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = _patch(client, token, {"disc_hint_sources": ["label"]})
    assert r.status_code == 200, r.text  # type: ignore[attr-defined]
    assert sorted(seen) == ["job_live", "job_ripped_unapplied"]  # one failure did not stop the next
    assert _row(db).disc_hint_sources == ["label"]


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"thediscdb_refresh_days": None}, "thediscdb_refresh_days must be a positive integer"),
        ({"thediscdb_refresh_days": 0}, "thediscdb_refresh_days must be a positive integer"),
        ({"manual_wait_seconds": None}, "manual_wait_seconds must be 0 or a positive integer"),
        ({"manual_wait_seconds": -5}, "manual_wait_seconds must be 0 or a positive integer"),
    ],
)
def test_not_null_int_settings_refuse_null_with_400(signing_key: bytes, body: dict, detail: str) -> None:
    """D-096: an emptied number input sends null; for a NOT NULL column that
    is a 400 the form can show, never an IntegrityError 500 on commit."""
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = _patch(client, token, body)
    assert r.status_code == 400  # type: ignore[attr-defined]
    assert r.json()["detail"] == detail  # type: ignore[attr-defined]


def test_manual_wait_seconds_accepts_zero(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = _patch(client, token, {"manual_wait_seconds": 0})
    assert r.status_code == 200, r.text  # type: ignore[attr-defined]
    assert _row(db).manual_wait_seconds == 0
