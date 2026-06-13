"""test-key endpoint — MakeMKV tri-state validity read from stored Config fields."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import metadata as metadata_router  # noqa: E402
from arm_common import Config, User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession, **config_keys: str | bool | None) -> None:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["config"] = [Config(id=1, **config_keys)]


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.http = httpx.AsyncClient(timeout=5.0)
    app.include_router(metadata_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_test_key_makemkv_reads_stored_valid(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, makemkv_key="M-x", makemkv_key_valid=True, makemkv_key_state="valid")
    db.rows["config"][0].makemkv_key_checked_at = datetime.now(timezone.utc)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/test-key", params={"provider": "makemkv"}, headers=_auth(token))
    body = r.json()
    assert r.status_code == 200, r.text
    assert body["valid"] is True
    assert body["checked_at"] is not None


def test_test_key_makemkv_unknown_when_never_checked(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, makemkv_key="M-x")  # no valid/state/checked_at
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/test-key", params={"provider": "makemkv"}, headers=_auth(token))
    body = r.json()
    assert body["valid"] is None
    assert "not yet validated" in (body["detail"] or "")


def test_test_key_makemkv_invalid_state(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, makemkv_key="M-x", makemkv_key_valid=False, makemkv_key_state="binary_expired")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/test-key", params={"provider": "makemkv"}, headers=_auth(token))
    assert r.json()["valid"] is False
