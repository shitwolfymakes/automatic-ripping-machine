"""config.transcode_enabled: view exposure, NULL-as-enabled, PATCH toggle,
and the not-capable guard (ripper-only deployments can't turn it on)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.config import Settings  # noqa: E402
from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import config as config_router  # noqa: E402
from arm_common import Config, JobStatus, SessionApplication, SessionApplicationStatus, User  # noqa: E402
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


def test_patch_rejects_explicit_null_toggle(client: TestClient, config_row: Config) -> None:
    r = client.patch("/api/config", json={"transcode_enabled": None})
    assert r.status_code == 400
    assert "transcode_enabled" in r.json()["detail"]
    assert config_row.transcode_enabled is True


# --- re-drain on re-enable ------------------------------------------------


def _seed_parked_encode(db: FakeSession, *, job_status: JobStatus) -> None:
    from tests.test_auto_session import _seed as seed_job

    seed_job(db, job_status=job_status)
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_encode",
            session_id="ses_x",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            status=SessionApplicationStatus.WAITING_IDENTIFY,
            overwrite=False,
        )
    ]


@pytest.fixture
def media_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from arm_backend import config as bcfg

    monkeypatch.setattr(bcfg.settings, "MEDIA_ROOT", str(tmp_path))
    return tmp_path


def _client_with_hub(signing_key: bytes, db: FakeSession) -> tuple[TestClient, Any]:
    from tests.test_auto_session import CapturingHub

    app, auth = _make_app(signing_key, db)
    hub = CapturingHub()
    app.state.ws_hub = hub
    c = TestClient(app)
    c.headers.update(auth)
    return c, hub


@pytest.mark.parametrize("job_status", [JobStatus.RIPPED, JobStatus.RIPPED_PARTIAL, JobStatus.IDENTIFIED])
def test_reenable_promotes_encode_application_parked_while_disabled(
    signing_key: bytes, db: FakeSession, config_row: Config, media_root: Path, job_status: JobStatus
) -> None:
    """An encode application that reached the parked-application drain while
    transcoding was off stays WAITING_IDENTIFY; switching the toggle back on
    re-drains it, promoting it to QUEUED with its tasks fanned out."""
    config_row.transcode_enabled = False
    _seed_parked_encode(db, job_status=job_status)
    c, hub = _client_with_hub(signing_key, db)

    r = c.patch("/api/config", json={"transcode_enabled": True})

    assert r.status_code == 200, r.text
    assert r.json()["transcode_enabled"] is True
    app_row = db.rows["session_applications"][0]
    assert app_row.status == SessionApplicationStatus.QUEUED
    assert len(db.rows["transcode_tasks"]) == 1
    assert db.rows["transcode_tasks"][0].session_application_id == "sap_encode"
    assert any(e["event_type"] == "session.queued" for e in hub.events)


def test_patch_without_transition_does_not_redrain(
    signing_key: bytes, db: FakeSession, config_row: Config, media_root: Path
) -> None:
    """Already enabled -> enabled is not a re-enable; parked rows are left to
    the normal after-rip / resolve drains."""
    config_row.transcode_enabled = True
    _seed_parked_encode(db, job_status=JobStatus.RIPPED)
    c, _hub = _client_with_hub(signing_key, db)

    r = c.patch("/api/config", json={"transcode_enabled": True})

    assert r.status_code == 200
    assert db.rows["session_applications"][0].status == SessionApplicationStatus.WAITING_IDENTIFY
    assert db.rows["transcode_tasks"] == []


def test_reenable_leaves_identity_pending_jobs_parked(
    signing_key: bytes, db: FakeSession, config_row: Config, media_root: Path
) -> None:
    """A job still awaiting identity keeps its application parked; resolve
    promotes it once identity lands."""
    config_row.transcode_enabled = False
    _seed_parked_encode(db, job_status=JobStatus.RIPPED_AWAITING_IDENTIFY)
    c, _hub = _client_with_hub(signing_key, db)

    r = c.patch("/api/config", json={"transcode_enabled": True})

    assert r.status_code == 200
    assert db.rows["session_applications"][0].status == SessionApplicationStatus.WAITING_IDENTIFY
    assert db.rows["transcode_tasks"] == []


def test_reenable_with_nothing_parked_is_a_noop(
    signing_key: bytes, db: FakeSession, config_row: Config, media_root: Path
) -> None:
    config_row.transcode_enabled = False
    db.rows["session_applications"] = []
    c, _hub = _client_with_hub(signing_key, db)

    r = c.patch("/api/config", json={"transcode_enabled": True})

    assert r.status_code == 200
    assert r.json()["transcode_enabled"] is True


def test_reenable_redrain_failure_never_fails_the_patch(
    signing_key: bytes, db: FakeSession, config_row: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The toggle is already committed when the re-drain runs; a failure while
    listing parked applications is logged and swallowed."""
    config_row.transcode_enabled = False
    real_execute = db.execute
    calls = {"n": 0}

    async def _execute(stmt: Any, *args: Any, **kwargs: Any) -> Any:
        if "session_applications" in str(stmt):
            calls["n"] += 1
            raise RuntimeError("db went away")
        return await real_execute(stmt, *args, **kwargs)

    monkeypatch.setattr(db, "execute", _execute)
    c, _hub = _client_with_hub(signing_key, db)

    r = c.patch("/api/config", json={"transcode_enabled": True})

    assert r.status_code == 200
    assert r.json()["transcode_enabled"] is True
    assert calls["n"] == 1
