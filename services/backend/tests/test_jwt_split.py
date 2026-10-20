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
    require_writer,
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


def test_openapi_declares_the_auth_schemes() -> None:
    """The wire contract names the scheme each route needs (D-183)."""
    from arm_backend.main import app

    schema = app.openapi()
    schemes = schema["components"]["securitySchemes"]
    assert schemes["UserJWT"]["scheme"] == "bearer"
    assert schemes["UserJWT"]["bearerFormat"] == "JWT"
    assert schemes["ServiceToken"]["scheme"] == "bearer"
    paths = schema["paths"]
    assert paths["/api/config"]["get"]["security"] == [{"UserJWT": []}, {}]
    assert paths["/api/config"]["patch"]["security"] == [{"UserJWT": []}]
    ripper_ops = [op for path, ops in paths.items() if path.startswith("/api/ripper/") for op in ops.values()]
    assert ripper_ops and all(op["security"] == [{"ServiceToken": []}] for op in ripper_ops)
    assert "security" not in paths["/api/setup/status"]["get"]


def test_openapi_splits_guest_reads_from_writer_only_operations() -> None:
    """Every UserJWT operation is either guest-readable (token optional, so an
    extra empty requirement) or writer-only (token required) (D-244)."""
    from arm_backend.main import app

    user_ops = {
        (method, path): op["security"]
        for path, ops in app.openapi()["paths"].items()
        for method, op in ops.items()
        if any("UserJWT" in requirement for requirement in op.get("security", []))
    }
    guest_readable = {key for key, security in user_ops.items() if security == [{"UserJWT": []}, {}]}
    writer_only = {key for key, security in user_ops.items() if security == [{"UserJWT": []}]}
    assert guest_readable | writer_only == set(user_ops)
    assert ("get", "/api/jobs") in guest_readable
    assert ("post", "/api/drives/rescan") in guest_readable
    assert ("get", "/api/users") in writer_only
    assert ("delete", "/api/jobs/{job_id}") in writer_only


def test_declare_guest_reads_marks_only_require_jwt_routes() -> None:
    """The marker follows the dependency tree: `require_jwt` alone is guest-
    readable, `require_writer` (which wraps it) is not, and service-token and
    open routes are left untouched."""
    from fastapi import Depends, FastAPI, WebSocket

    from arm_backend.auth import declare_guest_reads

    app = FastAPI()

    @app.get("/read")
    async def read(_: User = Depends(require_jwt)) -> None: ...

    @app.post("/write")
    async def write(_: User = Depends(require_writer)) -> None: ...

    @app.post("/svc", dependencies=[Depends(require_service_token)])
    async def svc() -> None: ...

    @app.get("/open")
    async def open_route() -> None: ...

    @app.websocket("/ws")
    async def ws(_websocket: WebSocket) -> None: ...

    declare_guest_reads(app.routes)
    paths = app.openapi()["paths"]
    assert paths["/read"]["get"]["security"] == [{"UserJWT": []}, {}]
    assert paths["/write"]["post"]["security"] == [{"UserJWT": []}]
    assert paths["/svc"]["post"]["security"] == [{"ServiceToken": []}]
    assert "security" not in paths["/open"]["get"]


def test_malformed_header_never_falls_back_to_guest_over_http() -> None:
    """The scheme dep hands over the raw header, so a non-Bearer value is still
    a 401 rather than an anonymous (guest) request."""
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from arm_backend.db import get_session

    app = FastAPI()

    @app.get("/ui")
    async def ui(_: User = Depends(require_jwt)) -> dict[str, bool]:
        return {"ok": True}

    @app.get("/svc", dependencies=[Depends(require_service_token)])
    async def svc() -> dict[str, bool]:
        return {"ok": True}

    async def _no_session() -> Any:
        yield None

    app.dependency_overrides[get_session] = _no_session
    client = TestClient(app)
    resp = client.get("/ui", headers={"Authorization": "Basic abc"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "missing bearer token"
    assert client.get("/svc", headers={"Authorization": f"Bearer {settings.ARM_SERVICE_TOKEN}"}).status_code == 200
    assert client.get("/svc").status_code == 401
