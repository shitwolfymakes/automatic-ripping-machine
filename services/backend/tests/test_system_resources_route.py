"""GET /api/system/resources — JWT-protected per-host resource metrics."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import arm_backend.routers.system as system_mod  # noqa: E402
import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.host_snapshots import HostSnapshotStore  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import system as system_router  # noqa: E402
from arm_common import Host, User  # noqa: E402
from arm_common.schemas import HostResourcesSnapshot, MemoryInfo  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession) -> None:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows.setdefault("hosts", [])


def _make_app(signing_key: bytes) -> tuple[FastAPI, str]:
    db = FakeSession()
    _seed(db)
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.system_paths = {"Raw": "/raw"}
    app.state.host_snapshots = HostSnapshotStore()
    app.include_router(system_router.router)

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    app.state._db = db  # stash for tests to seed hosts directly
    return app, token


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_resources_requires_jwt(signing_key: bytes) -> None:
    app, _ = _make_app(signing_key)
    with TestClient(app) as c:
        resp = c.get("/api/system/resources")
    assert resp.status_code == 401


def test_resources_shape(signing_key: bytes, monkeypatch) -> None:
    monkeypatch.setattr(system_mod, "probe_cpu_percent", lambda: 12.5)
    monkeypatch.setattr(
        system_mod,
        "probe_memory",
        lambda: MemoryInfo(total_gb=16.0, used_gb=2.0, free_gb=13.0, percent=12.5),
    )
    monkeypatch.setattr(system_mod, "probe_cpu_temp", lambda: 0.0)
    monkeypatch.setattr(system_mod, "_roots", lambda request: {"Raw": "/raw"})
    monkeypatch.setattr(
        system_mod,
        "get_disk_usage",
        lambda path: {"total": 100 * 1073741824, "used": 40 * 1073741824, "free": 60 * 1073741824, "percent": 40.0},
    )

    app, token = _make_app(signing_key)
    db: FakeSession = app.state._db
    now = datetime.now(timezone.utc)
    app.state.hostname = "backend-1"
    db.rows["hosts"].append(Host(hostname="backend-1", role="backend", version="9.9", first_seen=now, last_seen=now))

    with TestClient(app) as c:
        resp = c.get("/api/system/resources", headers=_auth(token))

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    view = next(v for v in body if v["hostname"] == "backend-1")
    assert view["role"] == "backend"
    assert view["version"] == "9.9"
    snap = view["snapshot"]
    assert snap["cpu_percent"] == 12.5
    assert snap["cpu_temp"] == 0.0
    assert snap["memory"]["free_gb"] == 13.0
    assert snap["storage"][0] == {
        "name": "Raw",
        "path": "/raw",
        "total_gb": 100.0,
        "used_gb": 40.0,
        "free_gb": 60.0,
        "percent": 40.0,
    }


def test_resources_omits_uncached_root(signing_key: bytes, monkeypatch) -> None:
    monkeypatch.setattr(system_mod, "probe_cpu_percent", lambda: 1.0)
    monkeypatch.setattr(
        system_mod,
        "probe_memory",
        lambda: MemoryInfo(total_gb=1.0, used_gb=0.0, free_gb=1.0, percent=0.0),
    )
    monkeypatch.setattr(system_mod, "probe_cpu_temp", lambda: 0.0)
    monkeypatch.setattr(system_mod, "_roots", lambda request: {"Raw": "/raw", "Iso": "/iso"})
    monkeypatch.setattr(system_mod, "get_disk_usage", lambda path: None)  # nothing cached

    app, token = _make_app(signing_key)
    db: FakeSession = app.state._db
    now = datetime.now(timezone.utc)
    app.state.hostname = "backend-1"
    db.rows["hosts"].append(Host(hostname="backend-1", role="backend", version="9.9", first_seen=now, last_seen=now))

    with TestClient(app) as c:
        resp = c.get("/api/system/resources", headers=_auth(token))

    assert resp.status_code == 200
    body = resp.json()
    view = next(v for v in body if v["hostname"] == "backend-1")
    assert view["snapshot"]["storage"] == []


def test_resources_returns_list_with_backend_host(signing_key: bytes, monkeypatch) -> None:
    """The backend's own host row + snapshot appear as one list element."""
    monkeypatch.setattr(system_mod, "probe_cpu_percent", lambda: 3.0)
    monkeypatch.setattr(
        system_mod,
        "probe_memory",
        lambda: MemoryInfo(total_gb=8.0, used_gb=1.0, free_gb=7.0, percent=12.5),
    )
    monkeypatch.setattr(system_mod, "probe_cpu_temp", lambda: 0.0)
    monkeypatch.setattr(system_mod, "_roots", lambda request: {})

    app, token = _make_app(signing_key)
    db: FakeSession = app.state._db
    now = datetime.now(timezone.utc)
    app.state.hostname = "backend-1"
    db.rows["hosts"].append(Host(hostname="backend-1", role="backend", version="9.9", first_seen=now, last_seen=now))
    # Pre-seed a snapshot too; the endpoint should refresh it on every read.
    app.state.host_snapshots.put(
        "backend-1",
        HostResourcesSnapshot(
            cpu_percent=999.0,
            cpu_temp=0.0,
            memory=MemoryInfo(total_gb=8.0, used_gb=1.0, free_gb=7.0, percent=12.5),
            storage=[],
        ),
        now,
    )

    with TestClient(app) as c:
        r = c.get("/api/system/resources", headers=_auth(token))

    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    backend = next(v for v in body if v["role"] == "backend" and v["hostname"] == "backend-1")
    # Refresh-on-read: the endpoint must overwrite the stale pre-seeded snapshot
    # (cpu_percent=999.0) with a freshly probed one (probe stub returns 3.0),
    # not trust whatever was already in the store.
    assert backend["snapshot"]["cpu_percent"] == 3.0


def test_resources_omits_stale_host(signing_key: bytes) -> None:
    app, token = _make_app(signing_key)
    db: FakeSession = app.state._db
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.rows["hosts"].append(Host(hostname="ripper-old", role="ripper", version="", first_seen=old, last_seen=old))
    # No app.state.hostname set -> backend's own snapshot is not refreshed/added.

    with TestClient(app) as c:
        r = c.get("/api/system/resources", headers=_auth(token))

    assert r.status_code == 200
    assert all(v["hostname"] != "ripper-old" for v in r.json())
