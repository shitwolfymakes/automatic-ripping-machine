"""Regression tests for the job_id path-traversal guard.

`job_id` arrives as a URL path param and is interpolated into filesystem
paths (per-job logs under `/logs/jobs/<id>.log` and `/raw/<id>/`). Without
validation a crafted id like `../../etc/passwd` traverses out of those roots
— flagged by CodeQL as "uncontrolled data used in a path expression".

Two layers are asserted here:
  1. Route boundary — endpoints pin the param with `pattern=`, so a bad id is
     rejected with 422 before any handler code runs.
  2. Defence-in-depth — `per_job_log_path` / `_delete_job_files` re-validate
     and raise `ValueError`, so the sinks stay safe even if called directly.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import jobs as jobs_router  # noqa: E402
from arm_backend.routers import logs as logs_router  # noqa: E402
from arm_backend.routers.logs import per_job_log_path  # noqa: E402
from arm_common import User  # noqa: E402
from arm_common.ulid import is_safe_id_component, new_id  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402

# Bad ids for the unit-level guards (called directly, no HTTP normalisation).
_BAD_IDS = ["..", "../etc", "a/b", "a\\b", "job.x", "foo\x00bar", "a b", ""]

# Bad ids for the route tests. A bare `..` (or `.`) is a dot-segment the HTTP
# client collapses before sending, so it can never reach the server as-is —
# these payloads instead carry a disallowed char (`.`, space) while still
# routing to `{job_id}`, so the param `pattern=` rejects them with 422.
_BAD_ROUTE_IDS = ["job_x.evil", "..foo", "a b"]


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


# --- unit: the shared allowlist ----------------------------------------------


def test_is_safe_id_component_accepts_real_and_test_ids() -> None:
    assert is_safe_id_component(new_id("job"))  # job_<26-char ULID>
    for ok in ("job_x", "job_a", "job_42", "drv_x", "usr_admin", "a-b_c"):
        assert is_safe_id_component(ok), ok


def test_is_safe_id_component_rejects_traversal_and_separators() -> None:
    for bad in _BAD_IDS:
        assert not is_safe_id_component(bad), repr(bad)


# --- unit: the filesystem sinks reject bad ids -------------------------------


def test_per_job_log_path_rejects_bad_id() -> None:
    with pytest.raises(ValueError):
        per_job_log_path("../../etc/passwd")


def test_per_job_log_path_builds_path_for_good_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logs_router, "LOG_DIR", tmp_path)
    assert per_job_log_path("job_x") == tmp_path / "jobs" / "job_x.log"


def test_delete_job_files_rejects_bad_id_without_touching_fs(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    sentinel = tmp_path / "secret"  # lives OUTSIDE raw_root
    sentinel.write_text("keep me")
    with pytest.raises(ValueError):
        jobs_router._delete_job_files("../secret", [], raw_root=raw_root, media_root=tmp_path / "media")
    assert sentinel.exists()  # guard fired before any rmtree


# --- route boundary: 422 before the handler ----------------------------------


def _logs_app(signing_key: bytes) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(logs_router.router)
    db = FakeSession()
    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _jobs_app(signing_key: bytes) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(jobs_router.router)
    db = FakeSession()
    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("bad", _BAD_ROUTE_IDS)
def test_stream_logs_rejects_bad_id(bad: str, signing_key: bytes) -> None:
    app, token = _logs_app(signing_key)
    with TestClient(app) as client:
        r = client.get(f"/api/logs/{bad}", headers=_auth(token))
    assert r.status_code == 422


@pytest.mark.parametrize("bad", _BAD_ROUTE_IDS)
def test_zip_logs_rejects_bad_id(bad: str, signing_key: bytes) -> None:
    app, token = _logs_app(signing_key)
    with TestClient(app) as client:
        r = client.get(f"/api/logs/{bad}.zip", headers=_auth(token))
    assert r.status_code == 422


@pytest.mark.parametrize("bad", _BAD_ROUTE_IDS)
def test_delete_job_rejects_bad_id(bad: str, signing_key: bytes) -> None:
    app, token = _jobs_app(signing_key)
    with TestClient(app) as client:
        r = client.delete(f"/api/jobs/{bad}", headers=_auth(token))
    assert r.status_code == 422
