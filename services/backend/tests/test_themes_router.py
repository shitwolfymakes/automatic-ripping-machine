"""themes router — list/get/css/upload/delete, JWT gates, 404/400 mapping."""

from __future__ import annotations

import io
import json
import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend import theme_service  # noqa: E402
from arm_backend.auth import require_jwt  # noqa: E402
from arm_backend.routers import themes as themes_router  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(theme_service.settings, "ARM_THEMES_PATH", str(tmp_path))
    app = FastAPI()
    app.include_router(themes_router.router)
    app.dependency_overrides[require_jwt] = lambda: object()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def unauth_client(tmp_path, monkeypatch):
    """Router mounted WITHOUT overriding require_jwt — exercises the real auth gate."""
    monkeypatch.setattr(theme_service.settings, "ARM_THEMES_PATH", str(tmp_path))
    app = FastAPI()
    app.include_router(themes_router.router)
    with TestClient(app) as c:
        yield c


def test_gated_routes_reject_without_jwt(unauth_client):
    # No bearer -> require_jwt rejects (401/403, NOT 200/404). These four are gated.
    assert unauth_client.get("/api/themes").status_code in (401, 403)
    assert unauth_client.get("/api/themes/blockbuster").status_code in (401, 403)
    assert unauth_client.post("/api/themes").status_code in (401, 403)
    assert unauth_client.delete("/api/themes/blockbuster").status_code in (401, 403)


def test_css_route_is_unauthenticated(unauth_client):
    # /css must work with NO auth (UI fetches it bare). blockbuster ships a .css.
    r = unauth_client.get("/api/themes/blockbuster/css")
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]


def test_upload_can_override_builtin_id(client):
    # Uploading a user theme with a built-in's id overrides it (builtin=False wins).
    theme = {"id": "blockbuster", "label": "My BB", "tokens": {"--x": "y"}}
    files = {"theme_json": ("bb.json", io.BytesIO(json.dumps(theme).encode()), "application/json")}
    r = client.post("/api/themes", files=files, data={"theme_css": ""})
    assert r.status_code == 201
    got = client.get("/api/themes/blockbuster").json()
    assert got["label"] == "My BB"
    assert got["builtin"] is False


def test_list_returns_builtins(client):
    r = client.get("/api/themes")
    assert r.status_code == 200
    ids = {t["id"] for t in r.json()}
    assert "blockbuster" in ids
    assert len(ids) >= 30
    assert all("css" not in t for t in r.json())


def test_get_builtin_full(client):
    r = client.get("/api/themes/blockbuster")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "blockbuster"
    assert "css" in body


def test_get_unknown_404(client):
    r = client.get("/api/themes/nope")
    assert r.status_code == 404


def test_css_unauthenticated_and_served(client):
    r = client.get("/api/themes/lcars/css")
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]
    assert r.text


def test_css_unknown_theme_404(client):
    r = client.get("/api/themes/nope/css")
    assert r.status_code == 404


def test_css_no_sidecar_404(client):
    # `blue` is a built-in token-only theme with no .css sidecar shipped in Task 1.
    r = client.get("/api/themes/blue/css")
    assert r.status_code == 404


def test_upload_round_trips(client):
    theme = {"id": "mine", "label": "Mine", "tokens": {"--color-primary": "rgb(1,2,3)"}}
    files = {"theme_json": ("mine.json", io.BytesIO(json.dumps(theme).encode()), "application/json")}
    r = client.post("/api/themes", files=files, data={"theme_css": "[data-scheme=mine]{}"})
    assert r.status_code == 201
    assert r.json()["builtin"] is False
    assert "mine" in {t["id"] for t in client.get("/api/themes").json()}
    assert client.get("/api/themes/mine/css").text == "[data-scheme=mine]{}"


def test_upload_invalid_json_400(client):
    files = {"theme_json": ("bad.json", io.BytesIO(b"{not json"), "application/json")}
    r = client.post("/api/themes", files=files, data={"theme_css": ""})
    assert r.status_code == 400


def test_upload_missing_fields_400(client):
    files = {"theme_json": ("x.json", io.BytesIO(b'{"id":"x"}'), "application/json")}
    r = client.post("/api/themes", files=files, data={"theme_css": ""})
    assert r.status_code == 400


def test_delete_user_theme(client):
    theme = {"id": "mine", "label": "Mine", "tokens": {}}
    files = {"theme_json": ("mine.json", io.BytesIO(json.dumps(theme).encode()), "application/json")}
    client.post("/api/themes", files=files, data={"theme_css": ""})
    r = client.delete("/api/themes/mine")
    assert r.status_code == 200
    assert "mine" not in {t["id"] for t in client.get("/api/themes").json()}


def test_delete_builtin_400(client):
    r = client.delete("/api/themes/blockbuster")
    assert r.status_code == 400
