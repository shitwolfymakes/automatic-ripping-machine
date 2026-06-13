"""Phase 11 — `PATCH /api/config` apprise URL validation + view round-trip.

Validation runs whether `notifications_enabled` is True or False — saving
bad URLs is invalid input regardless of the master toggle. The 400 detail
must redact the offending URL (scheme-only) so the response is safe to
paste into a bug report.
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
from arm_common.secrets import HIDDEN_SECRET  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession, *, enabled: bool = False, urls: list[str] | None = None) -> None:
    db.rows["config"] = [
        Config(
            id=1,
            tmdb_api_key=None,
            omdb_api_key=None,
            musicbrainz_user_agent=None,
            auto_transcode_on_idle=False,
            auto_rip_on_insert=True,
            block_on_miss=True,
            default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
            notification_apprise_urls=urls or [],
            notifications_enabled=enabled,
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


def test_valid_url_list_accepted(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/config",
            json={"notification_apprise_urls": ["mailto://user:pass@gmail.com"]},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    assert r.json()["notification_apprise_urls"] == ["mailto://user:pass@gmail.com"]


def test_invalid_url_returns_400_with_redacted_detail(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/config",
            json={"notification_apprise_urls": ["not-a-url://AAA-BBB-CCC"]},
            headers=_auth(token),
        )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "invalid apprise URL" in detail
    assert "****" in detail
    assert "AAA-BBB-CCC" not in detail


def test_clearing_urls_is_allowed(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, urls=["mailto://user@host"])
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/config",
            json={"notification_apprise_urls": []},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    assert r.json()["notification_apprise_urls"] == []


def test_validation_runs_when_enabled_too(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, enabled=True)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/config",
            json={
                "notifications_enabled": True,
                "notification_apprise_urls": ["totally-bogus://AAA"],
            },
            headers=_auth(token),
        )
    assert r.status_code == 400
    assert "AAA" not in r.json()["detail"]


def test_notifications_enabled_round_trips(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, enabled=False)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/config",
            json={"notifications_enabled": True},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    assert r.json()["notifications_enabled"] is True
    # The mutated row reflects the patch.
    assert db.rows["config"][0].notifications_enabled is True


def test_default_view_has_notifications_disabled(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/config", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["notifications_enabled"] is False


def test_makemkv_key_round_trips(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        # Unset by default.
        r = client.get("/api/config", headers=_auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["makemkv_key"] is None

        # PATCH persists it; the response view masks the secret, but the DB row holds the real value.
        r = client.patch("/api/config", json={"makemkv_key": "T-abc123"}, headers=_auth(token))
        assert r.status_code == 200, r.text
        assert r.json()["makemkv_key"] == HIDDEN_SECRET
        assert db.rows["config"][0].makemkv_key == "T-abc123"
