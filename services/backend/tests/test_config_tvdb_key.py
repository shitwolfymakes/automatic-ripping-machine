"""B29 — `tvdb_api_key` round-trips through GET/PATCH /api/config.

At the #6 layer there is no masking — the key is returned in cleartext,
mirroring the behaviour of the sibling provider keys (tmdb/omdb/makemkv).
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


def test_config_defaults_tvdb_api_key_to_none() -> None:
    cfg = Config(id=1)
    assert cfg.tvdb_api_key is None


def test_config_accepts_tvdb_api_key() -> None:
    cfg = Config(id=1, tvdb_api_key="tvdb-secret")
    assert cfg.tvdb_api_key == "tvdb-secret"


def test_tvdb_api_key_round_trips(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        patched = c.patch("/api/config", json={"tvdb_api_key": "tvdb-secret"}, headers=_auth(token))
        got = c.get("/api/config", headers=_auth(token))
    assert patched.status_code == 200, patched.text
    # The write stores the real value — the actual round-trip proof, true at every layer.
    assert db.rows["config"][0].tvdb_api_key == "tvdb-secret"
    # The field is exposed on the read view. Its GET value is cleartext at this early
    # config layer and masked ("<hidden>") once secret-masking lands higher in the stack,
    # so assert presence/non-empty (layer-agnostic), not a specific value.
    assert got.json()["tvdb_api_key"]
