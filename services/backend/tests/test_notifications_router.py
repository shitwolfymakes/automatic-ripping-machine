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


def test_delete_channel(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows.setdefault("notification_channels", []).append(
        NotificationChannel(id="ncl_1", type="apprise", name="D", config={"type": "apprise", "url": "json://l/x"})
    )
    with TestClient(app) as client:
        r = client.delete("/api/notifications/channels/ncl_1", headers=_auth(token))
    assert r.status_code == 204
    assert db.rows["notification_channels"] == []


def test_delete_channel_404(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.delete("/api/notifications/channels/ncl_x", headers=_auth(token))
    assert r.status_code == 404


def test_get_services(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/notifications/services", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["featured"] == ["discord"]
    assert r.json()["services"][0]["id"] == "discord"


def test_compose_url(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    body = {"required": {"webhook_id": "1", "webhook_token": "2"}, "advanced": {"format": "markdown"}}
    with TestClient(app) as client:
        r = client.post("/api/notifications/services/discord/compose-url", json=body, headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["url"] == "discord://1/2?format=markdown"


def test_event_types(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/notifications/event-types", headers=_auth(token))
    assert r.status_code == 200
    assert "rip.completed" in r.json()
    assert r.json() == sorted(r.json())


def test_test_saved_channel_success(signing_key: bytes) -> None:
    db = FakeSession()
    notifier = _FakeNotifier()
    app, token = _make_app(signing_key, db, notifier)
    db.rows.setdefault("notification_channels", []).append(
        NotificationChannel(id="ncl_1", type="apprise", name="D",
                            config={"type": "apprise", "url": "json://localhost/x"},
                            subscribed_events=["rip.completed"])
    )
    with TestClient(app) as client:
        r = client.post("/api/notifications/channels/ncl_1/test", json={}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "error": None}
    assert notifier.calls and notifier.calls[0][0] == ["json://localhost/x"]
    stored = db.rows["notification_channels"][0]
    assert stored.last_success_at is not None
    assert stored.last_error is None
    # a dispatch-log row was written
    assert any(r.success for r in db.rows.get("notification_dispatch_log", []))


def test_test_saved_channel_failure_returns_ok_false(signing_key: bytes) -> None:
    db = FakeSession()
    notifier = _FakeNotifier()
    notifier.raise_on_notify = True
    app, token = _make_app(signing_key, db, notifier)
    db.rows.setdefault("notification_channels", []).append(
        NotificationChannel(id="ncl_1", type="apprise", name="D",
                            config={"type": "apprise", "url": "json://localhost/x"})
    )
    with TestClient(app) as client:
        r = client.post("/api/notifications/channels/ncl_1/test", json={}, headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["ok"] is False
    stored = db.rows["notification_channels"][0]
    assert stored.last_error is not None


def test_test_saved_channel_404(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post("/api/notifications/channels/ncl_x/test", json={}, headers=_auth(token))
    assert r.status_code == 404


def test_test_adhoc_config_success(signing_key: bytes) -> None:
    db = FakeSession()
    notifier = _FakeNotifier()
    app, token = _make_app(signing_key, db, notifier)
    body = {"config": {"type": "apprise", "service_id": "discord", "fields": {"webhook_id": "1", "webhook_token": "2"}}}
    with TestClient(app) as client:
        r = client.post("/api/notifications/test", json=body, headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert notifier.calls[0][0] == ["discord://1/2"]
    # ad-hoc log row has channel_id None
    assert any(r.channel_id is None for r in db.rows.get("notification_dispatch_log", []))


def test_test_adhoc_no_url_returns_ok_false(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    body = {"config": {"type": "apprise"}}  # no url, no fields
    with TestClient(app) as client:
        r = client.post("/api/notifications/test", json=body, headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == {"ok": False, "error": "url is required"}


def test_test_saved_channel_with_reentered_fields(signing_key: bytes) -> None:
    db = FakeSession()
    notifier = _FakeNotifier()
    app, token = _make_app(signing_key, db, notifier)
    db.rows.setdefault("notification_channels", []).append(
        NotificationChannel(id="ncl_1", type="apprise", name="D",
                            config={"type": "apprise", "service_id": "discord", "url": "discord://1/2",
                                    "fields": {"webhook_id": "1", "webhook_token": "2"}},
                            subscribed_events=["rip.completed"])
    )
    # re-enter the token only; webhook_id stays via <hidden>
    body = {"fields": {"webhook_id": "<hidden>", "webhook_token": "NEW"}}
    with TestClient(app) as client:
        r = client.post("/api/notifications/channels/ncl_1/test", json=body, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    # the recomposed url (kept secret + new token) is what got sent, NOT the stored url
    assert notifier.calls[0][0] == ["discord://1/NEW"]


def test_test_saved_channel_empty_url_returns_ok_false(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    # channel whose config resolves to no url (no url, no fields)
    db.rows.setdefault("notification_channels", []).append(
        NotificationChannel(id="ncl_1", type="apprise", name="D",
                            config={"type": "apprise"}, subscribed_events=["rip.completed"])
    )
    with TestClient(app) as client:
        r = client.post("/api/notifications/channels/ncl_1/test", json={}, headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == {"ok": False, "error": "could not compose url from fields"}


def test_test_adhoc_unknown_service_returns_ok_false(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    # service_id not in the fake catalog -> compose_url_from_fields returns None -> url stays empty
    body = {"config": {"type": "apprise", "service_id": "ghost", "fields": {"a": "b"}}}
    with TestClient(app) as client:
        r = client.post("/api/notifications/test", json=body, headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == {"ok": False, "error": "url is required"}


def test_dispatch_log_list_and_filter(signing_key: bytes) -> None:
    from arm_common import NotificationDispatchLog
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows.setdefault("notification_dispatch_log", []).extend([
        NotificationDispatchLog(id="ndl_1", channel_id="ncl_1", event_type="rip.completed", title="t", body="b", success=True),
        NotificationDispatchLog(id="ndl_2", channel_id="ncl_2", event_type="rip.failed", title="t", body="b", success=False),
    ])
    with TestClient(app) as client:
        r = client.get("/api/notifications/dispatch-log", headers=_auth(token))
        assert r.status_code == 200
        assert len(r.json()) == 2
        r2 = client.get("/api/notifications/dispatch-log?channel_id=ncl_1", headers=_auth(token))
        assert [row["id"] for row in r2.json()] == ["ndl_1"]


def test_get_channel_returns_existing(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows.setdefault("notification_channels", []).append(
        NotificationChannel(id="ncl_1", type="apprise", name="D",
                            config={"type": "apprise", "url": "json://l/x"},
                            subscribed_events=["rip.completed"])
    )
    with TestClient(app) as client:
        r = client.get("/api/notifications/channels/ncl_1", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "D"


def test_create_unknown_service_id_yields_empty_url_rejected(signing_key: bytes) -> None:
    # service_id not in catalog -> compose_url_from_fields returns None ->
    # url stays empty -> _validate_apprise_url rejects (covers 114->116).
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    body = {
        "type": "apprise",
        "name": "Ghost",
        "config": {"type": "apprise", "service_id": "ghost", "fields": {"a": "b"}},
    }
    with TestClient(app) as client:
        r = client.post("/api/notifications/channels", json=body, headers=_auth(token))
    assert r.status_code == 422, r.text


def test_create_rejects_bad_template_key(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    body = {"type": "apprise", "name": "X",
            "config": {"type": "apprise", "url": "json://localhost/x"},
            "templates": {"not.an.event": {"title": "hi"}}}
    with TestClient(app) as client:
        r = client.post("/api/notifications/channels", json=body, headers=_auth(token))
    assert r.status_code == 422
    assert "not.an.event" in r.json()["detail"]


def test_list_channels_returns_rows_masked(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows.setdefault("notification_channels", []).extend([
        NotificationChannel(id="ncl_1", type="apprise", name="A",
                            config={"type": "apprise", "service_id": "discord", "url": "discord://1/2",
                                    "fields": {"webhook_id": "1", "webhook_token": "2"}},
                            subscribed_events=["rip.completed"]),
        NotificationChannel(id="ncl_2", type="apprise", name="B",
                            config={"type": "apprise", "url": "json://b/x"}),
    ])
    with TestClient(app) as client:
        r = client.get("/api/notifications/channels", headers=_auth(token))
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    # the fields-bearing channel has its private fields masked
    a = next(c for c in rows if c["name"] == "A")
    assert a["config"]["fields"]["webhook_id"] == "<hidden>"


def test_patch_channel_applies_all_fields(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows.setdefault("notification_channels", []).append(
        NotificationChannel(id="ncl_1", type="apprise", name="Old", enabled=True,
                            config={"type": "apprise", "url": "json://l/x"},
                            subscribed_events=["rip.completed"], templates={})
    )
    body = {
        "name": "New",
        "enabled": False,
        "subscribed_events": ["rip.failed", "session.completed"],
        "templates": {"rip.failed": {"title": "Custom", "body": "b"}},
    }
    with TestClient(app) as client:
        r = client.patch("/api/notifications/channels/ncl_1", json=body, headers=_auth(token))
    assert r.status_code == 200, r.text
    stored = db.rows["notification_channels"][0]
    assert stored.name == "New"
    assert stored.enabled is False
    assert stored.subscribed_events == ["rip.failed", "session.completed"]
    assert stored.templates == {"rip.failed": {"title": "Custom", "body": "b"}}


def test_app_registers_notifications_router() -> None:
    from arm_backend.main import app
    paths = {r.path for r in app.routes}
    assert "/api/notifications/channels" in paths
