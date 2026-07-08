"""GET /api/system/diagnostics — heal-on-read + report."""

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
from arm_backend.routers import system as system_router  # noqa: E402
from arm_common import Config, Drive, DriveStatus, User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402

not_root = pytest.mark.skipif(os.geteuid() == 0, reason="chmod-based unwritable dirs don't bind as root")


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


def _make_app(signing_key: bytes, db: FakeSession, *, tmp) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
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
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    r = _get(app, token)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    names = {ch["name"] for ch in body["checks"]}
    assert {"config", "MEDIA_ROOT", "RAW_ROOT", "LOG_DIR", "drives"} <= names
    media = next(p for p in body["paths"] if p["name"] == "MEDIA_ROOT")
    assert media["exists"] is True and media["writable"] is True


def test_diagnostics_heals_missing_root_on_read(signing_key: bytes, tmp_path) -> None:
    """A missing-but-creatable root is silently created, then reports ok —
    the report never shows a problem the backend could fix itself."""
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp=tmp_path)
    missing = tmp_path / "not-yet" / "media"
    app.state.system_paths["MEDIA_ROOT"] = str(missing)
    r = _get(app, token)
    assert r.status_code == 200, r.text
    assert missing.is_dir()
    media = next(ch for ch in r.json()["checks"] if ch["name"] == "MEDIA_ROOT")
    assert media["status"] == "ok"
    assert r.json()["status"] == "ok"


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


def test_diagnostics_unauthenticated_401(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
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
    db = FakeSession()
    _seed(db)
    app, _ = _make_app(signing_key, db, tmp=tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/system/version").status_code == 401


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


def test_diagnostics_uses_settings_fallback(signing_key: bytes, tmp_path, monkeypatch) -> None:
    """When system_paths is absent from app.state, _roots falls back to
    settings-derived defaults."""
    monkeypatch.setattr(system_router.settings, "MEDIA_ROOT", str(tmp_path / "m"))
    monkeypatch.setattr(system_router.settings, "RAW_ROOT", str(tmp_path / "r"))
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
    names = {p["name"] for p in r.json()["paths"]}
    assert {"MEDIA_ROOT", "RAW_ROOT", "LOG_DIR"} <= names
    # the settings-pointed roots were healed into existence
    assert (tmp_path / "m").is_dir() and (tmp_path / "r").is_dir()


@not_root
def test_ensure_roots_swallows_oserror(tmp_path, caplog) -> None:
    """A broken mount must never crash the caller — warn and move on."""
    fence = tmp_path / "fence"
    fence.mkdir()
    fence.chmod(0o555)
    try:
        with caplog.at_level("WARNING"):
            system_router.ensure_roots({"BAD": str(fence / "sub"), "GOOD": str(tmp_path / "good")})
    finally:
        fence.chmod(0o755)
    assert (tmp_path / "good").is_dir()
    assert any("cannot create BAD" in rec.getMessage() for rec in caplog.records)
