from __future__ import annotations

import os
import secrets
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend import file_browser as fb  # noqa: E402
from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import files as files_router  # noqa: E402
from arm_common import User  # noqa: E402
from arm_common.schemas import FileRoot  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    media, log = tmp_path / "media", tmp_path / "log"
    media.mkdir()
    log.mkdir()
    (media / "movies").mkdir()
    (media / "a.mkv").write_bytes(b"x" * 3)
    registry = {
        "MEDIA": FileRoot(key="MEDIA", label="Media", path=str(media), writable=True),
        "LOG": FileRoot(key="LOG", label="Logs", path=str(log), writable=False),
    }
    monkeypatch.setattr(fb, "ROOTS", registry)
    db = FakeSession()
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    application = FastAPI()
    application.state.signing_key = secrets.token_bytes(32)
    application.include_router(files_router.router)

    async def _override_session() -> FakeSession:
        return db

    application.dependency_overrides[get_session] = _override_session
    return application


def _auth(app) -> dict[str, str]:
    token, _ = issue_access_token("usr_admin", "admin", app.state.signing_key)
    return {"Authorization": f"Bearer {token}"}


def test_roots(app):
    with TestClient(app) as c:
        r = c.get("/api/files/roots", headers=_auth(app))
    assert r.status_code == 200
    assert {x["key"] for x in r.json()} == {"MEDIA", "LOG"}


def test_list(app):
    with TestClient(app) as c:
        r = c.get("/api/files/list", params={"root": "MEDIA", "subpath": ""}, headers=_auth(app))
    assert r.status_code == 200
    names = {e["name"] for e in r.json()["entries"]}
    assert names == {"movies", "a.mkv"}


def test_list_path_escape_400(app):
    with TestClient(app) as c:
        r = c.get("/api/files/list", params={"root": "MEDIA", "subpath": "../log"}, headers=_auth(app))
    assert r.status_code == 400
    assert r.json()["detail"] == "path_escape"


def test_mkdir(app):
    with TestClient(app) as c:
        r = c.post("/api/files/mkdir", json={"root": "MEDIA", "subpath": "", "name": "new"}, headers=_auth(app))
    assert r.status_code == 200
    assert r.json() == {"root": "MEDIA", "subpath": "new"}


def test_mkdir_readonly_403(app):
    with TestClient(app) as c:
        r = c.post("/api/files/mkdir", json={"root": "LOG", "subpath": "", "name": "x"}, headers=_auth(app))
    assert r.status_code == 403
    assert r.json()["detail"] == "read_only_root"


def test_delete(app):
    with TestClient(app) as c:
        r = c.request("DELETE", "/api/files", params={"root": "MEDIA", "subpath": "a.mkv"}, headers=_auth(app))
    assert r.status_code == 200
    assert r.json() == {"deleted": True}


def test_fix_permissions(app):
    with TestClient(app) as c:
        r = c.post("/api/files/fix-permissions", json={"root": "MEDIA", "subpath": "movies"}, headers=_auth(app))
    assert r.status_code == 200
    assert r.json()["fixed"] >= 1


def test_requires_jwt(app):
    with TestClient(app) as c:
        r = c.get("/api/files/roots")
    assert r.status_code == 401


def test_rename(app):
    with TestClient(app) as c:
        r = c.post(
            "/api/files/rename", json={"root": "MEDIA", "subpath": "a.mkv", "new_name": "b.mkv"}, headers=_auth(app)
        )
    assert r.status_code == 200
    assert r.json() == {"root": "MEDIA", "subpath": "b.mkv"}


def test_rename_readonly_403(app):
    with TestClient(app) as c:
        r = c.post(
            "/api/files/rename", json={"root": "LOG", "subpath": "x.txt", "new_name": "y.txt"}, headers=_auth(app)
        )
    assert r.status_code == 403
    assert r.json()["detail"] == "read_only_root"


def test_move(app):
    with TestClient(app) as c:
        r = c.post(
            "/api/files/move",
            json={"root": "MEDIA", "subpath": "a.mkv", "dest_root": "MEDIA", "dest_subpath": "movies"},
            headers=_auth(app),
        )
    assert r.status_code == 200
    assert r.json() == {"root": "MEDIA", "subpath": "movies/a.mkv"}


def test_move_dest_not_writable_403(app):
    with TestClient(app) as c:
        r = c.post(
            "/api/files/move",
            json={"root": "MEDIA", "subpath": "a.mkv", "dest_root": "LOG", "dest_subpath": ""},
            headers=_auth(app),
        )
    assert r.status_code == 403
    assert r.json()["detail"] == "dest_not_writable"


def test_move_into_self_400(app):
    with TestClient(app) as c:
        r = c.post(
            "/api/files/move",
            json={"root": "MEDIA", "subpath": "movies", "dest_root": "MEDIA", "dest_subpath": "movies"},
            headers=_auth(app),
        )
    assert r.status_code == 400
    assert r.json()["detail"] == "move_into_self"


def test_fix_permissions_on_file(app):
    with TestClient(app) as c:
        r = c.post("/api/files/fix-permissions", json={"root": "MEDIA", "subpath": "a.mkv"}, headers=_auth(app))
    assert r.status_code == 200
    assert r.json()["fixed"] == 1


def test_delete_not_found(app):
    with TestClient(app) as c:
        r = c.request("DELETE", "/api/files", params={"root": "MEDIA", "subpath": "missing.mkv"}, headers=_auth(app))
    assert r.status_code == 404
    assert r.json()["detail"] == "not_found"


def test_fix_permissions_readonly_403(app):
    with TestClient(app) as c:
        r = c.post("/api/files/fix-permissions", json={"root": "LOG", "subpath": ""}, headers=_auth(app))
    assert r.status_code == 403
    assert r.json()["detail"] == "read_only_root"


# ── I1b: unexpected OSError from fb ops maps to 500 "filesystem_error" ───────


def test_list_oserror_returns_500(app, monkeypatch):
    """An unexpected OSError from fb.list_dir must produce 500 / filesystem_error."""

    def _boom(root, subpath):
        raise OSError("disk gone")

    monkeypatch.setattr(fb, "list_dir", _boom)
    with TestClient(app) as c:
        r = c.get("/api/files/list", params={"root": "MEDIA", "subpath": ""}, headers=_auth(app))
    assert r.status_code == 500
    assert r.json()["detail"] == "filesystem_error"


def test_mkdir_oserror_returns_500(app, monkeypatch):
    def _boom(root, subpath, name):
        raise OSError("no space left")

    monkeypatch.setattr(fb, "make_dir", _boom)
    with TestClient(app) as c:
        r = c.post("/api/files/mkdir", json={"root": "MEDIA", "subpath": "", "name": "x"}, headers=_auth(app))
    assert r.status_code == 500
    assert r.json()["detail"] == "filesystem_error"


def test_rename_oserror_returns_500(app, monkeypatch):
    def _boom(root, subpath, new_name):
        raise OSError("read-only filesystem")

    monkeypatch.setattr(fb, "rename", _boom)
    with TestClient(app) as c:
        r = c.post(
            "/api/files/rename", json={"root": "MEDIA", "subpath": "a.mkv", "new_name": "b.mkv"}, headers=_auth(app)
        )
    assert r.status_code == 500
    assert r.json()["detail"] == "filesystem_error"


def test_move_oserror_returns_500(app, monkeypatch):
    def _boom(root, subpath, dest_root, dest_subpath):
        raise OSError("cross-device link")

    monkeypatch.setattr(fb, "move", _boom)
    with TestClient(app) as c:
        r = c.post(
            "/api/files/move",
            json={"root": "MEDIA", "subpath": "a.mkv", "dest_root": "MEDIA", "dest_subpath": "movies"},
            headers=_auth(app),
        )
    assert r.status_code == 500
    assert r.json()["detail"] == "filesystem_error"


def test_fix_permissions_oserror_returns_500(app, monkeypatch):
    def _boom(root, subpath):
        raise OSError("permission denied")

    monkeypatch.setattr(fb, "fix_permissions", _boom)
    with TestClient(app) as c:
        r = c.post("/api/files/fix-permissions", json={"root": "MEDIA", "subpath": "movies"}, headers=_auth(app))
    assert r.status_code == 500
    assert r.json()["detail"] == "filesystem_error"


def test_delete_oserror_returns_500(app, monkeypatch):
    def _boom(root, subpath):
        raise OSError("directory not empty")

    monkeypatch.setattr(fb, "delete", _boom)
    with TestClient(app) as c:
        r = c.request("DELETE", "/api/files", params={"root": "MEDIA", "subpath": "a.mkv"}, headers=_auth(app))
    assert r.status_code == 500
    assert r.json()["detail"] == "filesystem_error"
