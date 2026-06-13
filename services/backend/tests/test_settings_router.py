from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import secrets  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import settings as settings_router  # noqa: E402
from arm_common import User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


def _app() -> tuple[FastAPI, str]:
    key = secrets.token_bytes(32)
    db = FakeSession()
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]

    app = FastAPI()
    app.state.signing_key = key
    app.include_router(settings_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", key)
    return app, token


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_schema_returns_grouped_fields():
    app, token = _app()
    with TestClient(app) as c:
        r = c.get("/api/settings/schema", headers=_auth(token))
    assert r.status_code == 200, r.text
    groups = {g["name"] for g in r.json()["groups"]}
    assert {"Metadata", "Ripping", "Transcoding", "Notifications", "System"} <= groups
    all_fields = [f for g in r.json()["groups"] for f in g["fields"]]
    by_key = {f["key"]: f for f in all_fields}
    assert by_key["omdb_api_key"]["tier"] == "secret"
    assert by_key["metadata_provider"]["type"] == "enum"
    assert by_key["MEDIA_ROOT"]["editable"] is False


def test_schema_requires_jwt():
    app, _ = _app()
    with TestClient(app) as c:
        r = c.get("/api/settings/schema")
    assert r.status_code == 401
