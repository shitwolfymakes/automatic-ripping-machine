"""Phase 12 — `/api/logs/{job_id}` (NDJSON) and `/api/logs/{job_id}.zip`.

Both endpoints read only `LOG_DIR/jobs/<job_id>.log`. Tests monkeypatch
`arm_backend.log_reader.LOG_DIR` to a `tmp_path` seeded with hand-rolled
JSONL.
"""

from __future__ import annotations

import io
import json
import os
import secrets
import zipfile
from pathlib import Path


import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from arm_backend.db import get_session
from arm_backend.jwt_utils import issue_access_token
from arm_backend import log_reader
from arm_backend.routers import logs as logs_router
from arm_common import User
from arm_common.models.user import GUEST_ROLE

from tests._fakes import FakeSession


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(log_dir: Path, *, service: str, lines: list[dict[str, object]]) -> None:
    path = log_dir / f"{service}.log"
    with path.open("w", encoding="utf-8") as fh:
        for record in lines:
            fh.write(json.dumps(record) + "\n")


def _line(
    *, job_id: str | None = "job_01JZXR7K3M5Q8N4VWA00000001", msg: str = "x", service: str = "arm-backend"
) -> dict[str, object]:
    return {
        "ts": "2026-04-30T00:00:00+00:00",
        "level": "info",
        "service": service,
        "logger": f"{service}.test",
        "job_id": job_id,
        "track_id": None,
        "session_application_id": None,
        "event": None,
        "msg": msg,
        "fields": {},
        "exc": None,
    }


def _make_app(signing_key: bytes) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(logs_router.router)
    db = FakeSession()
    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )
    db.rows["users"].append(
        User(
            id="usr_guest",
            username="guest",
            password_hash="x",
            password_must_change=False,
            role=GUEST_ROLE,
            disabled=False,
        )
    )

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_stream_limit_is_capped_at_the_hard_cap(
    tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    monkeypatch.setattr(log_reader.settings, "ARM_LOG_PER_FILE_HARD_CAP", 3)  # cheap cap for the test
    _seed_per_job(tmp_path, job_id="job_01JZXR7K3M5Q8N4VWA00000001", lines=[_line(msg=f"m{i}") for i in range(10)])
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_01JZXR7K3M5Q8N4VWA00000001?limit=99999", headers=_auth(token))
    body_lines = [json.loads(line) for line in r.text.strip().splitlines()]
    assert len(body_lines) == 3


def test_stream_without_a_token_reads_as_guest(
    tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No Authorization header falls back to the guest account (read-only route)."""
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    app, _token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_01JZXR7K3M5Q8N4VWA00000001")
    assert r.status_code == 200


def test_zip_per_entry_line_cap(tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    monkeypatch.setattr(log_reader.settings, "ARM_LOG_ZIP_PER_ENTRY_LINE_CAP", 3)
    _seed_per_job(tmp_path, job_id="job_01JZXR7K3M5Q8N4VWA00000001", lines=[_line(msg=f"m{i}") for i in range(10)])
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_01JZXR7K3M5Q8N4VWA00000001.zip", headers=_auth(token))
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        body = zf.read("job_01JZXR7K3M5Q8N4VWA00000001.log").decode("utf-8").strip().splitlines()
    assert len(body) == 3


def test_zip_without_a_token_reads_as_guest(
    tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No Authorization header falls back to the guest account (read-only route)."""
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    app, _token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_01JZXR7K3M5Q8N4VWA00000001.zip")
    assert r.status_code == 200


def _seed_per_job(log_dir: Path, *, job_id: str, lines: list[dict[str, object]]) -> Path:
    """Write `lines` to `<log_dir>/jobs/<job_id>.log` — the file the
    LogTailer writes at runtime."""
    jobs_dir = log_dir / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    target = jobs_dir / f"{job_id}.log"
    with target.open("w", encoding="utf-8") as fh:
        for record in lines:
            fh.write(json.dumps(record) + "\n")
    return target


def test_zip_uses_per_job_file_when_present(
    tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When `/logs/jobs/<job_id>.log` exists, the zip is served from it
    directly (single entry) rather than scanning service logs. The
    service-level files are ignored even if they have matching lines."""
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    # Seed a stale service log with a different message — it should NOT
    # appear in the response because the per-job file is the source.
    _seed(tmp_path, service="arm-backend", lines=[_line(msg="stale-service-line")])
    _seed_per_job(tmp_path, job_id="job_01JZXR7K3M5Q8N4VWA00000001", lines=[_line(msg="per-job-line")])

    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_01JZXR7K3M5Q8N4VWA00000001.zip", headers=_auth(token))
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
        assert names == ["job_01JZXR7K3M5Q8N4VWA00000001.log"]
        body = zf.read("job_01JZXR7K3M5Q8N4VWA00000001.log").decode("utf-8")
    msgs = [json.loads(line)["msg"] for line in body.strip().splitlines()]
    assert msgs == ["per-job-line"]


def test_stream_reads_the_per_job_file_not_the_service_log(
    tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    _seed(tmp_path, service="arm-backend", lines=[_line(msg="stale-service-line")])
    _seed_per_job(tmp_path, job_id="job_01JZXR7K3M5Q8N4VWA00000001", lines=[_line(msg="per-job-line")])

    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_01JZXR7K3M5Q8N4VWA00000001", headers=_auth(token))
    assert r.status_code == 200
    msgs = [json.loads(line)["msg"] for line in r.text.strip().splitlines()]
    assert msgs == ["per-job-line"]


# --- residual file-IO branch coverage ----------------------------------------


def test_job_without_a_per_job_file_streams_nothing(
    tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    _seed(tmp_path, service="arm-backend", lines=[_line(msg="only-in-service-log")])
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_01JZXR7K3M5Q8N4VWA00000001", headers=_auth(token))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    assert r.content == b""


def test_job_without_a_per_job_file_zips_no_entries(
    tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    _seed(tmp_path, service="arm-backend", lines=[_line(msg="only-in-service-log")])
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_01JZXR7K3M5Q8N4VWA00000001.zip", headers=_auth(token))
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert zf.namelist() == []


def test_zip_per_job_present_but_empty(tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    """per-job file exists but has no lines → _read_capped_lines returns [],
    so no zip entry is written."""
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    (tmp_path / "jobs").mkdir()
    (tmp_path / "jobs" / "job_01JZXR7K3M5Q8N4VWA00000001.log").write_text("")
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_01JZXR7K3M5Q8N4VWA00000001.zip", headers=_auth(token))
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert zf.namelist() == []


class _UnopenableFile:
    name = "job_01JZXR7K3M5Q8N4VWA00000001.log"

    def is_file(self) -> bool:
        return True

    def open(self, *_a: object, **_k: object) -> object:
        raise OSError("permission denied")


def test_stream_per_job_open_oserror(tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    monkeypatch.setattr(log_reader, "per_job_log_path", lambda _jid: _UnopenableFile())
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_01JZXR7K3M5Q8N4VWA00000001", headers=_auth(token))
    assert r.status_code == 200
    assert r.content == b""  # the generator returned before yielding


def test_stream_per_job_respects_cap(tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    (tmp_path / "jobs").mkdir()
    with (tmp_path / "jobs" / "job_01JZXR7K3M5Q8N4VWA00000001.log").open("w", encoding="utf-8") as fh:
        for i in range(5):
            fh.write(json.dumps(_line(msg=f"l{i}")) + "\n")
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_01JZXR7K3M5Q8N4VWA00000001?limit=2", headers=_auth(token))
    assert r.status_code == 200
    assert len([ln for ln in r.text.splitlines() if ln]) == 2  # capped at the limit


def test_stream_limit_zero_returns_no_lines(
    tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """limit=0 means no lines, with and without a per-job file (D-166)."""
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    _seed(tmp_path, service="svc-a", lines=[_line(msg="a0")])
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_01JZXR7K3M5Q8N4VWA00000001?limit=0", headers=_auth(token))
        assert r.status_code == 200
        assert r.content == b""
        (tmp_path / "jobs").mkdir()
        (tmp_path / "jobs" / "job_01JZXR7K3M5Q8N4VWA00000001.log").write_text(
            json.dumps(_line(msg="l0")) + "\n", encoding="utf-8"
        )
        r = client.get("/api/logs/job_01JZXR7K3M5Q8N4VWA00000001?limit=0", headers=_auth(token))
        assert r.status_code == 200
        assert r.content == b""


# --- GET /api/logs (index of per-job log files) ---------------------------

_JOB_A = "job_01JZXR7K3M5Q8N4VWA00000001"
_JOB_B = "job_01JZXR7K3M5Q8N4VWA00000002"


def _job_file(log_dir: Path, name: str, body: str, mtime: float) -> Path:
    jobs = log_dir / "jobs"
    jobs.mkdir(exist_ok=True)
    path = jobs / name
    path.write_text(body, encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def test_index_lists_size_and_mtime_newest_first(
    tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    _job_file(tmp_path, f"{_JOB_A}.log", "abc\n", 1_700_000_000)
    _job_file(tmp_path, f"{_JOB_B}.log", "abcdef\n", 1_700_000_100)
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert [row["job_id"] for row in body] == [_JOB_B, _JOB_A]
    assert [row["size_bytes"] for row in body] == [7, 4]
    assert body[0]["modified_at"] == "2023-11-14T22:15:00Z"


def test_index_skips_invalid_names_and_non_log_files(
    tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    _job_file(tmp_path, f"{_JOB_A}.log", "x", 1_700_000_000)
    _job_file(tmp_path, "notes.log", "x", 1_700_000_000)
    _job_file(tmp_path, "..x.log", "x", 1_700_000_000)
    _job_file(tmp_path, f"{_JOB_B}.txt", "x", 1_700_000_000)
    (tmp_path / "jobs" / f"{_JOB_B}.log").mkdir()  # a directory is not a log file
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs", headers=_auth(token))
    assert [row["job_id"] for row in r.json()] == [_JOB_A]


def test_index_skips_a_file_that_cannot_be_checked(
    tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A listed file whose `is_file` check raises `OSError` is skipped, not a 500."""
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    _job_file(tmp_path, f"{_JOB_A}.log", "x", 1_700_000_000)
    broken = _job_file(tmp_path, f"{_JOB_B}.log", "x", 1_700_000_100)
    real_is_file = Path.is_file

    def flaky_is_file(self: Path, *, follow_symlinks: bool = True) -> bool:
        if self == broken:
            raise PermissionError("denied")
        return real_is_file(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "is_file", flaky_is_file)
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs", headers=_auth(token))
    assert r.status_code == 200
    assert [row["job_id"] for row in r.json()] == [_JOB_A]


def test_index_missing_directory_is_empty(tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path / "nope")
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs", headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == []


def test_index_rejects_bad_token(tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    app, _ = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs", headers=_auth("not-a-jwt"))
    assert r.status_code == 401


def test_index_does_not_shadow_job_routes(tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    _job_file(tmp_path, f"{_JOB_A}.log", '{"job_id": "x", "msg": "hi"}\n', 1_700_000_000)
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        one = client.get(f"/api/logs/{_JOB_A}", headers=_auth(token))
        zipped = client.get(f"/api/logs/{_JOB_A}.zip", headers=_auth(token))
    assert one.status_code == 200
    assert one.headers["content-type"].startswith("application/x-ndjson")
    assert zipped.status_code == 200
    assert zipped.headers["content-type"] == "application/zip"
