"""POST /api/ripper/keydb-status — writes community-keydb fetch outcome to Config singleton."""

from __future__ import annotations

import os
import secrets

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.routers import ripper as ripper_router  # noqa: E402
from arm_common import Config  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402

_SERVICE_AUTH = {"Authorization": "Bearer tok-service"}


def _app(db: FakeSession) -> FastAPI:
    app = FastAPI()
    app.state.signing_key = secrets.token_bytes(32)
    app.state.dispatcher = None
    app.state.ws_hub = None
    app.include_router(ripper_router.router)

    async def _sess() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _sess
    return app


def test_keydb_status_writes_config_singleton() -> None:
    db = FakeSession()
    db.rows["config"] = [Config(id=1)]
    app = _app(db)
    with TestClient(app) as c:
        r = c.post(
            "/api/ripper/keydb-status",
            json={"state": "ok", "vuk_count": 4200, "age_days": 0},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 204, r.text
    cfg = db.rows["config"][0]
    assert cfg.community_keydb_state == "ok"
    assert cfg.community_keydb_vuk_count == 4200
    assert cfg.community_keydb_checked_at is not None


def test_keydb_status_no_config_returns_404() -> None:
    db = FakeSession()
    db.rows["config"] = []
    app = _app(db)
    with TestClient(app) as c:
        r = c.post("/api/ripper/keydb-status", json={"state": "download_failed"}, headers=_SERVICE_AUTH)
    assert r.status_code == 404
