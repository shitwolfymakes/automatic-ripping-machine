"""GET /api/images/cache (stats) + POST /api/images/cache/clear — JWT-gated."""

from __future__ import annotations


import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from arm_backend import image_cache
from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_backend.routers import images as images_router
from arm_common import User
from arm_common.models.user import GUEST_ROLE

from tests._fakes import FakeSession


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(image_cache.settings, "ARM_IMAGE_CACHE_PATH", str(tmp_path))
    image_cache.reset()
    app = FastAPI()
    app.include_router(images_router.router)
    # POST /images/cache/clear is require_writer-gated (composes require_jwt),
    # so the override must satisfy both: an admin-role User, not a bare object.
    app.dependency_overrides[require_jwt] = lambda: User(
        id="usr_test", username="test", password_hash="x", password_must_change=False, role="admin"
    )
    with TestClient(app) as c:
        yield c
    image_cache.reset()


def test_cache_stats_empty(client):
    r = client.get("/api/images/cache")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["size_mb"] == 0


def test_cache_stats_after_store(client):
    image_cache.store("https://x/y.jpg", b"abc", "image/jpeg")
    r = client.get("/api/images/cache")
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_cache_clear(client):
    image_cache.store("https://x/y.jpg", b"abc", "image/jpeg")
    r = client.post("/api/images/cache/clear")
    assert r.status_code == 200
    body = r.json()
    assert body["cleared"] == 1
    assert client.get("/api/images/cache").json()["count"] == 0


def test_cache_stats_requires_jwt():
    # no require_jwt override → exercises the real auth gate. No bearer now
    # falls back to the guest account, so get_session still needs a fake DB
    # to resolve that lookup; the route itself is read-only so guest succeeds.
    app = FastAPI()
    app.include_router(images_router.router)
    db = FakeSession()
    db.rows["users"] = [
        User(
            id="usr_guest",
            username="guest",
            password_hash="x",
            password_must_change=False,
            role=GUEST_ROLE,
            disabled=False,
        )
    ]

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    with TestClient(app) as c:
        assert c.get("/api/images/cache").status_code == 200
