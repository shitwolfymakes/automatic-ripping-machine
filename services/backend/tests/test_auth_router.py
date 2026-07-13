"""End-to-end auth router tests via FastAPI TestClient + dep overrides."""

from __future__ import annotations

import os
import secrets
from typing import Any
from unittest.mock import MagicMock

import pytest
from argon2 import PasswordHasher
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.auth import require_writer  # noqa: E402
from arm_backend.db import get_session  # noqa: E402
from arm_backend.routers import auth as auth_router  # noqa: E402
from arm_common import User  # noqa: E402
from arm_common.models.user import GUEST_ROLE  # noqa: E402

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


def test_login_disabled_account_403(signing_key: bytes, admin_user: User) -> None:
    admin_user.disabled = True
    sess = _FakeSession(admin_user)
    app = _make_app(signing_key, sess)
    with TestClient(app) as client:
        r = client.post("/api/auth/login", json={"username": "admin", "password": "hunter2-correct"})
    assert r.status_code == 403
    assert r.json()["detail"] == "account disabled"


def test_require_jwt_rejects_disabled_user(signing_key: bytes, admin_user: User) -> None:
    from arm_backend.auth import require_jwt
    from arm_backend.jwt_utils import issue_access_token

    admin_user.disabled = True
    sess = _FakeSession(admin_user)
    app = FastAPI()
    app.state.signing_key = signing_key

    @app.get("/probe")
    async def _probe(user: User = Depends(require_jwt)) -> dict[str, str]:
        return {"id": user.id}

    async def _override_session() -> _FakeSession:
        return sess

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token(admin_user.id, admin_user.username, signing_key)

    with TestClient(app) as client:
        r = client.get("/probe", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_require_writer_admin_passes_guest_403(signing_key: bytes) -> None:
    from arm_backend.jwt_utils import issue_access_token

    admin_user = User(
        id="usr_admin2",
        username="admin2",
        password_hash=_hasher.hash("irrelevant"),
        password_must_change=False,
        role="admin",
    )
    guest_user = User(
        id="usr_guest",
        username="guest",
        password_hash=_hasher.hash("irrelevant"),
        password_must_change=False,
        role=GUEST_ROLE,
    )

    def _make_probe_app(user: User) -> tuple[FastAPI, _FakeSession]:
        sess = _FakeSession(user)
        app = FastAPI()
        app.state.signing_key = signing_key

        @app.get("/probe")
        async def _probe(user: User = Depends(require_writer)) -> dict[str, str]:
            return {"id": user.id}

        async def _override_session() -> _FakeSession:
            return sess

        app.dependency_overrides[get_session] = _override_session
        return app, sess

    admin_app, _ = _make_probe_app(admin_user)
    admin_token, _ = issue_access_token(admin_user.id, admin_user.username, signing_key)
    with TestClient(admin_app) as client:
        r = client.get("/probe", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200

    guest_app, _ = _make_probe_app(guest_user)
    guest_token, _ = issue_access_token(guest_user.id, guest_user.username, signing_key)
    with TestClient(guest_app) as client:
        r = client.get("/probe", headers={"Authorization": f"Bearer {guest_token}"})
    assert r.status_code == 403
    assert r.json()["detail"] == "read-only role: write access required"


def test_login_response_includes_role(signing_key: bytes, admin_user: User) -> None:
    sess = _FakeSession(admin_user)
    app = _make_app(signing_key, sess)
    with TestClient(app) as client:
        r = client.post("/api/auth/login", json={"username": "admin", "password": "hunter2-correct"})
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def _guest_user(disabled: bool = False) -> User:
    return User(
        id="usr_guest",
        username="guest",
        password_hash=_hasher.hash("irrelevant"),
        password_must_change=False,
        role=GUEST_ROLE,
        disabled=disabled,
    )


def _make_probe_app(signing_key: bytes, sess: _FakeSession) -> FastAPI:
    from arm_backend.auth import require_jwt

    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(auth_router.router)

    @app.get("/probe-read")
    async def _probe_read(user: User = Depends(require_jwt)) -> dict[str, str]:
        return {"id": user.id}

    @app.get("/probe-write")
    async def _probe_write(user: User = Depends(require_writer)) -> dict[str, str]:
        return {"id": user.id}

    async def _override_session() -> _FakeSession:
        return sess

    app.dependency_overrides[get_session] = _override_session
    return app


def test_anonymous_read_acts_as_guest(signing_key: bytes) -> None:
    guest_user = _guest_user()
    sess = _FakeSession(guest_user)
    app = _make_probe_app(signing_key, sess)
    with TestClient(app) as client:
        r = client.get("/probe-read")
    assert r.status_code == 200
    assert r.json()["id"] == guest_user.id


def test_anonymous_write_403_role_denied(signing_key: bytes) -> None:
    guest_user = _guest_user()
    sess = _FakeSession(guest_user)
    app = _make_probe_app(signing_key, sess)
    with TestClient(app) as client:
        r = client.get("/probe-write")
    assert r.status_code == 403
    assert r.json()["detail"] == "read-only role: write access required"


def test_anonymous_guest_disabled_401(signing_key: bytes) -> None:
    guest_user = _guest_user(disabled=True)
    sess = _FakeSession(guest_user)
    app = _make_probe_app(signing_key, sess)
    with TestClient(app) as client:
        r = client.get("/probe-read")
    assert r.status_code == 401
    assert r.json()["detail"] == "authentication required"


def test_anonymous_guest_row_missing_500(signing_key: bytes) -> None:
    sess = _FakeSession(user=None)
    app = _make_probe_app(signing_key, sess)
    with TestClient(app) as client:
        r = client.get("/probe-read")
    assert r.status_code == 500
    assert r.json()["detail"] == "guest account missing"


def test_present_invalid_token_still_401(signing_key: bytes) -> None:
    guest_user = _guest_user()
    sess = _FakeSession(guest_user)
    app = _make_probe_app(signing_key, sess)
    with TestClient(app) as client:
        r = client.get("/probe-read", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401
