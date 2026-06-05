"""End-to-end auth router tests via FastAPI TestClient + dep overrides."""

from __future__ import annotations

import os
import secrets
from typing import Any
from unittest.mock import MagicMock

import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.db import get_session  # noqa: E402
from arm_backend.routers import auth as auth_router  # noqa: E402
from arm_common import User  # noqa: E402

_hasher = PasswordHasher()


class _FakeSession:
    def __init__(self, user: User | None) -> None:
        self.user = user
        self.committed = 0

    async def execute(self, _stmt: Any) -> Any:
        result = MagicMock()
        result.scalar_one_or_none.return_value = self.user
        return result

    async def commit(self) -> None:
        self.committed += 1

    async def refresh(self, _obj: Any) -> None:
        return None

    def add(self, _obj: Any) -> None:
        return None


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


@pytest.fixture
def admin_user() -> User:
    return User(
        id="usr_admin",
        username="admin",
        password_hash=_hasher.hash("hunter2-correct"),
        password_must_change=True,
    )


def _make_app(signing_key: bytes, session: _FakeSession) -> FastAPI:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(auth_router.router)

    async def _override_session() -> _FakeSession:
        return session

    app.dependency_overrides[get_session] = _override_session
    return app


def test_login_success_returns_jwt_and_must_change(signing_key: bytes, admin_user: User) -> None:
    sess = _FakeSession(admin_user)
    app = _make_app(signing_key, sess)
    with TestClient(app) as client:
        r = client.post("/api/auth/login", json={"username": "admin", "password": "hunter2-correct"})
    assert r.status_code == 200
    body = r.json()
    assert body["password_must_change"] is True
    assert body["access_token"].count(".") == 2
    assert "expires_at" in body


def test_login_unknown_user_401(signing_key: bytes) -> None:
    sess = _FakeSession(user=None)
    app = _make_app(signing_key, sess)
    with TestClient(app) as client:
        r = client.post("/api/auth/login", json={"username": "ghost", "password": "x"})
    assert r.status_code == 401


def test_login_wrong_password_401(signing_key: bytes, admin_user: User) -> None:
    sess = _FakeSession(admin_user)
    app = _make_app(signing_key, sess)
    with TestClient(app) as client:
        r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_password_change_clears_must_change(signing_key: bytes, admin_user: User) -> None:
    from arm_backend.jwt_utils import issue_access_token

    sess = _FakeSession(admin_user)
    app = _make_app(signing_key, sess)
    token, _ = issue_access_token(admin_user.id, admin_user.username, signing_key)

    with TestClient(app) as client:
        r = client.post(
            "/api/auth/password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": "hunter2-correct", "new_password": "newpassword123"},
        )
    assert r.status_code == 200
    assert admin_user.password_must_change is False
    # Hash rotated.
    _hasher.verify(admin_user.password_hash, "newpassword123")


def test_password_change_rejects_wrong_current(signing_key: bytes, admin_user: User) -> None:
    from arm_backend.jwt_utils import issue_access_token

    sess = _FakeSession(admin_user)
    app = _make_app(signing_key, sess)
    token, _ = issue_access_token(admin_user.id, admin_user.username, signing_key)

    with TestClient(app) as client:
        r = client.post(
            "/api/auth/password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": "WRONG", "new_password": "newpassword123"},
        )
    assert r.status_code == 401
    assert admin_user.password_must_change is True


def test_password_change_rejects_same_password(signing_key: bytes, admin_user: User) -> None:
    from arm_backend.jwt_utils import issue_access_token

    sess = _FakeSession(admin_user)
    app = _make_app(signing_key, sess)
    token, _ = issue_access_token(admin_user.id, admin_user.username, signing_key)

    with TestClient(app) as client:
        r = client.post(
            "/api/auth/password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": "hunter2-correct", "new_password": "hunter2-correct"},
        )
    assert r.status_code == 400


def test_logout_is_noop(signing_key: bytes) -> None:
    sess = _FakeSession(user=None)
    app = _make_app(signing_key, sess)
    with TestClient(app) as client:
        r = client.post("/api/auth/logout")
    assert r.status_code == 200
    assert r.json()["ok"] is True
