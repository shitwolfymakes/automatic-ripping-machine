"""Phase 12 — `/api/logs/{job_id}` (NDJSON) and `/api/logs/{job_id}.zip`.

Both endpoints grep `LOG_DIR/*.log` line-by-line for `record["job_id"]`.
Tests monkeypatch `arm_backend.routers.logs.LOG_DIR` to a `tmp_path`
seeded with hand-rolled JSONL across multiple service files.
"""

from __future__ import annotations

import io
import json
import os
import secrets
import zipfile
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import logs as logs_router  # noqa: E402
from arm_common import User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(log_dir: Path, *, service: str, lines: list[dict[str, object]]) -> None:
    path = log_dir / f"{service}.log"
    with path.open("w", encoding="utf-8") as fh:
        for record in lines:
            fh.write(json.dumps(record) + "\n")


def _line(*, job_id: str | None = "job_x", msg: str = "x", service: str = "arm-backend") -> dict[str, object]:
    return {
        "ts": "2026-04-30T00:00:00+00:00",
        "level": "info",
        "service": service,
        "job_id": job_id,
        "track_id": None,
        "session_application_id": None,
        "msg": msg,
        "extra": {"logger": f"{service}.test"},
    }


def _make_app(signing_key: bytes) -> tuple[FastAPI, str]:
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


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_grep_returns_only_matching_lines(tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logs_router, "LOG_DIR", tmp_path)
    _seed(
        tmp_path,
        service="arm-backend",
        lines=[
            _line(msg="hit-1"),
            _line(job_id="other_job", msg="miss"),
            _line(msg="hit-2"),
        ],
    )
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_x", headers=_auth(token))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    body_lines = [json.loads(line) for line in r.text.strip().splitlines()]
    assert [row["msg"] for row in body_lines] == ["hit-1", "hit-2"]


def test_grep_files_alphabetical_no_resort(tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logs_router, "LOG_DIR", tmp_path)
    _seed(tmp_path, service="zzz-svc", lines=[_line(msg="z1"), _line(msg="z2")])
    _seed(tmp_path, service="arm-backend", lines=[_line(msg="b1")])
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_x", headers=_auth(token))
    body_lines = [json.loads(line) for line in r.text.strip().splitlines()]
    msgs = [row["msg"] for row in body_lines]
    # arm-backend.log sorts before zzz-svc.log alphabetically.
    assert msgs == ["b1", "z1", "z2"]


def test_grep_per_file_limit_clamps_each_file(
    tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(logs_router, "LOG_DIR", tmp_path)
    _seed(tmp_path, service="svc-a", lines=[_line(msg=f"a{i}") for i in range(5)])
    _seed(tmp_path, service="svc-b", lines=[_line(msg=f"b{i}") for i in range(5)])
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_x?limit=2", headers=_auth(token))
    body_lines = [json.loads(line) for line in r.text.strip().splitlines()]
    msgs = [row["msg"] for row in body_lines]
    # 2 from svc-a + 2 from svc-b = 4 total (per-file cap, not global).
    assert msgs == ["a0", "a1", "b0", "b1"]


def test_grep_hard_cap_pins_at_10000(tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logs_router, "LOG_DIR", tmp_path)
    monkeypatch.setattr(logs_router, "PER_FILE_HARD_CAP", 3)  # cheap cap for the test
    _seed(tmp_path, service="svc", lines=[_line(msg=f"m{i}") for i in range(10)])
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_x?limit=99999", headers=_auth(token))
    body_lines = [json.loads(line) for line in r.text.strip().splitlines()]
    assert len(body_lines) == 3


def test_grep_skips_unparseable_lines(tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logs_router, "LOG_DIR", tmp_path)
    path = tmp_path / "svc.log"
    with path.open("w", encoding="utf-8") as fh:
        fh.write("not json\n")
        fh.write(json.dumps(_line(msg="ok")) + "\n")
        fh.write("\n")  # blank line
        fh.write("{ broken json\n")
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_x", headers=_auth(token))
    assert r.status_code == 200
    body_lines = [json.loads(line) for line in r.text.strip().splitlines()]
    assert [row["msg"] for row in body_lines] == ["ok"]


def test_grep_requires_jwt(tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logs_router, "LOG_DIR", tmp_path)
    app, _token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_x")
    assert r.status_code in (401, 403)


def test_zip_contains_one_entry_per_service_with_matching_lines(
    tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(logs_router, "LOG_DIR", tmp_path)
    _seed(
        tmp_path,
        service="arm-backend",
        lines=[_line(msg="b1"), _line(job_id="other", msg="b-miss")],
    )
    _seed(tmp_path, service="arm-ripper-sr0", lines=[_line(msg="r1")])
    # No matches in this file → must be omitted from the zip.
    _seed(tmp_path, service="arm-empty", lines=[_line(job_id="other", msg="x")])

    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_x.zip", headers=_auth(token))

    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert 'filename="arm-logs-job_x.zip"' in r.headers["content-disposition"]
    assert int(r.headers["content-length"]) == len(r.content)

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = sorted(zf.namelist())
        assert names == ["arm-backend.log", "arm-ripper-sr0.log"]
        backend_body = zf.read("arm-backend.log").decode("utf-8")
    backend_lines = [json.loads(line) for line in backend_body.strip().splitlines()]
    assert [row["msg"] for row in backend_lines] == ["b1"]


def test_zip_per_entry_line_cap(tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logs_router, "LOG_DIR", tmp_path)
    monkeypatch.setattr(logs_router, "ZIP_PER_ENTRY_LINE_CAP", 3)
    _seed(tmp_path, service="svc", lines=[_line(msg=f"m{i}") for i in range(10)])
    app, token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_x.zip", headers=_auth(token))
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        body = zf.read("svc.log").decode("utf-8").strip().splitlines()
    assert len(body) == 3


def test_zip_requires_jwt(tmp_path: Path, signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logs_router, "LOG_DIR", tmp_path)
    app, _token = _make_app(signing_key)
    with TestClient(app) as client:
        r = client.get("/api/logs/job_x.zip")
    assert r.status_code in (401, 403)
