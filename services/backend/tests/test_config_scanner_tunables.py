"""drive_scan_interval_seconds / drive_detected_prune_days: view defaults, validation, round-trip."""

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
from arm_backend.routers import config as config_router  # noqa: E402
from arm_common import Config, User  # noqa: E402
from arm_common.enums import RetentionPolicy  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession) -> Config:
    # A bare in-memory Config carries None for server_default-only columns —
    # exactly the shape the view must coerce to the documented defaults.
    cfg = Config(
        id=1,
        auto_transcode_on_idle=False,
        auto_rip_on_insert=True,
        block_on_miss=True,
        default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
        notification_apprise_urls=[],
        notifications_enabled=False,
    )
    db.rows["config"] = [cfg]
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    return cfg


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, dict[str, str]]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(config_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, {"Authorization": f"Bearer {token}"}


def test_view_exposes_scanner_tunables_with_defaults(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, auth = _make_app(signing_key, db)
    with TestClient(app) as client:
        body = client.get("/api/config", headers=auth).json()
    assert body["drive_scan_interval_seconds"] == 30
    assert body["drive_detected_prune_days"] == 7


@pytest.mark.parametrize("payload", [{"drive_scan_interval_seconds": 0}, {"drive_detected_prune_days": -1}])
def test_update_rejects_non_positive_tunables(signing_key: bytes, payload: dict[str, int]) -> None:
    db = FakeSession()
    _seed(db)
    app, auth = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/config", json=payload, headers=auth)
    assert r.status_code == 400
    assert "positive integer" in r.json()["detail"]


def test_update_sets_scanner_tunables(signing_key: bytes) -> None:
    db = FakeSession()
    cfg = _seed(db)
    app, auth = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/config", json={"drive_scan_interval_seconds": 10, "drive_detected_prune_days": 3}, headers=auth
        )
        assert r.status_code == 200, r.text
        body = client.get("/api/config", headers=auth).json()
    assert (cfg.drive_scan_interval_seconds, cfg.drive_detected_prune_days) == (10, 3)
    assert (body["drive_scan_interval_seconds"], body["drive_detected_prune_days"]) == (10, 3)
