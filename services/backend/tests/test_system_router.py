"""GET /api/system/diagnostics — heal-on-read + report."""

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
from arm_common.models.user import GUEST_ROLE  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402

not_root = pytest.mark.skipif(os.geteuid() == 0, reason="chmod-based unwritable dirs don't bind as root")


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession) -> None:
    db.rows["users"] = [
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False),
        User(
            id="usr_guest",
            username="guest",
            password_hash="x",
            password_must_change=False,
            role=GUEST_ROLE,
            disabled=False,
        ),
    ]
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


def _make_app(signing_key: bytes, db: FakeSession, *, tmp) -> tuple[FastAPI, str]:
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
    app.state.system_paths = {
        "MEDIA_ROOT": str(media),
        "RAW_ROOT": str(raw),
        "LOG_DIR": str(logs),
    }
    app.include_router(system_router.router)

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _get(app: FastAPI, token: str):
    with TestClient(app) as c:
        return c.get("/api/system/diagnostics", headers=_auth(token))


def test_diagnostics_ok(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    # An unvalidated MakeMKV key degrades overall status to "warning" by
    # design — seed it validated so the baseline really is all-healthy.
    db.rows["config"][0].makemkv_key = "M-x"
    db.rows["config"][0].makemkv_key_valid = True
    db.rows["config"][0].makemkv_key_state = "valid"
    db.rows["config"][0].community_keydb_state = "ok"
    db.rows["config"][0].makemkv_sdf_state = "updated"
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    # An absent transcode dispatcher also degrades to "warning" — stub a live one.
    app.state.transcode_dispatcher = _StubDispatcher(host_paths=True)
    # Likewise an absent ripper manager — stub a live one.
    app.state.ripper_manager = _StubRipperManager()
    r = _get(app, token)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    names = {ch["name"] for ch in body["checks"]}
    assert {"config", "MEDIA_ROOT", "RAW_ROOT", "LOG_DIR", "drives"} <= names
    media = next(p for p in body["paths"] if p["name"] == "MEDIA_ROOT")
    assert media["exists"] is True and media["writable"] is True


@not_root
def test_diagnostics_uncreatable_required_root_is_error(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    fence = tmp_path / "fence"
    fence.mkdir()
    fence.chmod(0o555)
    app.state.system_paths["MEDIA_ROOT"] = str(fence / "sub")
    try:
        r = _get(app, token)
    finally:
        fence.chmod(0o755)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "error"
    media = next(ch for ch in r.json()["checks"] if ch["name"] == "MEDIA_ROOT")
    assert media["status"] == "error"
    assert "exists=False" in media["detail"]


@not_root
def test_diagnostics_uncreatable_optional_root_is_warning(signing_key: bytes, tmp_path) -> None:
    """Roots outside _REQUIRED_ROOTS degrade to a warning, not an error."""
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    fence = tmp_path / "fence"
    fence.mkdir()
    fence.chmod(0o555)
    app.state.system_paths = {**app.state.system_paths, "EXTRA_ROOT": str(fence / "extra")}
    try:
        r = _get(app, token)
    finally:
        fence.chmod(0o755)
    assert r.status_code == 200, r.text
    extra = next(ch for ch in r.json()["checks"] if ch["name"] == "EXTRA_ROOT")
    assert extra["status"] == "warning"
    assert r.json()["status"] == "warning"


def test_diagnostics_no_drives_is_warning(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["drives"] = []
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    r = _get(app, token)
    assert r.status_code == 200, r.text
    drives = next(ch for ch in r.json()["checks"] if ch["name"] == "drives")
    assert drives["status"] == "warning"


def test_diagnostics_config_missing_is_error(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"] = []
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    r = _get(app, token)
    assert r.status_code == 200, r.text
    cfg_check = next(ch for ch in r.json()["checks"] if ch["name"] == "config")
    assert cfg_check["status"] == "error"
    assert r.json()["status"] == "error"


def test_diagnostics_unauthenticated_reads_as_guest(signing_key: bytes, tmp_path) -> None:
    """No Authorization header falls back to the guest account (read-only route)."""
    db = FakeSession()
    _seed(db)
    app, _ = _make_app(signing_key, db, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics")
    assert r.status_code == 200


def test_diagnostics_unauthenticated_401_when_guest_disabled(signing_key: bytes, tmp_path) -> None:
    """With guest access disabled, an anonymous request is rejected."""
    db = FakeSession()
    _seed(db)
    db.rows["users"][1].disabled = True
    app, _ = _make_app(signing_key, db, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics")
    assert r.status_code == 401


def test_system_version(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    with TestClient(app) as client:
        r = client.get("/api/system/version", headers=_auth(token))
    assert r.status_code == 200
    assert isinstance(r.json()["version"], str) and r.json()["version"]


def test_app_version_env_override_wins(monkeypatch) -> None:
    from arm_backend.routers import system as system_router

    monkeypatch.setenv("ARM_VERSION", "9.9.9-test")
    system_router._app_version.cache_clear()
    try:
        assert system_router._app_version() == "9.9.9-test"
    finally:
        system_router._app_version.cache_clear()


def test_app_version_reads_version_file(monkeypatch, tmp_path) -> None:
    """The canonical VERSION file (baked into the image at /app/VERSION,
    repo root in dev) is the source of truth — not the static pyproject
    version, which is pinned 0.0.0."""
    from arm_backend.routers import system as system_router

    vfile = tmp_path / "VERSION"
    vfile.write_text("3.1.4-test\n")
    monkeypatch.delenv("ARM_VERSION", raising=False)
    monkeypatch.setattr(system_router, "_VERSION_FILE_CANDIDATES", (vfile,))
    system_router._app_version.cache_clear()
    try:
        assert system_router._app_version() == "3.1.4-test"
    finally:
        system_router._app_version.cache_clear()


def test_system_version_requires_auth(signing_key: bytes, tmp_path) -> None:
    """No Authorization header falls back to the guest account (read-only route)."""
    db = FakeSession()
    _seed(db)
    app, _ = _make_app(signing_key, db, tmp=tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/system/version").status_code == 200


def test_app_version_real_fallback(monkeypatch) -> None:
    import importlib.metadata

    from arm_backend.routers import system as system_router

    def _raise(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError("arm_backend")

    monkeypatch.delenv("ARM_VERSION", raising=False)
    monkeypatch.setattr(system_router, "_VERSION_FILE_CANDIDATES", ())
    monkeypatch.setattr(importlib.metadata, "version", _raise)
    system_router._app_version.cache_clear()
    try:
        assert system_router._app_version() == "0.0.0+unknown"
    finally:
        system_router._app_version.cache_clear()


def test_diagnostics_includes_makemkv_key_check_ok(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"][0].makemkv_key = "M-x"
    db.rows["config"][0].makemkv_key_valid = True
    db.rows["config"][0].makemkv_key_state = "valid"
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    checks = {ch["name"]: ch for ch in r.json()["checks"]}
    assert checks["makemkv_key"]["status"] == "ok"


def test_diagnostics_makemkv_key_warning_when_unknown(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"][0].makemkv_key = "M-x"
    # makemkv_key_valid defaults to None → never checked
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    checks = {ch["name"]: ch for ch in r.json()["checks"]}
    assert checks["makemkv_key"]["status"] == "warning"


def test_diagnostics_makemkv_key_error_when_invalid(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"][0].makemkv_key = "M-x"
    db.rows["config"][0].makemkv_key_valid = False
    db.rows["config"][0].makemkv_key_state = "binary_expired"
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    checks = {ch["name"]: ch for ch in r.json()["checks"]}
    assert checks["makemkv_key"]["status"] == "error"


def test_diagnostics_uses_settings_fallback(signing_key: bytes, tmp_path, monkeypatch) -> None:
    """When system_paths is absent from app.state, _roots falls back to
    settings-derived defaults."""
    from arm_backend.config import settings

    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path / "m"))
    monkeypatch.setattr(settings, "RAW_ROOT", str(tmp_path / "r"))
    db = FakeSession()
    _seed(db)
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(system_router.router)

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override
    token, _ = issue_access_token("usr_admin", "admin", signing_key)

    r = _get(app, token)
    assert r.status_code == 200, r.text
    paths = {p["name"]: p for p in r.json()["paths"]}
    assert {"MEDIA_ROOT", "RAW_ROOT", "LOG_DIR"} <= set(paths)
    # read-only diagnostics: settings-pointed roots are reported, not created
    assert paths["MEDIA_ROOT"]["exists"] is False
    assert not (tmp_path / "m").exists() and not (tmp_path / "r").exists()


class _StubDispatcher:
    """Minimal stand-in for TranscodeDispatcher exposing only the gate the
    diagnostics check reads. A real dispatcher needs a docker client + settings,
    which the Tier-1 fake-session suite has no business constructing."""

    def __init__(self, *, host_paths: bool, probe=(True, None), last_spawn_error: str | None = None) -> None:
        self._host_paths = host_paths
        self._probe = probe
        self.last_spawn_error = last_spawn_error

    def host_paths_set(self) -> bool:
        return self._host_paths

    def probe(self) -> tuple[bool, str | None]:
        return self._probe


class _StubRipperManager:
    def __init__(self, *, host_paths: bool = True, probe=(True, None)) -> None:
        self._host_paths = host_paths
        self._probe = probe

    def host_paths_set(self) -> bool:
        return self._host_paths

    def probe(self) -> tuple[bool, str | None]:
        return self._probe


def _ripper_check(body: dict) -> dict:
    return next(ch for ch in body["checks"] if ch["name"] == "ripper_manager")


def test_diagnostics_ripper_manager_warning_when_absent(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    check = _ripper_check(r.json())
    assert check["status"] == "warning" and "docker" in check["detail"]


def test_diagnostics_ripper_manager_warning_when_host_paths_unset(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    app.state.ripper_manager = _StubRipperManager(host_paths=False)
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    check = _ripper_check(r.json())
    assert check["status"] == "warning" and "ARM_HOST" in check["detail"]


def test_diagnostics_ripper_manager_warning_when_probe_fails(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    app.state.ripper_manager = _StubRipperManager(probe=(False, "image arm-ripper:latest not present on docker host"))
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    check = _ripper_check(r.json())
    assert check["status"] == "warning" and "not present" in check["detail"]


def test_diagnostics_ripper_manager_ok(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    app.state.ripper_manager = _StubRipperManager()
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    check = _ripper_check(r.json())
    assert check["status"] == "ok" and check["detail"] is None


def test_diagnostics_transcoder_warning_when_no_dispatcher(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    # _make_app does not set app.state.transcode_dispatcher -> getattr falls to None
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    assert r.status_code == 200, r.text
    check = next(ch for ch in r.json()["checks"] if ch["name"] == "transcoder")
    assert check["status"] == "warning"
    assert "docker" in check["detail"]


def test_diagnostics_transcoder_warning_when_host_paths_unset(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    app.state.transcode_dispatcher = _StubDispatcher(host_paths=False)
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    assert r.status_code == 200, r.text
    check = next(ch for ch in r.json()["checks"] if ch["name"] == "transcoder")
    assert check["status"] == "warning"
    assert "ARM_HOST" in check["detail"]


def test_diagnostics_transcoder_ok_when_live(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    app.state.transcode_dispatcher = _StubDispatcher(host_paths=True)
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    assert r.status_code == 200, r.text
    check = next(ch for ch in r.json()["checks"] if ch["name"] == "transcoder")
    assert check["status"] == "ok"
    assert check["detail"] is None


def test_diagnostics_transcoder_warning_when_probe_fails(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    app.state.transcode_dispatcher = _StubDispatcher(
        host_paths=True, probe=(False, "image x not present on docker host")
    )
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    assert r.status_code == 200, r.text
    check = next(ch for ch in r.json()["checks"] if ch["name"] == "transcoder")
    assert check["status"] == "warning" and "not present" in check["detail"]


def test_diagnostics_transcoder_warning_when_last_spawn_failed(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    app.state.transcode_dispatcher = _StubDispatcher(host_paths=True, last_spawn_error="409 name in use")
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    assert r.status_code == 200, r.text
    check = next(ch for ch in r.json()["checks"] if ch["name"] == "transcoder")
    assert check["status"] == "warning" and "409" in check["detail"]


def test_diagnostics_transcoder_ok_when_probe_and_spawns_clean(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    app.state.transcode_dispatcher = _StubDispatcher(host_paths=True)
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    assert r.status_code == 200, r.text
    check = next(ch for ch in r.json()["checks"] if ch["name"] == "transcoder")
    assert check["status"] == "ok"


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
def test_diagnostics_community_keydb_check(signing_key: bytes, tmp_path, state, expected_status) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"][0].community_keydb_state = state
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    assert r.status_code == 200, r.text
    check = next(ch for ch in r.json()["checks"] if ch["name"] == "community_keydb")
    assert check["status"] == expected_status


def test_diagnostics_community_keydb_ok_reports_vuk_count(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"][0].community_keydb_state = "ok"
    db.rows["config"][0].community_keydb_vuk_count = 4200
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    assert r.status_code == 200, r.text
    check = next(ch for ch in r.json()["checks"] if ch["name"] == "community_keydb")
    assert check["detail"] == "4200 VUK keys installed"


def test_diagnostics_overall_not_error_when_only_transcoder_warns(signing_key: bytes, tmp_path) -> None:
    # Roots are fine; dispatcher absent -> transcoder warns. Overall must be
    # "warning" (degraded), never promoted to "error".
    db = FakeSession()
    _seed(db)
    db.rows["config"][0].makemkv_key = "M-x"
    db.rows["config"][0].makemkv_key_valid = True
    db.rows["config"][0].makemkv_key_state = "valid"
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    body = r.json()
    transcoder = next(ch for ch in body["checks"] if ch["name"] == "transcoder")
    assert transcoder["status"] == "warning"
    assert body["status"] == "warning"


def test_diagnostics_makemkv_sdf_ok_when_updated(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"][0].makemkv_sdf_state = "updated"
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    checks = {ch["name"]: ch for ch in r.json()["checks"]}
    assert checks["makemkv_sdf"]["status"] == "ok"


def test_diagnostics_makemkv_sdf_warning_when_download_failed(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"][0].makemkv_sdf_state = "download_failed"
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    checks = {ch["name"]: ch for ch in r.json()["checks"]}
    assert checks["makemkv_sdf"]["status"] == "warning"


def test_diagnostics_makemkv_sdf_ok_when_disabled(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"][0].makemkv_sdf_state = "disabled"
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    checks = {ch["name"]: ch for ch in r.json()["checks"]}
    assert checks["makemkv_sdf"]["status"] == "ok"
    assert "disabled" in checks["makemkv_sdf"]["detail"]


def test_diagnostics_makemkv_sdf_warning_when_not_yet_checked(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    # makemkv_sdf_state defaults to None on a fresh Config
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/diagnostics", headers=_auth(token))
    checks = {ch["name"]: ch for ch in r.json()["checks"]}
    assert checks["makemkv_sdf"]["status"] == "warning"
    assert "not yet checked" in checks["makemkv_sdf"]["detail"]


def test_stats_counts(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/stats", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["uptime_seconds"] >= 40
    assert body["drives_online"] == 1
    assert body["events_unsent"] == 1
    assert body["jobs_by_status"].get("ripping") == 1


def test_stats_no_started_at(signing_key: bytes, tmp_path) -> None:
    """When started_at is not set on app.state, uptime_seconds should be 0."""
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    del app.state.started_at
    with TestClient(app) as c:
        r = c.get("/api/system/stats", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["uptime_seconds"] == 0
