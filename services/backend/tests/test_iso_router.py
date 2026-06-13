"""POST /api/jobs/iso/scan — ISO-import scan validation (backend-only)."""

from __future__ import annotations

import os
import secrets

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import iso as iso_router  # noqa: E402
from arm_common import User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession) -> None:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]


def _make_app(signing_key: bytes, db: FakeSession, ingress: str) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.iso_ingress_root = ingress
    app.include_router(iso_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_scan_returns_suggestions(signing_key: bytes, tmp_path) -> None:
    (tmp_path / "Iron Man (2008).iso").write_bytes(b"x")
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, str(tmp_path))
    with TestClient(app) as client:
        r = client.post("/api/jobs/iso/scan", json={"path": "Iron Man (2008).iso"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["suggested_title"] == "Iron Man"
    assert body["suggested_year"] == 2008
    assert body["exists"] is True


def test_scan_traversal_rejected_400(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, str(tmp_path))
    with TestClient(app) as client:
        r = client.post("/api/jobs/iso/scan", json={"path": "../secret.iso"}, headers=_auth(token))
    assert r.status_code == 400


def test_scan_absolute_path_rejected_400(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, str(tmp_path))
    with TestClient(app) as client:
        r = client.post("/api/jobs/iso/scan", json={"path": "/etc/passwd"}, headers=_auth(token))
    assert r.status_code == 400


def test_scan_missing_file_rejected_400(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, str(tmp_path))
    with TestClient(app) as client:
        r = client.post("/api/jobs/iso/scan", json={"path": "nope.iso"}, headers=_auth(token))
    assert r.status_code == 400


def test_scan_non_iso_rejected_400(signing_key: bytes, tmp_path) -> None:
    (tmp_path / "movie.mkv").write_bytes(b"x")
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, str(tmp_path))
    with TestClient(app) as client:
        r = client.post("/api/jobs/iso/scan", json={"path": "movie.mkv"}, headers=_auth(token))
    assert r.status_code == 400


def test_scan_unauthenticated_401(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, _ = _make_app(signing_key, db, str(tmp_path))
    with TestClient(app) as client:
        r = client.post("/api/jobs/iso/scan", json={"path": "x.iso"})
    assert r.status_code == 401
