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
from arm_backend.db import get_session  # noqa: E402
from arm_backend.routers import themes as themes_router  # noqa: E402
from arm_common import User  # noqa: E402
from arm_common.models.user import GUEST_ROLE  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(theme_service.settings, "ARM_THEMES_PATH", str(tmp_path))
    app = FastAPI()
    app.include_router(themes_router.router)
    # POST "" / DELETE /{id} are require_writer-gated (composes require_jwt),
    # so the override must satisfy both: an admin-role User, not a bare object.
    app.dependency_overrides[require_jwt] = lambda: User(
        id="usr_test", username="test", password_hash="x", password_must_change=False, role="admin"
    )
    with TestClient(app) as c:
        yield c


@pytest.fixture
def unauth_client(tmp_path, monkeypatch):
    """Router mounted WITHOUT overriding require_jwt — exercises the real auth gate.

    A bearer-less request now falls back to the guest account, so `get_session`
    still needs a real (fake) DB to resolve that lookup — only the JWT dep
    itself is left un-overridden.
    """
    monkeypatch.setattr(theme_service.settings, "ARM_THEMES_PATH", str(tmp_path))
    app = FastAPI()
    app.include_router(themes_router.router)
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
        yield c


def _upload(client, theme_id, css="", label="X", tokens=None):
    theme = {"id": theme_id, "label": label, "tokens": tokens or {"--x": "y"}}
    files = {"theme_json": (f"{theme_id}.json", io.BytesIO(json.dumps(theme).encode()), "application/json")}
    return client.post("/api/themes", files=files, data={"theme_css": css})


def test_gated_routes_reject_without_jwt(unauth_client):
    # No bearer -> falls back to the guest account. Reads succeed as guest;
    # writes are still denied by the role gate (403), never 200/404.
    assert unauth_client.get("/api/themes").status_code == 200
    assert unauth_client.get("/api/themes/mine").status_code == 404
    assert unauth_client.post("/api/themes").status_code in (401, 403)
    assert unauth_client.delete("/api/themes/mine").status_code in (401, 403)


def test_css_route_is_unauthenticated(client, unauth_client):
    # /css must work with NO auth (UI fetches it bare) for an uploaded user theme.
    _upload(client, "mine", css="[data-scheme=mine]{}")
    r = unauth_client.get("/api/themes/mine/css")
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]


def test_list_returns_only_user_themes(client):
    # Empty user dir -> no themes (built-ins are not backend-served).
    assert client.get("/api/themes").json() == []
    _upload(client, "mine")
    r = client.get("/api/themes")
    assert r.status_code == 200
    body = r.json()
    ids = {t["id"] for t in body}
    assert ids == {"mine"}
    assert all("css" not in t for t in body)


def test_get_user_theme_full(client):
    _upload(client, "mine", css="x{}")
    r = client.get("/api/themes/mine")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "mine"
    assert body["builtin"] is False
    assert "css" in body


def test_get_unknown_404(client):
    assert client.get("/api/themes/nope").status_code == 404
    assert client.get("/api/themes/lcars").status_code == 404  # built-ins not backend-served


def test_css_served_for_user_theme(client):
    _upload(client, "mine", css="[data-scheme=mine]{}")
    r = client.get("/api/themes/mine/css")
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]
    assert r.text == "[data-scheme=mine]{}"


def test_css_unknown_theme_404(client):
    r = client.get("/api/themes/nope/css")
    assert r.status_code == 404


def test_css_no_sidecar_404(client):
    # A token-only user theme (no css uploaded) -> /css 404.
    _upload(client, "tokenonly", css="")
    r = client.get("/api/themes/tokenonly/css")
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


def test_upload_oserror_503(client, monkeypatch):
    def _boom(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(theme_service.Path, "write_text", _boom)
    theme = {"id": "mine", "label": "Mine", "tokens": {}}
    files = {"theme_json": ("mine.json", io.BytesIO(json.dumps(theme).encode()), "application/json")}
    r = client.post("/api/themes", files=files, data={"theme_css": ""})
    assert r.status_code == 503
    assert "No space left on device" in r.json()["detail"]


def test_delete_invalid_theme_id_400(client):
    # _safe_theme_id rejects an id that doesn't match _SAFE_ID with ValueError.
    r = client.delete("/api/themes/UPPERCASE")
    assert r.status_code == 400


def test_delete_unknown_400(client):
    # Deleting a non-existent theme (incl. a built-in id, which isn't backend-served).
    assert client.delete("/api/themes/blockbuster").status_code == 400
    assert client.delete("/api/themes/nope").status_code == 400
