"""Jobs router coverage: list (filters + ripping progress), job detail,
abandon, update, resolve, delete log-cleanup error branch, and the
apply-session exception mapping. Delete/bulk-delete and the apply happy/
collision paths are covered by test_jobs_delete.py / test_apply_session.py.
"""

from __future__ import annotations

import os
import secrets
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from arm_backend.auto_session import ApplySessionOutcome, SessionNotFoundError  # noqa: E402
from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.path_template import TemplateValidationError  # noqa: E402
from arm_backend.routers import jobs as jobs_router  # noqa: E402
from arm_common import (  # noqa: E402
    DiscFingerprint,
    DiscType,
    Drive,
    DriveMediaStatus,
    DriveStatus,
    Job,
    JobStatus,
    MediaType,
    Session,
    SessionApplication,
    SessionApplicationStatus,
    TrackStatus,
    User,
)
from arm_common.enums import TrackKind  # noqa: E402
from arm_common.models import Track  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


class _Hub:
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


def _make_app(signing_key: bytes, db: FakeSession, hub: _Hub | None = None) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.ws_hub = hub or _Hub()
    app.include_router(jobs_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _job(job_id: str = "job_x", *, status: JobStatus = JobStatus.RIPPED, meta: dict | None = None) -> Job:
    return Job(
        id=job_id,
        drive_id="drv_x",
        disc_type=DiscType.DVD,
        title="X",
        year=2000,
        status=status,
        metadata_json=meta if meta is not None else {},
        resumed_from_crash=False,
    )


def _track(track_id: str, *, status: TrackStatus, index: int = 1, job_id: str = "job_x") -> Track:
    return Track(
        id=track_id,
        job_id=job_id,
        kind=TrackKind.VIDEO_TITLE,
        index=index,
        source_ref=str(index),
        status=status,
        attempts=0,
    )


# --- list_jobs ---------------------------------------------------------------


def test_list_jobs_filters_and_rip_progress(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["jobs"] = [
        _job("job_rip", status=JobStatus.RIPPING),
        _job("job_done", status=JobStatus.RIPPED),
    ]
    db.rows["tracks"] = [
        _track("t1", status=TrackStatus.DONE, index=1, job_id="job_rip"),
        _track("t2", status=TrackStatus.IN_PROGRESS, index=2, job_id="job_rip"),
        _track("t3", status=TrackStatus.QUEUED, index=3, job_id="job_rip"),
    ]
    with TestClient(app) as client:
        all_jobs = client.get("/api/jobs", headers=_auth(token))
        by_status = client.get("/api/jobs?status=ripping", headers=_auth(token))
        by_drive = client.get("/api/jobs?drive_id=drv_x", headers=_auth(token))
    assert all_jobs.status_code == 200
    assert len(all_jobs.json()) == 2
    ripping = next(j for j in all_jobs.json() if j["id"] == "job_rip")
    assert ripping["rip_progress"]["tracks_total"] == 3
    assert ripping["rip_progress"]["tracks_done"] == 1
    assert ripping["rip_progress"]["current_track_id"] == "t2"
    assert ripping["rip_progress"]["current_track_index"] == 2
    assert [j["id"] for j in by_status.json()] == ["job_rip"]
    assert len(by_drive.json()) == 2


# --- get_job_detail ----------------------------------------------------------


def test_get_job_detail_found(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["jobs"] = [_job("job_x", status=JobStatus.RIPPED)]
    db.rows["tracks"] = [_track("t1", status=TrackStatus.DONE)]
    db.rows["disc_fingerprints"] = [DiscFingerprint(id="dfp_1", job_id="job_x", algo="crc64", value="abc")]
    with TestClient(app) as client:
        r = client.get("/api/jobs/job_x", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["job"]["id"] == "job_x"
    assert [t["id"] for t in body["tracks"]] == ["t1"]
    assert [f["algo"] for f in body["fingerprints"]] == ["crc64"]


def test_get_job_detail_404(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/jobs/missing", headers=_auth(token))
    assert r.status_code == 404


# --- abandon_job -------------------------------------------------------------


def test_abandon_404(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post("/api/jobs/missing/abandon", headers=_auth(token))
    assert r.status_code == 404


def test_abandon_terminal_409(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["jobs"] = [_job(status=JobStatus.RIPPED)]
    with TestClient(app) as client:
        r = client.post("/api/jobs/job_x/abandon", headers=_auth(token))
    assert r.status_code == 409
    assert "terminal status" in r.json()["detail"]


def test_abandon_success_emits_with_delete_raw(signing_key: bytes) -> None:
    db = FakeSession()
    hub = _Hub()
    app, token = _make_app(signing_key, db, hub)
    db.rows["jobs"] = [_job(status=JobStatus.RIPPING)]
    with TestClient(app) as client:
        r = client.post("/api/jobs/job_x/abandon", json={"delete_raw": True}, headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["status"] == "abandoned"
    types = {e["event_type"] for e in hub.events}
    assert {"job.abandoned", "rip.abandoned"} <= types
    assert all(e["payload"]["delete_raw"] is True for e in hub.events)


# --- delete_job log-cleanup error branch -------------------------------------


def test_delete_job_swallows_log_unlink_error(
    signing_key: bytes, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["jobs"] = [_job(status=JobStatus.RIPPED)]

    class _BadPath:
        def unlink(self, missing_ok: bool = False) -> None:
            raise OSError("disk gone")

    monkeypatch.setattr(jobs_router, "per_job_log_path", lambda _jid: _BadPath())
    with TestClient(app) as client:
        with caplog.at_level("WARNING", logger="arm_backend.routers.jobs"):
            r = client.delete("/api/jobs/job_x", headers=_auth(token))
    assert r.status_code == 204
    assert any("per-job log delete failed" in rec.message for rec in caplog.records)


# --- manual_trigger ----------------------------------------------------------


def _drive(*, media: DriveMediaStatus | None = None, fresh: bool = True) -> Drive:
    from datetime import datetime, timezone

    d = Drive(id="drv_x", hostname="h", device_path="/dev/sr0", status=DriveStatus.ONLINE)
    if media is not None:
        d.media_status = media
        d.media_status_at = datetime.now(timezone.utc)
    return d


def test_manual_trigger_unknown_drive_404(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post("/api/jobs/manual", json={"drive_id": "nope"}, headers=_auth(token))
    assert r.status_code == 404


def test_manual_trigger_in_flight_409(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [_job(status=JobStatus.RIPPING)]
    with TestClient(app) as client:
        r = client.post("/api/jobs/manual", json={"drive_id": "drv_x"}, headers=_auth(token))
    assert r.status_code == 409
    assert "in-flight RIPPING" in r.json()["detail"]


def test_manual_trigger_media_not_ready_400(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["drives"] = [_drive(media=DriveMediaStatus.TRAY_OPEN)]
    db.rows["jobs"] = []
    with TestClient(app) as client:
        r = client.post("/api/jobs/manual", json={"drive_id": "drv_x"}, headers=_auth(token))
    assert r.status_code == 400
    assert "tray is open" in r.json()["detail"]


def test_manual_trigger_unknown_session_400(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["drives"] = [_drive(media=DriveMediaStatus.LOADED)]
    db.rows["jobs"] = []
    db.rows["sessions"] = []
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/manual",
            json={"drive_id": "drv_x", "session_id": "ses_missing"},
            headers=_auth(token),
        )
    assert r.status_code == 400
    assert "unknown session_id" in r.json()["detail"]


def test_manual_trigger_success_202(signing_key: bytes) -> None:
    db = FakeSession()
    hub = _Hub()
    app, token = _make_app(signing_key, db, hub)
    db.rows["drives"] = [_drive(media=DriveMediaStatus.LOADED)]
    db.rows["jobs"] = []
    db.rows["sessions"] = [
        Session(
            id="ses_1",
            name="S",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_1",
            output_path_template="{title}.{ext}",
        )
    ]
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/manual",
            json={"drive_id": "drv_x", "session_id": "ses_1"},
            headers=_auth(token),
        )
    assert r.status_code == 202
    assert r.json() == {"drive_id": "drv_x", "session_id": "ses_1"}
    assert any(e["event_type"] == "manual.trigger" for e in hub.events)


# --- update_job --------------------------------------------------------------


def test_update_job_404(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/jobs/missing", json={"poster_url_manual": "http://x/y.jpg"}, headers=_auth(token))
    assert r.status_code == 404


def test_update_job_sets_poster(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["jobs"] = [_job(status=JobStatus.RIPPED)]
    with TestClient(app) as client:
        r = client.patch(
            "/api/jobs/job_x",
            json={"poster_url_manual": "http://x/y.jpg"},
            headers=_auth(token),
        )
    assert r.status_code == 200
    assert r.json()["poster_url_manual"] == "http://x/y.jpg"


# --- resolve -----------------------------------------------------------------


def test_resolve_404(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post("/api/jobs/missing/resolve", json={"title": "T"}, headers=_auth(token))
    assert r.status_code == 404


def test_resolve_not_awaiting_409(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["jobs"] = [_job(status=JobStatus.RIPPED)]
    with TestClient(app) as client:
        r = client.post("/api/jobs/job_x/resolve", json={"title": "T"}, headers=_auth(token))
    assert r.status_code == 409
    assert "not awaiting_user_id" in r.json()["detail"]


def test_resolve_success_preserves_scan_and_emits(signing_key: bytes) -> None:
    db = FakeSession()
    hub = _Hub()
    app, token = _make_app(signing_key, db, hub)
    db.rows["jobs"] = [_job(status=JobStatus.AWAITING_USER_ID, meta={"scan_result": {"disc_type": "dvd"}})]
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_x/resolve",
            json={"title": "Blade Runner", "year": 1982, "metadata": {"tmdb_id": 78}},
            headers=_auth(token),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "identified"
    assert body["title"] == "Blade Runner"
    assert body["metadata_json"]["scan_result"] == {"disc_type": "dvd"}
    assert body["metadata_json"]["tmdb_id"] == 78
    types = {e["event_type"] for e in hub.events}
    assert {"identify.resolved", "rip.identify_resolved"} <= types


def test_resolve_success_without_preserved_scan(signing_key: bytes) -> None:
    """job.metadata_json has no scan_result — the preserve branch is
    skipped (covers the `preserved_scan is None` path)."""
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["jobs"] = [_job(status=JobStatus.AWAITING_USER_ID, meta={})]
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_x/resolve",
            json={"title": "Solaris", "metadata": {"k": "v"}},
            headers=_auth(token),
        )
    assert r.status_code == 200
    assert "scan_result" not in r.json()["metadata_json"]
    assert r.json()["metadata_json"]["k"] == "v"


# --- apply_session exception mapping (happy/collision in test_apply_session) --


def _apply_app(signing_key: bytes, db: FakeSession, monkeypatch: pytest.MonkeyPatch, fn: Any) -> tuple[FastAPI, str]:
    app, token = _make_app(signing_key, db)
    db.rows["jobs"] = [_job(status=JobStatus.RIPPED)]
    monkeypatch.setattr(jobs_router, "apply_session_internal", fn)
    return app, token


def test_apply_session_job_404(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post("/api/jobs/missing/transcode", json={"session_id": "s"}, headers=_auth(token))
    assert r.status_code == 404


def test_apply_session_unknown_session_400(signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSession()

    async def _raise(*_a: Any, **_k: Any) -> None:
        raise SessionNotFoundError("s")

    app, token = _apply_app(signing_key, db, monkeypatch, _raise)
    with TestClient(app) as client:
        r = client.post("/api/jobs/job_x/transcode", json={"session_id": "s"}, headers=_auth(token))
    assert r.status_code == 400
    assert "unknown session_id" in r.json()["detail"]


def test_apply_session_template_error_422(signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSession()

    async def _raise(*_a: Any, **_k: Any) -> None:
        raise TemplateValidationError("bad template")

    app, token = _apply_app(signing_key, db, monkeypatch, _raise)
    with TestClient(app) as client:
        r = client.post("/api/jobs/job_x/transcode", json={"session_id": "s"}, headers=_auth(token))
    assert r.status_code == 422
    assert "bad template" in r.json()["detail"]


def test_apply_session_integrity_error_409(signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSession()

    async def _raise(*_a: Any, **_k: Any) -> None:
        raise IntegrityError("stmt", {}, Exception("dup"))

    app, token = _apply_app(signing_key, db, monkeypatch, _raise)
    with TestClient(app) as client:
        r = client.post("/api/jobs/job_x/transcode", json={"session_id": "s"}, headers=_auth(token))
    assert r.status_code == 409
    assert "concurrent application" in r.json()["detail"]


def test_apply_session_collisions_409(signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSession()
    from arm_common.schemas import CollisionInfo

    async def _outcome(*_a: Any, **_k: Any) -> ApplySessionOutcome:
        return ApplySessionOutcome(
            application=None,
            tasks=[],
            collisions=[
                CollisionInfo(
                    output_path="a.mkv",
                    existing_task_id="txt_1",
                    on_filesystem=False,
                    reason="existing_task",
                )
            ],
            idempotent=False,
            skipped_reason="collisions",
        )

    app, token = _apply_app(signing_key, db, monkeypatch, _outcome)
    with TestClient(app) as client:
        r = client.post("/api/jobs/job_x/transcode", json={"session_id": "s"}, headers=_auth(token))
    assert r.status_code == 409
    assert r.json()["detail"]["message"] == "output_path collisions detected"
    assert r.json()["detail"]["collisions"][0]["output_path"] == "a.mkv"


def test_apply_session_success(signing_key: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSession()

    async def _outcome(*_a: Any, **_k: Any) -> ApplySessionOutcome:
        return ApplySessionOutcome(
            application=SessionApplication(
                id="sap_1",
                session_id="ses_1",
                job_id="job_x",
                status=SessionApplicationStatus.QUEUED,
                overwrite=False,
            ),
            tasks=[],
            collisions=[],
            idempotent=True,
            skipped_reason=None,
        )

    app, token = _apply_app(signing_key, db, monkeypatch, _outcome)
    with TestClient(app) as client:
        r = client.post("/api/jobs/job_x/transcode", json={"session_id": "ses_1"}, headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["session_application"]["id"] == "sap_1"
    assert body["idempotent"] is True
    assert body["collisions"] == []
