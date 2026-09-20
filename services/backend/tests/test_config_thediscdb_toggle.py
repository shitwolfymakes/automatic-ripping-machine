"""thediscdb_enabled / thediscdb_refresh_days round-trip through GET/PATCH
/api/config.

CONFIG_FIELD_META registers both as operator-tier, editable=True — they must
therefore be patchable via ConfigUpdateRequest, mirroring the sibling
operator-tier bool `makemkv_sdf_enabled` (see test_config_tvdb_key.py for the
established round-trip pattern this follows).
"""

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
from arm_common import Config, RetentionPolicy, User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession) -> None:
    db.rows["config"] = [
        Config(
            id=1,
            tmdb_api_key=None,
            omdb_api_key=None,
            tvdb_api_key=None,
            musicbrainz_user_agent=None,
            auto_transcode_on_idle=False,
            auto_rip_on_insert=True,
            block_on_miss=True,
            thediscdb_enabled=True,
            thediscdb_refresh_days=7,
            default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
            notification_apprise_urls=[],
            notifications_enabled=False,
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


def test_get_config_reflects_thediscdb_enabled(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"][0].thediscdb_enabled = False
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/config", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["thediscdb_enabled"] is False


def test_thediscdb_enabled_round_trips(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        patched = c.patch("/api/config", json={"thediscdb_enabled": False}, headers=_auth(token))
        got = c.get("/api/config", headers=_auth(token))
    assert patched.status_code == 200, patched.text
    # The write stores the real value — the actual round-trip proof, true at every layer.
    assert db.rows["config"][0].thediscdb_enabled is False
    assert got.json()["thediscdb_enabled"] is False


def test_thediscdb_refresh_days_round_trips(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        patched = c.patch("/api/config", json={"thediscdb_refresh_days": 3}, headers=_auth(token))
        got = c.get("/api/config", headers=_auth(token))
    assert patched.status_code == 200, patched.text
    assert db.rows["config"][0].thediscdb_refresh_days == 3
    assert got.json()["thediscdb_refresh_days"] == 3
