"""Tests for DELETE /api/jobs/{id} and DELETE /api/jobs.

Covers the real failure modes:
  1. Single delete on a terminal job → 204, row gone, no filesystem touch when delete_raw=False.
  2. Single delete with delete_raw=True → raw rmtree + media unlink + empty-dir prune, all in-process.
  3. Single delete on a non-terminal job → 409, row preserved.
  4. Bulk delete partitions terminal vs non-terminal correctly.
  5. `_delete_job_files` helper: raw rmtree, per-file media unlink (sibling re-rips not clobbered),
     empty title-dir prune, idempotent over missing files.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import jobs as jobs_router  # noqa: E402
from arm_backend.routers import logs as logs_router  # noqa: E402
from arm_common import DiscType, Job, JobStatus, User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


class _CapturingHub:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(
        self,
        topic: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        persist: bool = True,
        job_id: str | None = None,
        track_id: str | None = None,
        session: Any = None,
    ) -> None:
        self.events.append({"topic": topic, "event_type": event_type, "payload": payload})


def _make_job(job_id: str, *, status: JobStatus, drive_id: str = "drv_x") -> Job:
    return Job(
        id=job_id,
        drive_id=drive_id,
        disc_type=DiscType.DVD,
        title="X",
        year=2000,
        status=status,
        metadata_json={},
    )


def _make_app(signing_key: bytes, db: FakeSession, hub: _CapturingHub) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.ws_hub = hub
    app.include_router(jobs_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_admin(db: FakeSession) -> None:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]


def test_delete_terminal_job_no_raw(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [_make_job("job_a", status=JobStatus.RIPPED)]
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.delete("/api/jobs/job_a", headers=_auth(token))
    assert r.status_code == 204
    assert db.rows["jobs"] == []
    # No WS emit unless delete_raw=true.
    assert hub.events == []


def test_delete_with_delete_raw_runs_filesystem_cleanup(
    signing_key: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """delete_raw=true unlinks every recorded transcode output and rmtrees
    raw/<job_id>/. Runs in-process — no WS, no ripper dependency. (The
    previous WS-hop made deletes silently no-op when the owning drive's
    ripper was offline; this is the regression guard.)"""
    raw_root = tmp_path / "raw"
    media_root = tmp_path / "media"
    raw_root.mkdir()
    media_root.mkdir()
    (raw_root / "job_a").mkdir()
    (raw_root / "job_a" / "title00.mkv").write_bytes(b"x")
    title_dir = media_root / "X (2000)"
    title_dir.mkdir()
    output_file = title_dir / "X (2000) - Track 01 - plex-1080p.mkv"
    output_file.write_bytes(b"y")

    monkeypatch.setattr(jobs_router.settings, "RAW_ROOT", str(raw_root))
    monkeypatch.setattr(jobs_router.settings, "MEDIA_ROOT", str(media_root))

    async def _fake_resolve(_db: Any, _job_id: str) -> list[Path]:
        return [output_file]

    monkeypatch.setattr(jobs_router, "_resolve_media_outputs", _fake_resolve)

    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [_make_job("job_a", status=JobStatus.RIPPED, drive_id="drv_42")]
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.delete("/api/jobs/job_a?delete_raw=true", headers=_auth(token))
    assert r.status_code == 204
    assert db.rows["jobs"] == []
    assert not (raw_root / "job_a").exists()
    assert not output_file.exists()
    # Title dir is the only output's parent and is now empty — should be pruned.
    assert not title_dir.exists()
    # No WS dispatched for this path.
    assert hub.events == []


@pytest.mark.parametrize(
    "status",
    [
        JobStatus.CREATED,
        JobStatus.AWAITING_USER_ID,
        JobStatus.IDENTIFIED,
        JobStatus.RIPPING,
    ],
)
def test_delete_non_terminal_returns_409(signing_key: bytes, status: JobStatus) -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [_make_job("job_a", status=status)]
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.delete("/api/jobs/job_a?delete_raw=true", headers=_auth(token))
    assert r.status_code == 409
    # Row preserved; WS not fired.
    assert len(db.rows["jobs"]) == 1
    assert hub.events == []


def test_delete_unknown_job_returns_404(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = []
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.delete("/api/jobs/job_missing", headers=_auth(token))
    assert r.status_code == 404


def test_bulk_delete_partitions_terminal_and_non_terminal(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [
        _make_job("job_done", status=JobStatus.RIPPED),
        _make_job("job_partial", status=JobStatus.RIPPED_PARTIAL),
        _make_job("job_failed", status=JobStatus.FAILED),
        _make_job("job_abandoned", status=JobStatus.ABANDONED),
        _make_job("job_running", status=JobStatus.RIPPING),
        _make_job("job_pending_id", status=JobStatus.AWAITING_USER_ID),
    ]
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.delete("/api/jobs", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert sorted(body["deleted_ids"]) == ["job_abandoned", "job_done", "job_failed", "job_partial"]
    assert sorted(body["skipped_non_terminal"]) == ["job_pending_id", "job_running"]
    # Survivors are the non-terminal ones.
    surviving_ids = sorted(j.id for j in db.rows["jobs"])
    assert surviving_ids == ["job_pending_id", "job_running"]
    # No WS unless delete_raw=true.
    assert hub.events == []


def test_bulk_delete_with_raw_cleans_each_terminal_job(
    signing_key: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bulk delete_raw=true runs the synchronous cleanup once per terminal
    job. The in-flight job is skipped and its files are untouched."""
    raw_root = tmp_path / "raw"
    media_root = tmp_path / "media"
    raw_root.mkdir()
    media_root.mkdir()
    for jid in ("job_a", "job_b", "job_active"):
        (raw_root / jid).mkdir()
        (raw_root / jid / "title00.mkv").write_bytes(b"x")

    monkeypatch.setattr(jobs_router.settings, "RAW_ROOT", str(raw_root))
    monkeypatch.setattr(jobs_router.settings, "MEDIA_ROOT", str(media_root))

    async def _fake_resolve(_db: Any, _job_id: str) -> list[Path]:
        return []

    monkeypatch.setattr(jobs_router, "_resolve_media_outputs", _fake_resolve)

    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [
        _make_job("job_a", status=JobStatus.RIPPED, drive_id="drv_1"),
        _make_job("job_b", status=JobStatus.FAILED, drive_id="drv_2"),
        _make_job("job_active", status=JobStatus.RIPPING, drive_id="drv_3"),
    ]
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.delete("/api/jobs?delete_raw=true", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert sorted(body["deleted_ids"]) == ["job_a", "job_b"]
    assert body["skipped_non_terminal"] == ["job_active"]
    # Terminal jobs' raw dirs are gone; in-flight job's raw dir is untouched.
    assert not (raw_root / "job_a").exists()
    assert not (raw_root / "job_b").exists()
    assert (raw_root / "job_active").exists()
    assert hub.events == []


def test_bulk_delete_empty_db_returns_empty_lists(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = []
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.delete("/api/jobs", headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == {"deleted_ids": [], "skipped_non_terminal": []}


def test_delete_removes_per_job_log(tmp_path: Any, signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    """The per-job aggregated log at `/logs/jobs/<job_id>.log` is removed
    when the Job row is hard-deleted. Cascade is filesystem-side, not
    DB-side — the DB doesn't know the file exists."""
    monkeypatch.setattr(logs_router, "LOG_DIR", tmp_path)
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    log_file = jobs_dir / "job_a.log"
    log_file.write_text('{"msg": "rip start"}\n{"msg": "rip done"}\n')

    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [_make_job("job_a", status=JobStatus.RIPPED)]
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.delete("/api/jobs/job_a", headers=_auth(token))
    assert r.status_code == 204
    assert not log_file.exists()


def test_delete_succeeds_when_per_job_log_missing(
    tmp_path: Any, signing_key: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Older jobs that ran before the per-job append landed have no log
    file. Delete must still succeed — no error, no 500."""
    monkeypatch.setattr(logs_router, "LOG_DIR", tmp_path)
    # Note: no /jobs/job_a.log exists.
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [_make_job("job_a", status=JobStatus.RIPPED)]
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.delete("/api/jobs/job_a", headers=_auth(token))
    assert r.status_code == 204


def test_bulk_delete_removes_per_job_logs(tmp_path: Any, signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bulk delete removes the per-job log for every job that was actually
    deleted. Skipped (non-terminal) jobs keep their logs."""
    monkeypatch.setattr(logs_router, "LOG_DIR", tmp_path)
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    (jobs_dir / "job_a.log").write_text("{}\n")
    (jobs_dir / "job_b.log").write_text("{}\n")
    (jobs_dir / "job_active.log").write_text("{}\n")

    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [
        _make_job("job_a", status=JobStatus.RIPPED, drive_id="drv_1"),
        _make_job("job_b", status=JobStatus.FAILED, drive_id="drv_2"),
        _make_job("job_active", status=JobStatus.RIPPING, drive_id="drv_3"),
    ]
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.delete("/api/jobs", headers=_auth(token))
    assert r.status_code == 200
    assert not (jobs_dir / "job_a.log").exists()
    assert not (jobs_dir / "job_b.log").exists()
    # The non-terminal job's log is preserved (job wasn't deleted).
    assert (jobs_dir / "job_active.log").exists()


# ---- _delete_job_files helper ---------------------------------------------


def test_delete_job_files_rmtrees_raw_dir(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    media_root = tmp_path / "media"
    media_root.mkdir()
    (raw_root / "job_a").mkdir(parents=True)
    (raw_root / "job_a" / "title00.mkv").write_bytes(b"x")
    (raw_root / "job_a" / "manifest.json").write_text("{}")

    counters = jobs_router._delete_job_files("job_a", [], raw_root=raw_root, media_root=media_root)
    assert counters == {"raw_dir_removed": 1, "media_files_removed": 0, "media_dirs_pruned": 0}
    assert not (raw_root / "job_a").exists()


def test_delete_job_files_unlinks_media_files_individually(tmp_path: Path) -> None:
    """Per-file unlink because re-rips of the same disc share `media/<Title>/`.
    Track-A from a deleted job must not take Track-B from a sibling re-rip
    down with it."""
    raw_root = tmp_path / "raw"
    media_root = tmp_path / "media"
    raw_root.mkdir()
    title_dir = media_root / "Sintel (2010)"
    title_dir.mkdir(parents=True)
    job_a_file = title_dir / "Sintel (2010) - Track 01 - plex-1080p.mkv"
    sibling_file = title_dir / "Sintel (2010) - Track 01 - plex-1080p-gpu-preferred.mkv"
    job_a_file.write_bytes(b"a")
    sibling_file.write_bytes(b"b")

    counters = jobs_router._delete_job_files("job_a", [job_a_file], raw_root=raw_root, media_root=media_root)
    assert counters["media_files_removed"] == 1
    assert not job_a_file.exists()
    # Sibling re-rip's output is preserved; title dir is non-empty so survives prune.
    assert sibling_file.exists()
    assert title_dir.exists()
    assert counters["media_dirs_pruned"] == 0


def test_delete_job_files_prunes_empty_title_dir(tmp_path: Path) -> None:
    """When the unlink leaves the title dir empty, rmdir it. Stops at
    `media_root` — never removes the root itself."""
    raw_root = tmp_path / "raw"
    media_root = tmp_path / "media"
    raw_root.mkdir()
    title_dir = media_root / "Sintel (2010)"
    title_dir.mkdir(parents=True)
    only_file = title_dir / "Sintel (2010) - Track 01 - plex-1080p.mkv"
    only_file.write_bytes(b"a")

    counters = jobs_router._delete_job_files("job_a", [only_file], raw_root=raw_root, media_root=media_root)
    assert counters["media_dirs_pruned"] >= 1
    assert not title_dir.exists()
    # The media root itself is intact.
    assert media_root.exists()


def test_delete_job_files_prunes_nested_dirs(tmp_path: Path) -> None:
    """Shows like `media/<Show>/Season 01/episode.mkv` should prune from
    the leaf upward until a non-empty stem is reached."""
    raw_root = tmp_path / "raw"
    media_root = tmp_path / "media"
    raw_root.mkdir()
    season_dir = media_root / "ShowName" / "Season 01"
    season_dir.mkdir(parents=True)
    ep = season_dir / "S01E01.mkv"
    ep.write_bytes(b"a")

    counters = jobs_router._delete_job_files("job_a", [ep], raw_root=raw_root, media_root=media_root)
    assert counters["media_dirs_pruned"] == 2
    assert not season_dir.exists()
    assert not (media_root / "ShowName").exists()
    assert media_root.exists()


def test_delete_job_files_is_idempotent_over_missing_files(tmp_path: Path) -> None:
    """All-missing inputs are a no-op return — same shape, all zeros."""
    raw_root = tmp_path / "raw"
    media_root = tmp_path / "media"
    raw_root.mkdir()
    media_root.mkdir()

    counters = jobs_router._delete_job_files(
        "job_never_was",
        [media_root / "Ghost (1990)" / "Ghost (1990) - Track 01.mkv"],
        raw_root=raw_root,
        media_root=media_root,
    )
    assert counters == {"raw_dir_removed": 0, "media_files_removed": 0, "media_dirs_pruned": 0}


def test_prune_empty_dirs_refuses_path_outside_root(tmp_path: Path) -> None:
    """A media output path outside `media_root` must NOT cause a prune walk
    that could ascend into unrelated parts of the filesystem."""
    media_root = tmp_path / "media"
    media_root.mkdir()
    outside = tmp_path / "elsewhere" / "stuff"
    outside.mkdir(parents=True)

    pruned = jobs_router._prune_empty_dirs(outside, media_root)
    assert pruned == 0
    assert outside.exists()
