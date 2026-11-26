"""GET /api/handbrake-schema (slim view + ETag), /builtin/{name}, POST /refresh."""

from __future__ import annotations

import secrets

from fastapi import FastAPI
from fastapi.testclient import TestClient

from arm_backend.db import get_session
from arm_backend.handbrake_schema_store import SchemaStore
from arm_backend.jwt_utils import issue_access_token
from arm_backend.routers import handbrake_schema as router_mod
from arm_common import User

from tests._fakes import FakeSession
from tests._hb_schema import fixture_schema


class _Runner:
    def __init__(self, error: str | None) -> None:
        self.error = error
        self.calls = 0

    async def refresh(self) -> str | None:
        self.calls += 1
        return self.error


def _app(*, loaded: bool = True, runner: _Runner | None = None, role: str = "admin") -> tuple[FastAPI, str]:
    key = secrets.token_bytes(32)
    db = FakeSession()
    db.rows["users"] = [User(id="usr_a", username="a", password_hash="x", password_must_change=False, role=role)]
    app = FastAPI()
    app.state.signing_key = key
    store = SchemaStore()
    if loaded:
        store.replace(fixture_schema())
    app.state.handbrake_schema_store = store
    app.state.handbrake_schema_runner = runner or _Runner(None)
    app.include_router(router_mod.router)

    async def _session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _session
    token, _ = issue_access_token("usr_a", "a", key)
    return app, token


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_slim_view_carries_the_etag() -> None:
    app, token = _app()
    with TestClient(app) as c:
        r = c.get("/api/handbrake-schema", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.headers["etag"] == f'"{fixture_schema().content_hash}"'
    assert r.json()["content_hash"] == fixture_schema().content_hash


def test_matching_if_none_match_gets_304_with_the_etag() -> None:
    app, token = _app()
    h = fixture_schema().content_hash
    with TestClient(app) as c:
        quoted = c.get("/api/handbrake-schema", headers={**_auth(token), "If-None-Match": f'"{h}"'})
        bare = c.get("/api/handbrake-schema", headers={**_auth(token), "If-None-Match": h})
        other = c.get("/api/handbrake-schema", headers={**_auth(token), "If-None-Match": '"nope"'})
    for r in (quoted, bare):
        assert r.status_code == 304
        assert r.content == b""
        assert r.headers["etag"] == f'"{h}"'
    assert other.status_code == 200


def test_slim_view_is_503_without_a_schema() -> None:
    app, token = _app(loaded=False)
    with TestClient(app) as c:
        r = c.get("/api/handbrake-schema", headers=_auth(token))
    assert r.status_code == 503
    assert r.json() == {"detail": "No HandBrake schema loaded yet"}


def test_requires_a_token() -> None:
    app, _ = _app()
    with TestClient(app) as c:
        assert c.get("/api/handbrake-schema", headers=_auth("garbage")).status_code == 401


def test_builtin_returns_one_preset() -> None:
    app, token = _app()
    name = next(iter(fixture_schema().builtin_presets))
    with TestClient(app) as c:
        r = c.get(f"/api/handbrake-schema/builtin/{name}", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json() == fixture_schema().builtin_presets[name]
    assert r.headers["etag"] == f'"{fixture_schema().content_hash}"'


def test_builtin_unknown_name_is_404() -> None:
    app, token = _app()
    with TestClient(app) as c:
        r = c.get("/api/handbrake-schema/builtin/Nope%20At%20All", headers=_auth(token))
    assert r.status_code == 404
    assert r.json() == {
        "detail": f"HandBrake {fixture_schema().handbrake_tag} has no built-in preset named 'Nope At All'"
    }


def test_builtin_is_503_without_a_schema() -> None:
    app, token = _app(loaded=False)
    with TestClient(app) as c:
        r = c.get("/api/handbrake-schema/builtin/x", headers=_auth(token))
    assert r.status_code == 503


def test_refresh_reports_the_runner_outcome() -> None:
    for error, expected in ((None, {"ok": True, "error": None}), ("boom", {"ok": False, "error": "boom"})):
        runner = _Runner(error)
        app, token = _app(runner=runner)
        with TestClient(app) as c:
            r = c.post("/api/handbrake-schema/refresh", headers=_auth(token))
        assert r.status_code == 200, r.text
        assert r.json() == expected
        assert runner.calls == 1


def test_refresh_needs_a_writer() -> None:
    runner = _Runner(None)
    app, token = _app(runner=runner, role="guest")
    with TestClient(app) as c:
        r = c.post("/api/handbrake-schema/refresh", headers=_auth(token))
    assert r.status_code == 403
    assert runner.calls == 0


def test_refresh_without_a_runner_is_503() -> None:
    app, token = _app()
    del app.state.handbrake_schema_runner
    with TestClient(app) as c:
        r = c.post("/api/handbrake-schema/refresh", headers=_auth(token))
    assert r.status_code == 503
    assert r.json() == {"detail": "No HandBrake schema runner in this Backend"}
