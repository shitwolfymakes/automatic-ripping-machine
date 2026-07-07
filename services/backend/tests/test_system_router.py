"""GET /api/system/preflight, /paths, /stats."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import system as system_router  # noqa: E402
from arm_common import Config, DiscType, Drive, DriveStatus, Event, Job, JobStatus, User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession) -> None:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["config"] = [Config(id=1)]
    db.rows["drives"] = [
        Drive(id="drv_on0000000000000000000001", hostname="h1", device_path="/dev/sr0", status=DriveStatus.ONLINE),
        Drive(id="drv_off000000000000000000002", hostname="h2", device_path="/dev/sr1", status=DriveStatus.OFFLINE),
    ]
    db.rows["jobs"] = [
        Job(
            id="job_0000000000000000000000001",
            drive_id="drv_on0000000000000000000001",
            disc_type=DiscType.DVD,
            status=JobStatus.RIPPING,
        ),
        Job(
            id="job_0000000000000000000000002",
            drive_id="drv_on0000000000000000000001",
            disc_type=DiscType.DVD,
            status=JobStatus.RIPPED,
        ),
    ]
    db.rows["events"] = [
        Event(id="evt_0000000000000000000000001", event_type="rip.completed", notified_at=None),
        Event(id="evt_0000000000000000000000002", event_type="rip.completed", notified_at=datetime.now(timezone.utc)),
    ]


def _make_app(signing_key: bytes, db: FakeSession, *, ingress_ok: bool, tmp) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.started_at = datetime.now(timezone.utc) - timedelta(seconds=42)
    # transcode_dispatcher intentionally NOT set; tests that need it set it directly on app.state
    media = tmp / "media"
    media.mkdir()
    raw = tmp / "raw"
    raw.mkdir()
    logs = tmp / "logs"
    logs.mkdir()
    ingress = tmp / "ingress"
    if ingress_ok:
        ingress.mkdir()
    app.state.system_paths = {
        "MEDIA_ROOT": str(media),
        "RAW_ROOT": str(raw),
        "LOG_DIR": str(logs),
        "ISO_INGRESS_ROOT": str(ingress),
    }
    app.include_router(system_router.router)

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_preflight_ok(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["status"] in {"ok", "warning"}
    names = {ch["name"] for ch in r.json()["checks"]}
    assert "MEDIA_ROOT" in names


def test_preflight_missing_ingress_is_warning(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, ingress_ok=False, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    assert r.status_code == 200, r.text
    ingress = next(ch for ch in r.json()["checks"] if ch["name"] == "ISO_INGRESS_ROOT")
    assert ingress["status"] == "warning"


def test_preflight_missing_required_root_is_error(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    # Point MEDIA_ROOT at a non-existent dir.
    app.state.system_paths["MEDIA_ROOT"] = str(tmp_path / "does-not-exist")
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "error"
    media = next(ch for ch in r.json()["checks"] if ch["name"] == "MEDIA_ROOT")
    assert media["status"] == "error"


def test_paths_shape(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/paths", headers=_auth(token))
    assert r.status_code == 200, r.text
    media = next(p for p in r.json()["paths"] if p["name"] == "MEDIA_ROOT")
    assert media["exists"] is True and media["writable"] is True


def test_stats_counts(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/stats", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["uptime_seconds"] >= 40
    assert body["drives_online"] == 1
    assert body["events_unsent"] == 1
    assert body["jobs_by_status"].get("ripping") == 1


def test_preflight_no_drives_is_warning(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["drives"] = []
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    assert r.status_code == 200, r.text
    drives = next(ch for ch in r.json()["checks"] if ch["name"] == "drives")
    assert drives["status"] == "warning"


def test_preflight_unauthenticated_401(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, _ = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight")
    assert r.status_code == 401


def test_preflight_config_missing_is_error(signing_key: bytes, tmp_path) -> None:
    """If the config singleton is absent, the config check should be 'error'."""
    db = FakeSession()
    _seed(db)
    db.rows["config"] = []
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    assert r.status_code == 200, r.text
    cfg_check = next(ch for ch in r.json()["checks"] if ch["name"] == "config")
    assert cfg_check["status"] == "error"
    assert r.json()["status"] == "error"


def test_stats_no_started_at(signing_key: bytes, tmp_path) -> None:
    """When started_at is not set on app.state, uptime_seconds should be 0."""
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    del app.state.started_at
    with TestClient(app) as c:
        r = c.get("/api/system/stats", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["uptime_seconds"] == 0


def test_system_version(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as client:
        r = client.get("/api/system/version", headers=_auth(token))
    assert r.status_code == 200
    assert isinstance(r.json()["version"], str) and r.json()["version"]


def test_app_version_env_override_wins(monkeypatch) -> None:
    from arm_backend.routers import system as system_router_mod

    monkeypatch.setenv("ARM_VERSION", "9.9.9-test")
    system_router_mod._app_version.cache_clear()
    try:
        assert system_router_mod._app_version() == "9.9.9-test"
    finally:
        system_router_mod._app_version.cache_clear()


def test_app_version_reads_version_file(monkeypatch, tmp_path) -> None:
    """The canonical VERSION file (baked into the image at /app/VERSION,
    repo root in dev) is the source of truth — not the static pyproject
    version, which is pinned 0.0.0."""
    from arm_backend.routers import system as system_router_mod

    vfile = tmp_path / "VERSION"
    vfile.write_text("3.1.4-test\n")
    monkeypatch.delenv("ARM_VERSION", raising=False)
    monkeypatch.setattr(system_router_mod, "_VERSION_FILE_CANDIDATES", (vfile,))
    system_router_mod._app_version.cache_clear()
    try:
        assert system_router_mod._app_version() == "3.1.4-test"
    finally:
        system_router_mod._app_version.cache_clear()


def test_system_version_requires_auth(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, _ = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/system/version").status_code == 401


def test_app_version_real_fallback(monkeypatch) -> None:
    import importlib.metadata

    from arm_backend.routers import system as system_router_mod

    def _raise(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError("arm_backend")

    monkeypatch.delenv("ARM_VERSION", raising=False)
    monkeypatch.setattr(system_router_mod, "_VERSION_FILE_CANDIDATES", ())
    monkeypatch.setattr(importlib.metadata, "version", _raise)
    system_router_mod._app_version.cache_clear()
    try:
        assert system_router_mod._app_version() == "0.0.0+unknown"
    finally:
        system_router_mod._app_version.cache_clear()


def test_preflight_includes_makemkv_key_check_ok(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"][0].makemkv_key = "M-x"
    db.rows["config"][0].makemkv_key_valid = True
    db.rows["config"][0].makemkv_key_state = "valid"
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    checks = {ch["name"]: ch for ch in r.json()["checks"]}
    assert checks["makemkv_key"]["status"] == "ok"


def test_preflight_makemkv_key_warning_when_unknown(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"][0].makemkv_key = "M-x"
    # makemkv_key_valid defaults to None → never checked
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    checks = {ch["name"]: ch for ch in r.json()["checks"]}
    assert checks["makemkv_key"]["status"] == "warning"


def test_preflight_makemkv_key_error_when_invalid(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"][0].makemkv_key = "M-x"
    db.rows["config"][0].makemkv_key_valid = False
    db.rows["config"][0].makemkv_key_state = "binary_expired"
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    checks = {ch["name"]: ch for ch in r.json()["checks"]}
    assert checks["makemkv_key"]["status"] == "error"


def test_paths_uses_settings_fallback(signing_key: bytes) -> None:
    """When system_paths is absent from app.state, _roots falls back to settings."""
    db = FakeSession()
    _seed(db)
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(system_router.router)

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override
    token, _ = issue_access_token("usr_admin", "admin", signing_key)

    with TestClient(app) as c:
        r = c.get("/api/system/paths", headers=_auth(token))
    assert r.status_code == 200, r.text
    names = {p["name"] for p in r.json()["paths"]}
    # settings defaults include MEDIA_ROOT, RAW_ROOT, ISO_INGRESS_ROOT, LOG_DIR
    assert "MEDIA_ROOT" in names


class _StubDispatcher:
    """Minimal stand-in for TranscodeDispatcher exposing only the gate the
    preflight check reads. A real dispatcher needs a docker client + settings,
    which the Tier-1 fake-session suite has no business constructing."""

    def __init__(self, *, host_paths: bool) -> None:
        self._host_paths = host_paths

    def host_paths_set(self) -> bool:
        return self._host_paths


def test_preflight_transcoder_warning_when_no_dispatcher(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    # _make_app does not set app.state.transcode_dispatcher → getattr falls to None
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    assert r.status_code == 200, r.text
    check = next(ch for ch in r.json()["checks"] if ch["name"] == "transcoder")
    assert check["status"] == "warning"
    assert "docker" in check["detail"]


def test_preflight_transcoder_warning_when_host_paths_unset(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    app.state.transcode_dispatcher = _StubDispatcher(host_paths=False)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    assert r.status_code == 200, r.text
    check = next(ch for ch in r.json()["checks"] if ch["name"] == "transcoder")
    assert check["status"] == "warning"
    assert "ARM_HOST" in check["detail"]


def test_preflight_transcoder_ok_when_live(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    app.state.transcode_dispatcher = _StubDispatcher(host_paths=True)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    assert r.status_code == 200, r.text
    check = next(ch for ch in r.json()["checks"] if ch["name"] == "transcoder")
    assert check["status"] == "ok"
    assert check["detail"] is None


@pytest.mark.parametrize(
    "state,expected_status",
    [
        ("ok", "ok"),
        ("fresh_kept", "ok"),
        ("disabled", "ok"),
        ("download_failed", "warning"),
        ("empty", "warning"),
        ("probe_failed", "warning"),
        (None, "warning"),
    ],
)
def test_preflight_community_keydb_check(signing_key: bytes, tmp_path, state, expected_status) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"][0].community_keydb_state = state
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    assert r.status_code == 200, r.text
    check = next(ch for ch in r.json()["checks"] if ch["name"] == "community_keydb")
    assert check["status"] == expected_status


def test_preflight_community_keydb_ok_reports_vuk_count(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"][0].community_keydb_state = "ok"
    db.rows["config"][0].community_keydb_vuk_count = 4200
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    assert r.status_code == 200, r.text
    check = next(ch for ch in r.json()["checks"] if ch["name"] == "community_keydb")
    assert check["detail"] == "4200 VUK keys installed"


def test_preflight_overall_not_error_when_only_transcoder_warns(signing_key: bytes, tmp_path) -> None:
    # ingress_ok=True means roots are fine; dispatcher absent → transcoder warns.
    # Overall must be "warning" (degraded), never promoted to "error".
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    body = r.json()
    transcoder = next(ch for ch in body["checks"] if ch["name"] == "transcoder")
    assert transcoder["status"] == "warning"
    assert body["status"] == "warning"


def test_preflight_makemkv_sdf_ok_when_updated(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"][0].makemkv_sdf_state = "updated"
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    checks = {ch["name"]: ch for ch in r.json()["checks"]}
    assert checks["makemkv_sdf"]["status"] == "ok"


def test_preflight_makemkv_sdf_warning_when_download_failed(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"][0].makemkv_sdf_state = "download_failed"
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    checks = {ch["name"]: ch for ch in r.json()["checks"]}
    assert checks["makemkv_sdf"]["status"] == "warning"


def test_preflight_makemkv_sdf_ok_when_disabled(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"][0].makemkv_sdf_state = "disabled"
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    checks = {ch["name"]: ch for ch in r.json()["checks"]}
    assert checks["makemkv_sdf"]["status"] == "ok"
    assert "disabled" in checks["makemkv_sdf"]["detail"]


def test_preflight_makemkv_sdf_warning_when_not_yet_checked(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    # makemkv_sdf_state defaults to None on a fresh Config
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    checks = {ch["name"]: ch for ch in r.json()["checks"]}
    assert checks["makemkv_sdf"]["status"] == "warning"
    assert "not yet checked" in checks["makemkv_sdf"]["detail"]
