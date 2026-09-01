"""GET /api/system/resources — JWT-protected system resource metrics."""

from __future__ import annotations

import os
import secrets
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import arm_backend.routers.system as system_mod  # noqa: E402
import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import system as system_router  # noqa: E402
from arm_common import User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession) -> None:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]


def _make_app(signing_key: bytes) -> tuple[FastAPI, str]:
    db = FakeSession()
    _seed(db)
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.system_paths = {"Raw": "/raw"}
    app.include_router(system_router.router)

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_resources_requires_jwt(signing_key: bytes) -> None:
    app, _ = _make_app(signing_key)
    with TestClient(app) as c:
        resp = c.get("/api/system/resources")
    assert resp.status_code == 401


def test_resources_shape(signing_key: bytes, monkeypatch) -> None:
    monkeypatch.setattr(system_mod.psutil, "cpu_percent", lambda interval=None: 12.5)
    monkeypatch.setattr(
        system_mod.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(
            total=16 * 1073741824,
            used=2 * 1073741824,
            available=13 * 1073741824,
            percent=12.5,
        ),
    )
    monkeypatch.setattr(system_mod.psutil, "sensors_temperatures", lambda: {})
    monkeypatch.setattr(system_mod, "_roots", lambda request: {"Raw": "/raw"})
    monkeypatch.setattr(
        system_mod,
        "get_disk_usage",
        lambda path: {"total": 100 * 1073741824, "used": 40 * 1073741824, "free": 60 * 1073741824, "percent": 40.0},
    )

    app, token = _make_app(signing_key)
    with TestClient(app) as c:
        resp = c.get("/api/system/resources", headers=_auth(token))

    assert resp.status_code == 200
    body = resp.json()
    assert body["cpu_percent"] == 12.5
    assert body["cpu_temp"] == 0.0  # no sensors → 0.0
    assert body["memory"]["free_gb"] == 13.0
    assert body["storage"][0] == {
        "name": "Raw",
        "path": "/raw",
        "total_gb": 100.0,
        "used_gb": 40.0,
        "free_gb": 60.0,
        "percent": 40.0,
    }


def test_resources_omits_uncached_root(signing_key: bytes, monkeypatch) -> None:
    monkeypatch.setattr(system_mod.psutil, "cpu_percent", lambda interval=None: 1.0)
    monkeypatch.setattr(
        system_mod.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(total=1073741824, used=0, available=1073741824, percent=0.0),
    )
    monkeypatch.setattr(system_mod.psutil, "sensors_temperatures", lambda: {})
    monkeypatch.setattr(system_mod, "_roots", lambda request: {"Raw": "/raw", "Iso": "/iso"})
    monkeypatch.setattr(system_mod, "get_disk_usage", lambda path: None)  # nothing cached

    app, token = _make_app(signing_key)
    with TestClient(app) as c:
        resp = c.get("/api/system/resources", headers=_auth(token))

    assert resp.status_code == 200
    assert resp.json()["storage"] == []
