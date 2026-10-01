"""Must-change-password lock: the read-only GETs the setup walkthrough's step 1
needs stay open (exact path, GET only); everything else stays locked."""

from __future__ import annotations

import os
import secrets

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.auth import require_jwt  # noqa: E402
from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_common import User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


def _app(key: bytes) -> FastAPI:
    app = FastAPI()
    app.state.signing_key = key
    db = FakeSession()
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=True)]

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override

    def ok(_: User = Depends(require_jwt)) -> dict[str, bool]:
        return {"ok": True}

    for path in ("/api/system/version", "/api/system/resources", "/api/setup", "/api/setup/disc-routes"):
        app.add_api_route(path, ok, methods=["GET"])
    app.add_api_route("/api/setup", ok, methods=["POST"])
    app.add_api_route("/api/setup/steps/system", ok, methods=["PUT"])
    app.add_api_route("/api/jobs", ok, methods=["GET"])
    return app


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("GET", "/api/system/version", 200),
        ("GET", "/api/system/resources", 200),
        ("GET", "/api/setup", 200),
        ("GET", "/api/setup/disc-routes", 403),  # exact match only
        ("POST", "/api/setup", 403),  # GET only
        ("PUT", "/api/setup/steps/system", 403),
        ("GET", "/api/jobs", 403),
    ],
)
def test_must_change_allow_list(method: str, path: str, expected: int) -> None:
    key = secrets.token_bytes(32)
    token, _ = issue_access_token("usr_admin", "admin", key)
    with TestClient(_app(key)) as c:
        r = c.request(method, path, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == expected, (method, path, r.text)
