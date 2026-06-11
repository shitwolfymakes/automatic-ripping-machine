"""In-app inbox endpoints."""

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
from arm_common import NotificationInbox, User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _make_app(signing_key: bytes, db: FakeSession):
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.notifier = object()  # unused by inbox endpoints
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


def _seed_rows(db: FakeSession) -> None:
    db.rows.setdefault("notification_inbox", []).extend([
        NotificationInbox(id="nin_1", event_type="rip.completed", title="t1", message="m1", seen=False, cleared=False),
        NotificationInbox(id="nin_2", event_type="rip.failed", title="t2", message="m2", seen=True, cleared=False),
        NotificationInbox(id="nin_3", event_type="rip.completed", title="t3", message="m3", seen=True, cleared=True),
    ])


def test_inbox_list_excludes_cleared_by_default(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_rows(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/notifications/inbox", headers=_auth(token))
        assert r.status_code == 200
        ids = {row["id"] for row in r.json()}
        assert ids == {"nin_1", "nin_2"}  # nin_3 cleared, hidden
        r2 = client.get("/api/notifications/inbox?include_cleared=true", headers=_auth(token))
        assert len(r2.json()) == 3


def test_inbox_count(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_rows(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/notifications/inbox/count", headers=_auth(token))
    assert r.json() == {"unseen": 1, "seen": 1, "cleared": 1, "total": 3}


def test_inbox_dismiss_all(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_rows(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post("/api/notifications/inbox/dismiss-all", headers=_auth(token))
    assert r.json()["updated"] == 1  # only nin_1 was unseen
    assert all(row.seen for row in db.rows["notification_inbox"])


def test_inbox_purge(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_rows(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post("/api/notifications/inbox/purge", headers=_auth(token))
    assert r.json()["deleted"] == 1  # only nin_3 was cleared
    assert {row.id for row in db.rows["notification_inbox"]} == {"nin_1", "nin_2"}


def test_inbox_patch_seen_and_cleared(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_rows(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/notifications/inbox/nin_1", json={"seen": True, "cleared": True}, headers=_auth(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["seen"] is True and body["cleared"] is True
        assert body["seen_at"] is not None and body["cleared_at"] is not None
        r404 = client.patch("/api/notifications/inbox/nin_x", json={"seen": True}, headers=_auth(token))
        assert r404.status_code == 404


def test_inbox_requires_auth(signing_key: bytes) -> None:
    db = FakeSession()
    app, _ = _make_app(signing_key, db)
    with TestClient(app) as client:
        assert client.get("/api/notifications/inbox").status_code == 401
        assert client.get("/api/notifications/inbox/count").status_code == 401
        assert client.post("/api/notifications/inbox/dismiss-all").status_code == 401


def test_app_registers_inbox_route() -> None:
    from arm_backend.main import app
    paths = {r.path for r in app.routes}
    assert "/api/notifications/inbox" in paths


def test_inbox_patch_only_seen(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_rows(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        # nin_1 starts seen=False, cleared=False; set ONLY seen
        r = client.patch("/api/notifications/inbox/nin_1", json={"seen": True}, headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["seen"] is True and body["seen_at"] is not None
    assert body["cleared"] is False and body["cleared_at"] is None  # cleared untouched


def test_inbox_patch_only_cleared_then_unset(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_rows(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        # set ONLY cleared=True on nin_1, then unset it (False -> cleared_at None)
        r1 = client.patch("/api/notifications/inbox/nin_1", json={"cleared": True}, headers=_auth(token))
        assert r1.status_code == 200, r1.text
        assert r1.json()["cleared"] is True and r1.json()["cleared_at"] is not None
        r2 = client.patch("/api/notifications/inbox/nin_1", json={"cleared": False}, headers=_auth(token))
    assert r2.status_code == 200, r2.text
    assert r2.json()["cleared"] is False and r2.json()["cleared_at"] is None


def test_inbox_patch_empty_body_noop(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_rows(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        # neither seen nor cleared provided -> both branches skipped, 200 no-op
        r = client.patch("/api/notifications/inbox/nin_1", json={}, headers=_auth(token))
    assert r.status_code == 200, r.text
    # nin_1 unchanged: still seen=False, cleared=False
    assert r.json()["seen"] is False and r.json()["cleared"] is False
