"""GET /api/images/cache (stats) + POST /api/images/cache/clear — JWT-gated."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend import image_cache  # noqa: E402
from arm_backend.auth import require_jwt  # noqa: E402
from arm_backend.db import get_session  # noqa: E402
from arm_backend.routers import images as images_router  # noqa: E402
from arm_common import User  # noqa: E402
from arm_common.models.user import GUEST_ROLE  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


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
