"""Notification channels CRUD + catalog + test-send."""

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
from arm_backend.routers import notifications as notif_router  # noqa: E402
from arm_backend.notifications import catalog as cat  # noqa: E402
from arm_common import NotificationChannel, User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


class _FakeNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.raise_on_notify = False

    async def notify(self, urls, title, body) -> None:
        self.calls.append((list(urls), title, body))
        if self.raise_on_notify:
            raise RuntimeError("send failed")


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


@pytest.fixture(autouse=True)
def _fake_catalog(monkeypatch):
    cat.build_catalog.cache_clear()
    fake = {
        "featured": ["discord"],
        "services": [
            {
                "id": "discord",
                "name": "Discord",
                "docs_url": "",
                "url_scheme": "discord",
                "required_fields": [
                    {"key": "webhook_id", "label": "Webhook ID", "type": "string", "private": True, "required": True},
                    {"key": "webhook_token", "label": "Token", "type": "string", "private": True, "required": True},
                ],
                "advanced_fields": [
                    {"key": "format", "label": "Format", "type": "choice", "private": False, "required": False}
                ],
            }
        ],
    }
    monkeypatch.setattr(cat, "build_catalog", lambda: fake)
    # field_map imports build_catalog by name — patch there too.
    from arm_backend.notifications import field_map as fm

    monkeypatch.setattr(fm, "build_catalog", lambda: fake)
    yield


def _make_app(signing_key: bytes, db: FakeSession, notifier=None):
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.notifier = notifier or _FakeNotifier()
    app.include_router(notif_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_list_requires_auth(signing_key: bytes) -> None:
    db = FakeSession()
    app, _ = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/notifications/channels")
    assert r.status_code == 401


def test_create_channel_with_raw_url(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    body = {
        "type": "apprise",
        "name": "Raw",
        "config": {"type": "apprise", "url": "json://localhost/x"},
        "subscribed_events": ["rip.completed"],
    }
    with TestClient(app) as client:
        r = client.post("/api/notifications/channels", json=body, headers=_auth(token))
    assert r.status_code == 201, r.text
    assert r.json()["config"]["url"] == "json://localhost/x"
    assert r.json()["id"].startswith("ncl_")


def test_create_channel_composes_from_fields(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    body = {
        "type": "apprise",
        "name": "Discord",
        "config": {"type": "apprise", "service_id": "discord", "fields": {"webhook_id": "1", "webhook_token": "2"}},
        "subscribed_events": ["rip.completed"],
    }
    with TestClient(app) as client:
        r = client.post("/api/notifications/channels", json=body, headers=_auth(token))
    assert r.status_code == 201, r.text
    cfg = r.json()["config"]
    assert cfg["url"] == "discord://1/2"
    # private fields masked on the way out
    assert cfg["fields"]["webhook_id"] == "<hidden>"


def test_create_rejects_bad_event(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    body = {
        "type": "apprise",
        "name": "X",
        "config": {"type": "apprise", "url": "json://localhost/x"},
        "subscribed_events": ["not.a.real.event"],
    }
    with TestClient(app) as client:
        r = client.post("/api/notifications/channels", json=body, headers=_auth(token))
    assert r.status_code == 422
    assert "not.a.real.event" in r.json()["detail"]


def test_get_channel_404(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/notifications/channels/ncl_missing", headers=_auth(token))
    assert r.status_code == 404


def test_patch_channel_name_only(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows.setdefault("notification_channels", []).append(
        NotificationChannel(id="ncl_1", type="apprise", name="Old",
                            config={"type": "apprise", "url": "json://localhost/x"},
                            subscribed_events=["rip.completed"])
    )
    with TestClient(app) as client:
        r = client.patch("/api/notifications/channels/ncl_1", json={"name": "New"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "New"
    assert r.json()["config"]["url"] == "json://localhost/x"  # untouched


def test_patch_channel_merges_hidden_secret(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows.setdefault("notification_channels", []).append(
        NotificationChannel(id="ncl_1", type="apprise", name="D",
                            config={"type": "apprise", "service_id": "discord", "url": "discord://1/2",
                                    "fields": {"webhook_id": "1", "webhook_token": "2"}},
                            subscribed_events=["rip.completed"])
    )
    body = {"config": {"type": "apprise", "service_id": "discord",
                       "fields": {"webhook_id": "<hidden>", "webhook_token": "NEW"}}}
    with TestClient(app) as client:
        r = client.patch("/api/notifications/channels/ncl_1", json=body, headers=_auth(token))
    assert r.status_code == 200, r.text
    # url recomposed with kept secret + new token; output masked
    # (fetch stored row to assert the real url)
    stored = db.rows["notification_channels"][0]
    assert stored.config["url"] == "discord://1/NEW"
    assert stored.config["fields"]["webhook_id"] == "1"


def test_patch_channel_404(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/notifications/channels/ncl_x", json={"name": "n"}, headers=_auth(token))
    assert r.status_code == 404


def test_patch_channel_config_raw_url(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows.setdefault("notification_channels", []).append(
        NotificationChannel(id="ncl_1", type="apprise", name="D",
                            config={"type": "apprise", "url": "json://old/x"},
                            subscribed_events=["rip.completed"])
    )
    body = {"config": {"type": "apprise", "url": "json://new/y"}}
    with TestClient(app) as client:
        r = client.patch("/api/notifications/channels/ncl_1", json=body, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert db.rows["notification_channels"][0].config["url"] == "json://new/y"


def test_patch_channel_empty_config_rejected(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows.setdefault("notification_channels", []).append(
        NotificationChannel(id="ncl_1", type="apprise", name="D",
                            config={"type": "apprise", "url": "json://old/x"},
                            subscribed_events=["rip.completed"])
    )
    # config with neither url nor fields -> resolves to empty url -> 422, channel not bricked
    body = {"config": {"type": "apprise"}}
    with TestClient(app) as client:
        r = client.patch("/api/notifications/channels/ncl_1", json=body, headers=_auth(token))
    assert r.status_code == 422, r.text
    # stored config untouched (still the old valid url)
    assert db.rows["notification_channels"][0].config["url"] == "json://old/x"
