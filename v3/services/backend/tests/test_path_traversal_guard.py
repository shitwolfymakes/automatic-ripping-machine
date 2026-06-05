"""Regression tests for the job_id path-traversal guard.

`job_id` arrives as a URL path param and is interpolated into filesystem
paths (per-job logs under `/logs/jobs/<id>.log` and `/raw/<id>/`). Without
validation a crafted id like `../../etc/passwd` traverses out of those roots
— flagged by CodeQL as "uncontrolled data used in a path expression".

Two layers are asserted here:
  1. Route boundary — endpoints pin `{job_id}` to the exact `job_<ULID>`
     shape, so a malformed id is rejected with 422 before any handler runs.
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
from arm_common.ulid import is_valid_id, new_id  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402

# A real, well-formed job id (job_ + 26 Crockford base32 chars).
VALID_JOB_ID = "job_01HZX9R7K3M5Q8N4VWQRSTVWXY"

# Malformed ids for the unit-level guards (called directly, no HTTP norm).
_BAD_IDS = [
    "",  # empty
    "job_x",  # ULID body too short
    "job_a",  # ditto
    "job_01HZX9R7K3M5Q8N4VWQRSTVWX",  # 25-char body (one short)
    "job_01hzx9r7k3m5q8n4vwqrstvwxy",  # lowercase — wrong alphabet
    "JOB_01HZX9R7K3M5Q8N4VWQRSTVWXY",  # wrong prefix case
    "evt_01HZX9R7K3M5Q8N4VWQRSTVWXY",  # wrong prefix
    "..",  # traversal
    "../etc",
    "a/b",
    "a\\b",
    "job_/../passwd",
    "foo\x00bar",  # NUL
]

# Malformed ids for the route tests. A bare `..` is a dot-segment the HTTP
# client collapses before sending, so it can never reach the server as-is;
# these payloads still route to `{job_id}` but fail the strict pattern → 422.
# `job_x` is the important case: a plausible-looking id of the wrong shape.
_BAD_ROUTE_IDS = ["job_x", "job_x.evil", "..foo", "a b"]


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


# --- unit: the shared validator ----------------------------------------------


def test_is_valid_id_accepts_well_formed_job_ids() -> None:
    assert is_valid_id("job", new_id("job"))
    assert is_valid_id("job", VALID_JOB_ID)


def test_is_valid_id_rejects_malformed_ids() -> None:
    for bad in _BAD_IDS:
        assert not is_valid_id("job", bad), repr(bad)


# --- unit: the filesystem sinks reject bad ids -------------------------------


def test_per_job_log_path_rejects_bad_id() -> None:
    with pytest.raises(ValueError):
        per_job_log_path("../../etc/passwd")


def test_per_job_log_path_builds_path_for_good_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logs_router, "LOG_DIR", tmp_path)
    assert per_job_log_path(VALID_JOB_ID) == tmp_path / "jobs" / f"{VALID_JOB_ID}.log"


def test_delete_job_files_rejects_bad_id_without_touching_fs(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    sentinel = tmp_path / "secret"  # lives OUTSIDE raw_root
    sentinel.write_text("keep me")
    with pytest.raises(ValueError):
        jobs_router._delete_job_files("../secret", [], raw_root=raw_root, media_root=tmp_path / "media")
    assert sentinel.exists()  # guard fired before any rmtree


# --- route boundary: 422 before the handler ----------------------------------


def _app_with(router: object, signing_key: bytes) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(router.router)  # type: ignore[attr-defined]
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
    app, token = _app_with(logs_router, signing_key)
    with TestClient(app) as client:
        r = client.get(f"/api/logs/{bad}", headers=_auth(token))
    assert r.status_code == 422


@pytest.mark.parametrize("bad", _BAD_ROUTE_IDS)
def test_zip_logs_rejects_bad_id(bad: str, signing_key: bytes) -> None:
    app, token = _app_with(logs_router, signing_key)
    with TestClient(app) as client:
        r = client.get(f"/api/logs/{bad}.zip", headers=_auth(token))
    assert r.status_code == 422


@pytest.mark.parametrize("bad", _BAD_ROUTE_IDS)
def test_delete_job_rejects_bad_id(bad: str, signing_key: bytes) -> None:
    app, token = _app_with(jobs_router, signing_key)
    with TestClient(app) as client:
        r = client.delete(f"/api/jobs/{bad}", headers=_auth(token))
    assert r.status_code == 422


# --- a well-formed id passes the pattern and reaches the handler -------------


def test_valid_id_passes_pattern_to_handler(
    signing_key: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(logs_router, "LOG_DIR", tmp_path)  # empty → 200, no lines
    app, token = _app_with(logs_router, signing_key)
    with TestClient(app) as client:
        r = client.get(f"/api/logs/{VALID_JOB_ID}", headers=_auth(token))
    assert r.status_code == 200  # not 422 — the pattern let it through

    app, token = _app_with(jobs_router, signing_key)
    with TestClient(app) as client:
        r = client.delete(f"/api/jobs/{VALID_JOB_ID}", headers=_auth(token))
    assert r.status_code == 404  # passed validation, then unknown id
