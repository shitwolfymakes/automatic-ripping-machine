"""POST /api/ripper/makemkv-key-status — writes makemkv key probe outcome to Config singleton."""

from __future__ import annotations

import os
import secrets

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
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


@pytest.mark.parametrize(
    "state,expected_valid",
    [
        ("valid", True),
        ("unregistered_or_expired", False),
        ("binary_expired", False),
        ("format_invalid", False),
        ("probe_failed", None),
    ],
)
def test_report_writes_valid_and_state(state: str, expected_valid: bool | None) -> None:
    db = FakeSession()
    db.rows["config"] = [Config(id=1)]
    app = _app(db)
    with TestClient(app) as c:
        r = c.post("/api/ripper/makemkv-key-status", json={"state": state, "detail": "d"}, headers=_SERVICE_AUTH)
    assert r.status_code == 204, r.text
    cfg = db.rows["config"][0]
    assert cfg.makemkv_key_state == state
    assert cfg.makemkv_key_valid is expected_valid
    assert cfg.makemkv_key_checked_at is not None


def test_report_no_config_returns_404() -> None:
    db = FakeSession()
    db.rows["config"] = []
    app = _app(db)
    with TestClient(app) as c:
        r = c.post("/api/ripper/makemkv-key-status", json={"state": "valid"}, headers=_SERVICE_AUTH)
    assert r.status_code == 404
