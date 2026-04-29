"""UI JWT vs service token split — `require_jwt` and `require_service_token` reject the wrong type."""

from __future__ import annotations

import os
import secrets
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.auth import (  # noqa: E402
    looks_like_jwt,
    require_jwt,
    require_service_token,
)
from arm_backend.config import settings  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_common import User  # noqa: E402


def test_looks_like_jwt_predicate() -> None:
    # Real JWTs always have exactly two `.` separators.
    assert looks_like_jwt("aaa.bbb.ccc") is True
    assert looks_like_jwt("hex-only-service-token") is False
    assert looks_like_jwt("") is False
    assert looks_like_jwt("a.b") is False
    assert looks_like_jwt("a.b.c.d") is False


async def test_require_service_token_rejects_jwt_shaped_value() -> None:
    with pytest.raises(HTTPException) as ei:
        await require_service_token(authorization="Bearer aaa.bbb.ccc")
    assert ei.value.status_code == 401
    assert "service token" in ei.value.detail.lower()


async def test_require_service_token_rejects_missing_header() -> None:
    with pytest.raises(HTTPException) as ei:
        await require_service_token(authorization=None)
    assert ei.value.status_code == 401


async def test_require_service_token_rejects_wrong_token() -> None:
    with pytest.raises(HTTPException) as ei:
        await require_service_token(authorization="Bearer wrong-token-not-a-jwt")
    assert ei.value.status_code == 401
    assert "invalid service token" in ei.value.detail.lower()


async def test_require_service_token_accepts_real_token() -> None:
    # No exception → success.
    await require_service_token(authorization=f"Bearer {settings.ARM_SERVICE_TOKEN}")


class _FakeSession:
    def __init__(self, user: User | None) -> None:
        self._user = user

    async def execute(self, _stmt: Any) -> Any:
        result = MagicMock()
        result.scalar_one_or_none.return_value = self._user
        return result


def _request_with_state(signing_key: bytes | None, path: str = "/api/jobs") -> Any:
    req = MagicMock()
    req.app.state.signing_key = signing_key
    req.url.path = path
    return req


async def test_require_jwt_rejects_service_token_shaped_value() -> None:
    req = _request_with_state(secrets.token_bytes(32))
    sess = _FakeSession(user=None)
    with pytest.raises(HTTPException) as ei:
        await require_jwt(request=req, authorization="Bearer tok-service", session=sess)  # type: ignore[arg-type]
    assert ei.value.status_code == 401
    assert "user jwt" in ei.value.detail.lower() or "ui" in ei.value.detail.lower()


async def test_require_jwt_rejects_missing_signing_key() -> None:
    key = secrets.token_bytes(32)
    token, _ = issue_access_token("usr_abc", "alice", key)
    req = _request_with_state(signing_key=None)
    sess = _FakeSession(user=None)
    with pytest.raises(HTTPException) as ei:
        await require_jwt(request=req, authorization=f"Bearer {token}", session=sess)  # type: ignore[arg-type]
    assert ei.value.status_code == 500


async def test_require_jwt_rejects_unknown_user() -> None:
    key = secrets.token_bytes(32)
    token, _ = issue_access_token("usr_abc", "alice", key)
    req = _request_with_state(key)
    sess = _FakeSession(user=None)
    with pytest.raises(HTTPException) as ei:
        await require_jwt(request=req, authorization=f"Bearer {token}", session=sess)  # type: ignore[arg-type]
    assert ei.value.status_code == 401


async def test_require_jwt_returns_user_on_success() -> None:
    key = secrets.token_bytes(32)
    token, _ = issue_access_token("usr_abc", "alice", key)
    user = User(id="usr_abc", username="alice", password_hash="x", password_must_change=False)
    req = _request_with_state(key)
    sess = _FakeSession(user=user)
    got = await require_jwt(request=req, authorization=f"Bearer {token}", session=sess)  # type: ignore[arg-type]
    assert got.id == "usr_abc"


async def test_require_jwt_403s_must_change_user_on_non_whitelisted_route() -> None:
    key = secrets.token_bytes(32)
    token, _ = issue_access_token("usr_abc", "alice", key)
    user = User(id="usr_abc", username="alice", password_hash="x", password_must_change=True)
    req = _request_with_state(key, path="/api/jobs")
    sess = _FakeSession(user=user)
    with pytest.raises(HTTPException) as ei:
        await require_jwt(request=req, authorization=f"Bearer {token}", session=sess)  # type: ignore[arg-type]
    assert ei.value.status_code == 403
    assert "password change" in ei.value.detail.lower()


async def test_require_jwt_allows_must_change_user_on_password_route() -> None:
    key = secrets.token_bytes(32)
    token, _ = issue_access_token("usr_abc", "alice", key)
    user = User(id="usr_abc", username="alice", password_hash="x", password_must_change=True)
    req = _request_with_state(key, path="/api/auth/password")
    sess = _FakeSession(user=user)
    got = await require_jwt(request=req, authorization=f"Bearer {token}", session=sess)  # type: ignore[arg-type]
    assert got.id == "usr_abc"
