"""Users router: fixed admin+guest account management (list, disable, set-password)."""

from __future__ import annotations

import os
import secrets

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from argon2 import PasswordHasher  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import pytest  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import users as users_router  # noqa: E402
from arm_common import User  # noqa: E402
from arm_common.models.user import GUEST_ROLE  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402

_hasher = PasswordHasher()


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


@pytest.fixture
def admin_user() -> User:
    return User(
        id="usr_admin",
        username="admin",
        password_hash=_hasher.hash("hunter2-correct"),
        password_must_change=False,
    )


@pytest.fixture
def guest_user() -> User:
    return User(
        id="usr_guest",
        username="guest",
        password_hash=_hasher.hash("guestpass"),
        password_must_change=False,
        role=GUEST_ROLE,
        disabled=True,
    )


def _make_app(signing_key: bytes, db: FakeSession) -> FastAPI:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(users_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    return app


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed(db: FakeSession, admin_user: User, guest_user: User) -> None:
    db.rows["users"] = [admin_user, guest_user]


def test_list_users_returns_both_rows(signing_key: bytes, admin_user: User, guest_user: User) -> None:
    db = FakeSession()
    _seed(db, admin_user, guest_user)
    app = _make_app(signing_key, db)
    token, _ = issue_access_token(admin_user.id, admin_user.username, signing_key)

    with TestClient(app) as client:
        r = client.get("/api/users", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    by_username = {u["username"]: u for u in body}
    assert by_username.keys() == {"admin", "guest"}
    assert by_username["guest"]["disabled"] is True
    assert by_username["admin"]["disabled"] is False
    assert by_username["guest"]["role"] == "guest"
    assert by_username["admin"]["role"] == "admin"


def test_patch_guest_disabled_toggles(signing_key: bytes, admin_user: User, guest_user: User) -> None:
    db = FakeSession()
    _seed(db, admin_user, guest_user)
    app = _make_app(signing_key, db)
    token, _ = issue_access_token(admin_user.id, admin_user.username, signing_key)

    with TestClient(app) as client:
        r = client.patch(f"/api/users/{guest_user.id}", json={"disabled": False}, headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["disabled"] is False
    assert guest_user.disabled is False


def test_patch_admin_row_409(signing_key: bytes, admin_user: User, guest_user: User) -> None:
    db = FakeSession()
    _seed(db, admin_user, guest_user)
    app = _make_app(signing_key, db)
    token, _ = issue_access_token(admin_user.id, admin_user.username, signing_key)

    with TestClient(app) as client:
        r = client.patch(f"/api/users/{admin_user.id}", json={"disabled": True}, headers=_auth(token))
    assert r.status_code == 409


def test_set_guest_password_200(signing_key: bytes, admin_user: User, guest_user: User) -> None:
    db = FakeSession()
    _seed(db, admin_user, guest_user)
    app = _make_app(signing_key, db)
    token, _ = issue_access_token(admin_user.id, admin_user.username, signing_key)
    old_hash = guest_user.password_hash

    with TestClient(app) as client:
        r = client.post(
            f"/api/users/{guest_user.id}/password", json={"new_password": "newguestpass"}, headers=_auth(token)
        )
    assert r.status_code == 200
    assert guest_user.password_hash != old_hash
    _hasher.verify(guest_user.password_hash, "newguestpass")
    assert guest_user.password_must_change is False


def test_set_admin_password_409(signing_key: bytes, admin_user: User, guest_user: User) -> None:
    db = FakeSession()
    _seed(db, admin_user, guest_user)
    app = _make_app(signing_key, db)
    token, _ = issue_access_token(admin_user.id, admin_user.username, signing_key)

    with TestClient(app) as client:
        r = client.post(
            f"/api/users/{admin_user.id}/password", json={"new_password": "newadminpass"}, headers=_auth(token)
        )
    assert r.status_code == 409


def test_password_min_length_422(signing_key: bytes, admin_user: User, guest_user: User) -> None:
    db = FakeSession()
    _seed(db, admin_user, guest_user)
    app = _make_app(signing_key, db)
    token, _ = issue_access_token(admin_user.id, admin_user.username, signing_key)

    with TestClient(app) as client:
        r = client.post(
            f"/api/users/{guest_user.id}/password", json={"new_password": "short12"[:7]}, headers=_auth(token)
        )
    assert r.status_code == 422


def test_users_routes_guest_403(signing_key: bytes, admin_user: User, guest_user: User) -> None:
    guest_user.disabled = False  # disabled accounts 401 before reaching require_writer's 403
    db = FakeSession()
    _seed(db, admin_user, guest_user)
    app = _make_app(signing_key, db)
    token, _ = issue_access_token(guest_user.id, guest_user.username, signing_key)

    with TestClient(app) as client:
        r_list = client.get("/api/users", headers=_auth(token))
        r_patch = client.patch(f"/api/users/{guest_user.id}", json={"disabled": False}, headers=_auth(token))
        r_pw = client.post(
            f"/api/users/{guest_user.id}/password", json={"new_password": "irrelevant"}, headers=_auth(token)
        )
    assert r_list.status_code == 403
    assert r_patch.status_code == 403
    assert r_pw.status_code == 403


def test_unknown_user_404(signing_key: bytes, admin_user: User, guest_user: User) -> None:
    db = FakeSession()
    _seed(db, admin_user, guest_user)
    app = _make_app(signing_key, db)
    token, _ = issue_access_token(admin_user.id, admin_user.username, signing_key)

    with TestClient(app) as client:
        r = client.patch("/api/users/usr_nope", json={"disabled": True}, headers=_auth(token))
    assert r.status_code == 404
