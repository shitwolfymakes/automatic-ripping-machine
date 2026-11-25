"""`PATCH /api/config` notification + view round-trip.

`notification_apprise_urls` is not on the
editable surface — it is absent from `ConfigUpdateRequest`, so a PATCH that
sends it is silently ignored (the legacy flat list never dispatches; channels
do). `ConfigView` still carries it for read back-compat, redacted to each
URL's scheme because the URLs hold credentials. These tests assert the field
is inert on write and never shows a credential on read.
"""

from __future__ import annotations

import secrets


from fastapi import FastAPI
from fastapi.testclient import TestClient

import pytest

from arm_backend.db import get_session
from arm_backend.jwt_utils import issue_access_token
from arm_backend.routers import config as config_router
from arm_common import Config, RetentionPolicy, User
from arm_common.secrets import HIDDEN_SECRET

from tests._fakes import FakeSession


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


def test_apprise_urls_patch_is_ignored(signing_key: bytes) -> None:
    # The field is off the editable surface, so a PATCH carrying it is silently
    # dropped (200) and the stored list is unchanged; it reads back redacted.
    db = FakeSession()
    _seed(db, urls=["mailto://orig@host"])
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/config",
            json={"notification_apprise_urls": ["mailto://user:pass@gmail.com"]},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    # Unchanged: the PATCH value never reached the row.
    assert r.json()["notification_apprise_urls"] == ["mailto://****"]
    assert db.rows["config"][0].notification_apprise_urls == ["mailto://orig@host"]


def test_invalid_apprise_url_no_longer_validated(signing_key: bytes) -> None:
    # No write-path validation remains: a bogus URL in the PATCH body is ignored
    # rather than rejected, because the field is no longer accepted at all.
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/config",
            json={"notification_apprise_urls": ["not-a-url://AAA-BBB-CCC"]},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    # inert on write: the bogus URL was neither rejected nor persisted
    assert db.rows["config"][0].notification_apprise_urls == []


def test_apprise_urls_are_redacted_in_view(signing_key: bytes) -> None:
    # Apprise URLs carry the destination's credential (in the userinfo, the
    # path or the query, depending on the service). GET keeps the list for
    # back-compat but shows only each URL's scheme, as the channel views do.
    db = FakeSession()
    _seed(
        db,
        urls=[
            "mailto://user:hunter2@gmail.com",
            "discord://123456/webhooktoken-SECRET",
            "pover://userkey@apptoken?priority=high&token=QSECRET",
            "no-scheme-SECRET",
        ],
    )
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/config", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["notification_apprise_urls"] == ["mailto://****", "discord://****", "pover://****", "****"]
    for secret in ("hunter2", "webhooktoken", "SECRET", "userkey", "apptoken"):
        assert secret not in r.text


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
