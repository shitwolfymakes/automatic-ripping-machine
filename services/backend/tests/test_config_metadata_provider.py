"""metadata_provider column on the Config singleton."""

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


def test_config_has_metadata_provider_field() -> None:
    cfg = Config(id=1)
    # Field(default="tmdb") fires in Python, so a bare in-memory Config already
    # carries "tmdb"; the DB-level server_default is the backup for raw INSERTs.
    assert cfg.metadata_provider == "tmdb"
    cfg.metadata_provider = "omdb"
    assert cfg.metadata_provider == "omdb"


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession, *, metadata_provider: str = "tmdb") -> None:
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
            metadata_provider=metadata_provider,
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


def test_config_view_exposes_metadata_provider(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/config", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["metadata_provider"] == "tmdb"


def test_config_patch_metadata_provider_ok(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/config", json={"metadata_provider": "omdb"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["metadata_provider"] == "omdb"
    assert db.rows["config"][0].metadata_provider == "omdb"


def test_config_patch_metadata_provider_rejects_invalid(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/config", json={"metadata_provider": "netflix"}, headers=_auth(token))
    assert r.status_code == 400
    assert "metadata_provider" in r.json()["detail"]


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
