"""config.transcode_enabled: view exposure, NULL-as-enabled, PATCH toggle,
and the not-capable guard (ripper-only deployments can't turn it on)."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.config import Settings  # noqa: E402
from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import config as config_router  # noqa: E402
from arm_common import Config, User  # noqa: E402
from arm_common.enums import RetentionPolicy  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "DATABASE_URL": "postgresql://x:x@localhost/x",
        "ARM_SERVICE_TOKEN": "tok-service",
    }
    base.update(overrides)
    return Settings.model_construct(**base)


@pytest.fixture
def signing_key() -> bytes:
    import secrets

    return secrets.token_bytes(32)


@pytest.fixture
def db() -> FakeSession:
    fake = FakeSession()
    fake.rows["config"] = [
        Config(
            id=1,
            auto_transcode_on_idle=False,
            auto_rip_on_insert=True,
            block_on_miss=True,
            default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
            notification_apprise_urls=[],
            notifications_enabled=False,
            transcode_enabled=True,
        )
    ]
    fake.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    return fake


@pytest.fixture
def config_row(db: FakeSession) -> Config:
    return db.rows["config"][0]


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, dict[str, str]]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(config_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(signing_key: bytes, db: FakeSession) -> TestClient:
    app, auth = _make_app(signing_key, db)
    client = TestClient(app)
    client.headers.update(auth)
    return client


def test_get_exposes_transcode_flags(client: TestClient, config_row: Config) -> None:
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["transcode_enabled"] is True
    assert body["transcode_capable"] is True


def test_null_column_reads_as_enabled(client: TestClient, config_row: Config) -> None:
    config_row.transcode_enabled = None  # pre-backfill upgrade row
    r = client.get("/api/config")
    assert r.json()["transcode_enabled"] is True


def test_patch_toggle_roundtrip(client: TestClient, config_row: Config) -> None:
    r = client.patch("/api/config", json={"transcode_enabled": False})
    assert r.status_code == 200
    assert r.json()["transcode_enabled"] is False


def test_enable_refused_when_not_capable(
    client: TestClient, config_row: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force the deployment not-capable, then try to switch the toggle on.
    monkeypatch.setattr("arm_backend.routers.config.settings", _settings(ARM_TRANSCODE_CAPABLE=False))
    config_row.transcode_enabled = False
    r = client.patch("/api/config", json={"transcode_enabled": True})
    assert r.status_code == 422
    assert "ripper-only" in r.json()["detail"]


def test_patch_transcode_capable_is_forbidden(client: TestClient, config_row: Config) -> None:
    r = client.patch("/api/config", json={"transcode_capable": False})
    assert r.status_code == 400  # non-editable key, caught by the raw-body guard


def test_enable_allowed_when_capable_via_remote_host(
    client: TestClient, config_row: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ARM_TRANSCODE_CAPABLE=false but a remote docker host is configured: capable.
    monkeypatch.setattr(
        "arm_backend.routers.config.settings",
        _settings(ARM_TRANSCODE_CAPABLE=False, ARM_TRANSCODE_DOCKER_HOST="ssh://sam@transcoder-server"),
    )
    config_row.transcode_enabled = False
    r = client.patch("/api/config", json={"transcode_enabled": True})
    assert r.status_code == 200
    assert r.json()["transcode_enabled"] is True
