"""Identification settings on the Config singleton (spec 2026-10-14 PR 1)."""

from __future__ import annotations

import os
import secrets

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import config as config_router  # noqa: E402
from arm_backend.seeders import CONFIG_SINGLETON_ID  # noqa: E402
from arm_common import Config, RetentionPolicy, User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession, **overrides: object) -> Config:
    row = Config(
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
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    db.rows["config"] = [row]
    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )
    return row


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(config_router.router)

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_config_view_exposes_the_identification_settings(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        body = client.get("/api/config", headers=_auth(token)).json()
    assert body["movie_sources"] == ["tmdb", "omdb"]
    assert body["music_sources"] == ["musicbrainz"]
    assert body["search_provider_movie"] == "tmdb"
    assert body["search_provider_tv"] == "tmdb"
    assert body["search_provider_music"] == "musicbrainz"
    assert body["movie_auto_apply"] is True
    assert body["music_auto_apply"] is True
    assert body["crc64service_enabled"] is True
    assert "metadata_provider" not in body


def test_config_view_defaults_when_the_new_columns_are_none(signing_key: bytes) -> None:
    db = FakeSession()
    row = _seed(db)
    for key in (
        "movie_sources",
        "music_sources",
        "search_provider_movie",
        "search_provider_tv",
        "search_provider_music",
        "movie_auto_apply",
        "music_auto_apply",
        "crc64service_enabled",
    ):
        setattr(row, key, None)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/config", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["movie_sources"] == ["tmdb", "omdb"]
    assert body["search_provider_music"] == "musicbrainz"
    assert body["crc64service_enabled"] is True


def test_patch_ranked_lists_and_toggles(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tmdb_api_key="k", omdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/config",
            json={
                "movie_sources": ["omdb", "tmdb"],
                "music_sources": [],
                "crc64service_enabled": False,
            },
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["movie_sources"] == ["omdb", "tmdb"]
    assert body["music_sources"] == []
    assert body["crc64service_enabled"] is False
    row = db.rows["config"][0]
    assert row.movie_sources == ["omdb", "tmdb"] and row.crc64service_enabled is False


def test_patch_auto_apply_toggles_false_round_trip(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/config",
            json={"movie_auto_apply": False, "music_auto_apply": False},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["movie_auto_apply"] is False
    assert body["music_auto_apply"] is False
    row = db.rows["config"][0]
    assert row.movie_auto_apply is False and row.music_auto_apply is False


@pytest.mark.parametrize("key", ["movie_auto_apply", "music_auto_apply"])
def test_patch_auto_apply_toggle_null_is_rejected(signing_key: bytes, key: str) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/config", json={key: None}, headers=_auth(token))
    assert r.status_code == 400
    assert r.json()["detail"] == f"{key} must be true or false"


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"movie_sources": ["tmdb", "netflix"]}, "movie_sources: unknown value(s) netflix"),
        ({"movie_sources": ["tmdb", "tmdb"]}, "movie_sources: duplicate values"),
        ({"music_sources": None}, "music_sources must be a list"),
        ({"search_provider_movie": "netflix"}, "search_provider_movie must be one of tmdb, omdb"),
        ({"search_provider_movie": None}, "search_provider_movie must be one of tmdb, omdb"),
        ({"search_provider_music": "spotify"}, "search_provider_music must be one of musicbrainz"),
        ({"crc64service_enabled": None}, "crc64service_enabled must be true or false"),
    ],
)
def test_patch_rejects_bad_identification_settings(signing_key: bytes, body: dict, detail: str) -> None:
    db = FakeSession()
    _seed(db, tmdb_api_key="k", omdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/config", json=body, headers=_auth(token))
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == detail


def test_patch_search_provider_needs_its_key(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tmdb_api_key="k", omdb_api_key=None)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/config", json={"search_provider_movie": "omdb"}, headers=_auth(token))
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "search_provider_movie: OMDb needs its API key"
        # The key sent in the same body counts (review focus 2).
        r = client.patch(
            "/api/config", json={"search_provider_movie": "omdb", "omdb_api_key": "new-k"}, headers=_auth(token)
        )
        assert r.status_code == 200, r.text
        assert r.json()["search_provider_movie"] == "omdb"
        # A keyless choice needs no key even when no key is stored.
        r = client.patch("/api/config", json={"search_provider_music": "musicbrainz"}, headers=_auth(token))
        assert r.status_code == 200, r.text
        r = client.patch("/api/config", json={"search_provider_tv": "tvdb"}, headers=_auth(token))
        assert r.status_code == 400, r.text
        assert r.json()["detail"] == "search_provider_tv: TVDB needs its API key"
        r = client.patch("/api/config", json={"search_provider_tv": "tvdb", "tvdb_api_key": "k"}, headers=_auth(token))
        assert r.status_code == 200, r.text
        r = client.patch("/api/config", json={"search_provider_tv": "tvmaze"}, headers=_auth(token))
        assert r.status_code == 200, r.text


def test_patch_search_provider_rejects_a_key_cleared_in_the_same_body(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tmdb_api_key="k", omdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/config", json={"search_provider_movie": "omdb", "omdb_api_key": ""}, headers=_auth(token)
        )
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "search_provider_movie: OMDb needs its API key"


def test_patch_ranked_lists_do_not_require_keys(signing_key: bytes) -> None:
    """A ranked list may name an unkeyed source: the registry skips it at run
    time and the UI shows the "Needs key" chip (same rule as episode_sources)."""
    db = FakeSession()
    _seed(db, tmdb_api_key=None, omdb_api_key=None)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/config", json={"movie_sources": ["omdb", "tmdb"]}, headers=_auth(token))
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("key", ["movie_sources", "music_sources"])
def test_changing_the_new_lists_re_resolves_live_jobs(
    signing_key: bytes, monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    db = FakeSession()
    _seed(db)
    resolved: list[str] = []

    async def fake_reresolve(session, request):  # type: ignore[no-untyped-def]
        resolved.append(key)

    monkeypatch.setattr(config_router, "_reresolve_identity", fake_reresolve)
    app, token = _make_app(signing_key, db)
    body = {key: ["omdb"] if key == "movie_sources" else []}
    with TestClient(app) as client:
        r = client.patch("/api/config", json=body, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert resolved == [key]


def test_patch_config_rejects_non_editable_key(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        # MEDIA_ROOT is an infra (non-editable) key; forcing it into the body must 400
        r = c.patch("/api/config", json={"MEDIA_ROOT": "/evil"}, headers=_auth(token))
    assert r.status_code == 400, r.text


def test_config_view_exposes_makemkv_status(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    row = db.rows["config"][0]
    row.makemkv_key_valid = True
    row.makemkv_key_state = "valid"
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/config", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["makemkv_key_valid"] is True
    assert body["makemkv_key_state"] == "valid"
    assert "makemkv_key_checked_at" in body
