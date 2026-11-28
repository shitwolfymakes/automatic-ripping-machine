"""miss_media_type / miss_titles_kept: the Defaults settings for an unidentified disc."""

from __future__ import annotations

import secrets

from fastapi import FastAPI
from fastapi.testclient import TestClient

from arm_backend.db import get_session
from arm_backend.jwt_utils import issue_access_token
from arm_backend.routers import config as config_router
from arm_common import Config, RetentionPolicy, MissMediaType, MissTitlesKept, User
from tests._fakes import FakeSession
from tests.test_migration_chain import _render_sql

_PARENT = "0058_iso_name_hint_source"
_REV = "0059_miss_defaults"


def _client(db: FakeSession) -> tuple[TestClient, dict[str, str]]:
    key = secrets.token_bytes(32)
    app = FastAPI()
    app.state.signing_key = key
    app.include_router(config_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )
    token, _ = issue_access_token("usr_admin", "admin", key)
    return TestClient(app), {"Authorization": f"Bearer {token}"}


def _db() -> FakeSession:
    db = FakeSession()
    db.rows["config"] = [
        Config(
            id=1,
            auto_transcode_on_idle=False,
            auto_rip_on_insert=True,
            block_on_miss=True,
            ripping_paused=False,
            thediscdb_enabled=False,
            manual_wait_seconds=60,
            default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
            notification_apprise_urls=[],
            notifications_enabled=False,
        )
    ]
    return db


def test_config_defaults_to_movie_and_all_when_the_columns_are_unset() -> None:
    client, auth = _client(_db())
    with client:
        body = client.get("/api/config", headers=auth).json()
    assert (body["miss_media_type"], body["miss_titles_kept"]) == ("movie", "all")


def test_config_patch_accepts_valid_values_and_rejects_others() -> None:
    client, auth = _client(_db())
    with client:
        r = client.patch("/api/config", json={"miss_media_type": "tv", "miss_titles_kept": "preset"}, headers=auth)
        assert r.status_code == 200
        assert (r.json()["miss_media_type"], r.json()["miss_titles_kept"]) == ("tv", "preset")
        assert client.patch("/api/config", json={"miss_media_type": "cd"}, headers=auth).status_code == 422
        assert client.patch("/api/config", json={"miss_titles_kept": "some"}, headers=auth).status_code == 422


def test_enums_carry_the_wire_values() -> None:
    assert [m.value for m in MissMediaType] == ["movie", "tv"]
    assert [m.value for m in MissTitlesKept] == ["all", "preset"]


def test_0059_adds_both_columns_with_their_defaults() -> None:
    sql = _render_sql(_PARENT, _REV)
    assert "ALTER TABLE config ADD COLUMN miss_media_type VARCHAR DEFAULT 'movie' NOT NULL" in sql
    assert "ALTER TABLE config ADD COLUMN miss_titles_kept VARCHAR DEFAULT 'all' NOT NULL" in sql
    assert "CREATE TYPE" not in sql


def test_0059_downgrade_drops_both_columns() -> None:
    sql = _render_sql(_REV, _PARENT, downgrade=True)
    assert "ALTER TABLE config DROP COLUMN miss_media_type" in sql
    assert "ALTER TABLE config DROP COLUMN miss_titles_kept" in sql


def test_0059_matches_the_model() -> None:
    cols = Config.__table__.columns
    assert not cols["miss_media_type"].nullable
    assert cols["miss_media_type"].server_default.arg == "movie"
    assert cols["miss_titles_kept"].server_default.arg == "all"
