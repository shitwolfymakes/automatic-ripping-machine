"""GET /api/config masks secret-tier fields with HIDDEN_SECRET.

Non-set (None) secrets remain None; set secrets become '<hidden>'.
The secret-key set is derived from the registry, not hardcoded.
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
from arm_backend.seeders import CONFIG_SINGLETON_ID  # noqa: E402
from arm_common import Config, RetentionPolicy, User  # noqa: E402
from arm_common.secrets import HIDDEN_SECRET  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession, **kwargs) -> None:
    row = Config(
        id=CONFIG_SINGLETON_ID,
        tmdb_api_key=kwargs.pop("tmdb_api_key", None),
        omdb_api_key=kwargs.pop("omdb_api_key", None),
        makemkv_key=kwargs.pop("makemkv_key", None),
        musicbrainz_user_agent=None,
        auto_transcode_on_idle=False,
        auto_rip_on_insert=True,
        block_on_miss=True,
        default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
        notification_apprise_urls=[],
        notifications_enabled=False,
        metadata_provider="tmdb",
    )
    for k, v in kwargs.items():
        setattr(row, k, v)
    db.rows["config"] = [row]
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


def test_get_config_masks_set_secrets(signing_key):
    db = FakeSession()
    _seed(db, tmdb_api_key="sk-real", omdb_api_key="omdb-real", makemkv_key="M-real")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/config", headers=_auth(token))
    body = r.json()
    assert r.status_code == 200, r.text
    assert body["tmdb_api_key"] == HIDDEN_SECRET
    assert body["omdb_api_key"] == HIDDEN_SECRET
    assert body["makemkv_key"] == HIDDEN_SECRET
    assert body["metadata_provider"] != HIDDEN_SECRET  # non-secret never masked


def test_get_config_unset_secret_is_null_not_hidden(signing_key):
    db = FakeSession()
    _seed(db, tmdb_api_key=None)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/config", headers=_auth(token))
    assert r.json()["tmdb_api_key"] is None


def test_secret_keys_match_registry():
    from arm_backend.routers.config import _SECRET_KEYS
    from arm_common.config_metadata import CONFIG_FIELD_META
    from arm_common.schemas import ConfigView

    expected = {m.key for m in CONFIG_FIELD_META if m.tier == "secret"} & set(ConfigView.model_fields)
    assert _SECRET_KEYS == expected
    assert {"tmdb_api_key", "omdb_api_key", "makemkv_key"} <= _SECRET_KEYS
    assert "tvdb_api_key" not in _SECRET_KEYS  # not in ConfigView yet (B29)
