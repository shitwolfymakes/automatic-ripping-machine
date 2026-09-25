"""End-to-end tests for `POST /api/jobs/{id}/transcode` (apply-session)."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import jobs as jobs_router  # noqa: E402
from arm_common import (  # noqa: E402
    Config,
    ContainerFormat,
    DiscType,
    HwPreference,
    IdentificationMode,
    Job,
    JobStatus,
    MediaType,
    OutputMode,
    RipPreset,
    Session,
    SessionApplication,
    SessionApplicationStatus,
    Track,
    TrackKind,
    TrackSelection,
    TrackStatus,
    TranscodePreset,
    TranscodeTask,
    TranscodeTaskStatus,
    TranscodeTool,
    User,
)

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession, *, job_status: JobStatus = JobStatus.RIPPED) -> None:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["jobs"] = [
        Job(
            id="job_01JZXR7K3M5Q8N4VWA00000001",
            drive_id="drv_x",
            disc_type=DiscType.DVD,
            title="Iron Man",
            year=2008,
            status=job_status,
            metadata_json={},
        )
    ]
    db.rows["rip_presets"] = [
        RipPreset(
            id="rpr_x",
            name="Movie main",
            media_type=MediaType.MOVIE,
            is_builtin=True,
            track_selection=TrackSelection.MAIN_FEATURE,
            identification_mode=IdentificationMode.REQUIRED,
            output_mode=OutputMode.TRACKS,
        )
    ]
    db.rows["transcode_presets"] = [
        TranscodePreset(
            id="tpr_x",
            name="Plex 1080p H.265",
            media_type=MediaType.MOVIE,
            is_builtin=True,
            tool=TranscodeTool.HANDBRAKE,
            container=ContainerFormat.MKV,
            hw_preference=HwPreference.CPU_ONLY,
        )
    ]
    db.rows["sessions"] = [
        Session(
            id="ses_x",
            name="My Plex",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_x",
            transcode_preset_id="tpr_x",
            output_path_template="{title} ({year})/{title} - {transcode_slug}.{ext}",
        )
    ]
    db.rows["tracks"] = [
        Track(
            id="trk_1",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            kind=TrackKind.VIDEO_TITLE,
            index=1,
            source_ref="1",
            expected_duration_seconds=8000,
            status=TrackStatus.DONE,
        )
    ]
    db.rows["transcode_tasks"] = []
    db.rows["session_applications"] = []
    db.rows["drives"] = []


def _seed_config(db: FakeSession, *, transcode_enabled: bool | None) -> None:
    db.rows["config"] = [Config(id=1, transcode_enabled=transcode_enabled)]


class _CapturingHub:
    """Minimal hub stand-in that records emit calls for assertions."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def emit(
        self,
        topic: str,
        event_type: str,
        payload: dict[str, object],
        *,
        persist: bool = True,
        job_id: str | None = None,
        track_id: str | None = None,
        session: object = None,
    ) -> None:
        self.events.append({"topic": topic, "event_type": event_type, "payload": payload})


def _make_app(
    signing_key: bytes,
    db: FakeSession,
    tmp_media_root: Path,
    *,
    hub: object | None = None,
) -> tuple[FastAPI, str]:
    from arm_backend import config as bcfg

    bcfg.settings.MEDIA_ROOT = str(tmp_media_root)

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


def test_apply_happy_path_creates_application_and_tasks(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["idempotent"] is False
    assert body["session_application"]["status"] == "queued"
    assert len(body["tasks"]) == 1
    assert body["tasks"][0]["output_path"] == "Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv"
    assert body["tasks"][0]["status"] == "queued"
    assert body["collisions"] == []


def test_manual_reapply_with_existing_done_returns_collisions_for_overwrite_prompt(
    signing_key: bytes, tmp_path: Path
) -> None:
    """Manual apply is non-idempotent: re-clicking Apply on a job whose
    previous application is DONE surfaces a collision (the existing DB row
    at the same output_path), so the UI can show the overwrite confirm
    dialog. The user can then post `overwrite=true` to redo the work
    (separate test below)."""
    db = FakeSession()
    _seed(db)
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_existing",
            session_id="ses_x",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            status=SessionApplicationStatus.DONE,
            overwrite=False,
        )
    ]
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_existing",
            session_application_id="sap_existing",
            source_track_id="trk_1",
            status=TranscodeTaskStatus.DONE,
            output_path="Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv",
            attempts=1,
            progress_pct=100,
        )
    ]
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["collisions"][0]["existing_task_id"] == "txt_existing"
    assert detail["collisions"][0]["reason"] == "existing_task"


def test_manual_reapply_with_overwrite_evicts_done_tasks_and_creates_new(signing_key: bytes, tmp_path: Path) -> None:
    """`overwrite=true` on a manual re-apply should delete the colliding
    DONE/QUEUED/FAILED tasks (they're history at this point) and create
    a fresh application + tasks. The empty session_application left
    behind also gets cleaned up so the JobDetail page doesn't accumulate
    husk rows."""
    db = FakeSession()
    _seed(db)
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_existing",
            session_id="ses_x",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            status=SessionApplicationStatus.DONE,
            overwrite=False,
        )
    ]
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_existing",
            session_application_id="sap_existing",
            source_track_id="trk_1",
            status=TranscodeTaskStatus.DONE,
            output_path="Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv",
            attempts=1,
            progress_pct=100,
        )
    ]
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x", "overwrite": True},
            headers=_auth(token),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["idempotent"] is False
    # The new application is freshly created, not "sap_existing".
    new_app_id = body["session_application"]["id"]
    assert new_app_id != "sap_existing"
    # Old task was deleted; only the new task remains at this path.
    paths = [t.output_path for t in db.rows["transcode_tasks"]]
    assert paths == ["Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv"]
    assert db.rows["transcode_tasks"][0].id != "txt_existing"
    # Husk session_application got cleaned up.
    assert all(a.id != "sap_existing" for a in db.rows["session_applications"])


def test_manual_reapply_overwrite_refused_when_in_progress(signing_key: bytes, tmp_path: Path) -> None:
    """Don't displace a transcoder that's actively writing — even with
    `overwrite=true`, an IN_PROGRESS collision on the *same* job's own prior
    application is a hard 409 telling the user to cancel the running task
    explicitly first (G-08: eviction is scoped to the applying job, but a
    same-job in-progress task is still refused, not silently skipped)."""
    db = FakeSession()
    _seed(db)
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_other",
            session_id="ses_x",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            status=SessionApplicationStatus.RUNNING,
            overwrite=False,
        )
    ]
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_running",
            session_application_id="sap_other",
            source_track_id="trk_other",
            status=TranscodeTaskStatus.IN_PROGRESS,
            output_path="Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv",
            attempts=1,
            progress_pct=42,
            claimed_by="arm-transcode-running",
        )
    ]
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x", "overwrite": True},
            headers=_auth(token),
        )
    assert r.status_code == 409
    assert "in_progress" in r.json()["detail"].lower()


def test_manual_reapply_overwrite_cross_job_in_progress_is_reported_not_refused(
    signing_key: bytes, tmp_path: Path
) -> None:
    """A *different* job's IN_PROGRESS task at the same output_path is never
    reachable by this job's eviction at all (G-08 scoping) — it surfaces as
    an ordinary cross-job `skipped_reason="collisions"` (409 collisions,
    not the in-progress-refusal 409), naming the owning job."""
    db = FakeSession()
    _seed(db)
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_other",
            session_id="ses_x",
            job_id="job_01JZXR7K3M5Q8N4VWA0000000J",
            status=SessionApplicationStatus.RUNNING,
            overwrite=False,
        )
    ]
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_running",
            session_application_id="sap_other",
            source_track_id="trk_other",
            status=TranscodeTaskStatus.IN_PROGRESS,
            output_path="Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv",
            attempts=1,
            progress_pct=42,
            claimed_by="arm-transcode-running",
        )
    ]
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x", "overwrite": True},
            headers=_auth(token),
        )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["message"] == "output_path collisions detected"
    assert detail["collisions"][0]["existing_job_id"] == "job_01JZXR7K3M5Q8N4VWA0000000J"
    # The other job's in-progress task is untouched.
    assert any(t.id == "txt_running" for t in db.rows["transcode_tasks"])


def test_apply_collision_409_lists_paths(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_other",
            session_application_id="sap_other",
            source_track_id="trk_other",
            status=TranscodeTaskStatus.QUEUED,
            output_path="Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv",
        )
    ]
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["message"] == "output_path collisions detected"
    assert detail["collisions"][0]["existing_task_id"] == "txt_other"
    assert detail["collisions"][0]["reason"] == "existing_task"


def test_apply_overwrite_true_clears_collision(signing_key: bytes, tmp_path: Path) -> None:
    """overwrite=True clears a collision owned by THIS job (a prior
    session_application for job_01JZXR7K3M5Q8N4VWA00000001) — the
    same-job case licensed for eviction."""
    db = FakeSession()
    _seed(db)
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_other",
            session_id="ses_x",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            status=SessionApplicationStatus.DONE,
            overwrite=False,
        )
    ]
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_other",
            session_application_id="sap_other",
            source_track_id="trk_other",
            status=TranscodeTaskStatus.QUEUED,
            output_path="Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv",
        )
    ]
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x", "overwrite": True},
            headers=_auth(token),
        )
    assert r.status_code == 200
    assert r.json()["session_application"]["overwrite"] is True


def test_apply_overwrite_true_unowned_task_still_409s(signing_key: bytes, tmp_path: Path) -> None:
    """Fix 76-5: overwrite=True must NOT clear a collision whose owning
    session_application is missing (existing_job_id can't be resolved) —
    an unowned task is treated as cross-job, always reported, never
    evicted, even under overwrite."""
    db = FakeSession()
    _seed(db)
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_other",
            session_application_id="sap_missing",  # no matching session_applications row
            source_track_id="trk_other",
            status=TranscodeTaskStatus.QUEUED,
            output_path="Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv",
        )
    ]
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x", "overwrite": True},
            headers=_auth(token),
        )
    assert r.status_code == 409
    assert r.json()["detail"]["collisions"][0]["existing_task_id"] == "txt_other"


def test_apply_filesystem_collision_detected(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    _seed(db)
    target = tmp_path / "Iron Man (2008)"
    target.mkdir(parents=True)
    (target / "Iron Man - plex-1080p-h-265.mkv").write_text("pre-existing")
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["collisions"][0]["on_filesystem"] is True
    assert detail["collisions"][0]["reason"] == "on_disk"


def test_apply_duplicate_in_request_collision_for_multi_track_no_track_token(
    signing_key: bytes, tmp_path: Path
) -> None:
    """Multi-track rip + template without `{track}` → all tracks resolve to same path.

    Surfaces as `reason="duplicate_in_request"` (not `on_disk`), so the dialog
    can tell the user to fix the template instead of pointing at a non-existent file.
    """
    db = FakeSession()
    _seed(db)
    db.rows["tracks"].append(
        Track(
            id="trk_2",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            kind=TrackKind.VIDEO_TITLE,
            index=2,
            source_ref="2",
            expected_duration_seconds=7000,
            status=TrackStatus.DONE,
        )
    )
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert len(detail["collisions"]) == 1
    c = detail["collisions"][0]
    assert c["reason"] == "duplicate_in_request"
    assert c["existing_task_id"] is None
    assert c["on_filesystem"] is False


def test_manual_apply_media_mismatch_is_422(signing_key: bytes, tmp_path: Path) -> None:
    """G-04: applying a movie session to a job identified as music (or vice
    versa) is a client error, not a silent empty fan-out. The detail names
    both types so the operator can see the mismatch."""
    db = FakeSession()
    _seed(db)
    db.rows["jobs"][0].media_type = MediaType.MUSIC
    db.rows["sessions"][0].media_type = MediaType.MOVIE
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "media" in detail
    assert "not compatible with" in detail
    assert "movie" in detail
    assert "music" in detail
    assert db.rows["transcode_tasks"] == []
    assert db.rows["session_applications"] == []


def test_manual_apply_media_mismatch_does_not_requery_router_side(
    signing_key: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix 76-7: the router must build the 422 detail from
    `outcome.error_detail` (computed once inside apply_session_internal at
    the media_mismatch guard site), not by re-SELECTing the Session and
    bare-asserting it's non-None — a concurrent delete (or `python -O`,
    which strips asserts) would turn that re-query path into a 500. Pin the
    structural change two ways: (1) jobs.py no longer imports
    `media_mismatch_detail` at all (asserted here directly against the
    module), and (2) `select` is never called from within the apply_session
    endpoint after apply_session_internal returns a media_mismatch outcome
    (the only pre-fix call site for the re-query)."""
    from arm_backend.routers import jobs as jobs_router_module

    assert not hasattr(jobs_router_module, "media_mismatch_detail"), (
        "jobs.py must not import media_mismatch_detail: the router reads outcome.error_detail instead (Fix 76-7)"
    )

    real_select = jobs_router_module.select
    select_calls_after_mismatch: list[object] = []
    mismatch_reached = False

    def _tracking_select(*args: object, **kwargs: object) -> object:
        if mismatch_reached:
            select_calls_after_mismatch.append(args)
        return real_select(*args, **kwargs)

    db = FakeSession()
    _seed(db)
    db.rows["jobs"][0].media_type = MediaType.MUSIC
    db.rows["sessions"][0].media_type = MediaType.MOVIE
    app, token = _make_app(signing_key, db, tmp_path)

    real_apply_session_internal = jobs_router_module.apply_session_internal

    async def _wrapped_apply(*args: object, **kwargs: object) -> object:
        nonlocal mismatch_reached
        outcome = await real_apply_session_internal(*args, **kwargs)  # type: ignore[arg-type]
        mismatch_reached = outcome.skipped_reason == "media_mismatch"
        return outcome

    monkeypatch.setattr(jobs_router_module, "select", _tracking_select)
    monkeypatch.setattr(jobs_router_module, "apply_session_internal", _wrapped_apply)

    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 422
    assert select_calls_after_mismatch == []
    detail = r.json()["detail"]
    assert "not compatible with" in detail
    assert "movie" in detail
    assert "music" in detail


def test_manual_apply_tv_session_on_movie_job_succeeds(signing_key: bytes, tmp_path: Path) -> None:
    """C1: movie and tv are the same track kind (VIDEO_TITLE) — a TV session
    manually applied to a job identified as a movie (or vice versa) must
    fan out, not 422 as a mismatch."""
    db = FakeSession()
    _seed(db)
    db.rows["jobs"][0].media_type = MediaType.MOVIE
    db.rows["sessions"][0].media_type = MediaType.TV
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["tasks"]) == 1
    assert body["collisions"] == []


def test_manual_apply_iso_session_on_movie_job_succeeds(signing_key: bytes, tmp_path: Path) -> None:
    """C1: an iso session applied to a movie job must fan out — no
    identified job is ever `iso`, so an iso drive-default/route must still
    apply to a video disc's job or it dead-ends every rip."""
    db = FakeSession()
    _seed(db)
    db.rows["jobs"][0].media_type = MediaType.MOVIE
    db.rows["sessions"][0].media_type = MediaType.ISO
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["tasks"]) == 1
    assert body["collisions"] == []


def test_apply_to_unidentified_job_creates_waiting_identify(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    _seed(db, job_status=JobStatus.AWAITING_USER_ID)
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["session_application"]["status"] == "waiting_identify"
    assert body["tasks"] == []


def test_apply_rejects_job_in_bad_status(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    _seed(db, job_status=JobStatus.RIPPING)
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 409


def test_apply_unknown_session_400(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_does_not_exist"},
            headers=_auth(token),
        )
    assert r.status_code == 400


def test_apply_integrity_race_returns_409(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    _seed(db)
    db.commit_raises = IntegrityError("stmt", {}, Exception("partial unique"))
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 409
    assert "concurrent" in r.json()["detail"].lower()


def test_apply_emits_session_queued_with_manual_source(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    _seed(db)
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, tmp_path, hub=hub)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    queued = [e for e in hub.events if e["event_type"] == "session.queued"]
    assert len(queued) == 1
    payload = queued[0]["payload"]
    assert payload["source"] == "manual"
    assert payload["job_id"] == "job_01JZXR7K3M5Q8N4VWA00000001"
    assert payload["task_count"] == 1


def test_apply_to_identified_unripped_job_parks_as_waiting_identify(signing_key: bytes, tmp_path: Path) -> None:
    """Apply between identify and rip-start: the job is `identified` but has no
    Track rows yet (the ripper persists them at rip-start). The application
    must park rather than fan out an empty `queued` application."""
    db = FakeSession()
    _seed(db, job_status=JobStatus.IDENTIFIED)
    db.rows["tracks"] = []
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_application"]["status"] == "waiting_identify"
    assert body["tasks"] == []
    assert len(db.rows["session_applications"]) == 1
    assert db.rows["session_applications"][0].status == SessionApplicationStatus.WAITING_IDENTIFY
    assert db.rows["transcode_tasks"] == []


def test_apply_records_the_operator(signing_key: bytes, tmp_path: Path) -> None:
    """G-07: a manual apply stamps created_by_user_id with the caller, so
    the audit trail can say who queued a transcode (auto stays None)."""
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    assert db.rows["session_applications"][0].created_by_user_id == "usr_admin"


def test_apply_to_ripped_awaiting_identify_parks_as_waiting_identify(signing_key: bytes, tmp_path: Path) -> None:
    """G-09: a completed placeholder rip still has no identity; applying a
    session parks it exactly like the pre-rip unidentified case, and
    resolve's after-rip pass promotes it."""
    db = FakeSession()
    _seed(db, job_status=JobStatus.RIPPED_AWAITING_IDENTIFY)
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_application"]["status"] == "waiting_identify"
    assert body["tasks"] == []


def test_apply_ripped_with_all_tracks_excluded_parks_as_no_outputs_not_no_tracks(
    signing_key: bytes, tmp_path: Path
) -> None:
    """Fix 75-7 regression: on a RIPPED job whose only track is excluded,
    Track rows DO exist but compute_outputs legitimately resolves zero
    paths. Before the fix, the park decision was keyed on `not resolved`
    (compute_outputs' result) rather than `not tracks`, so this case was
    indistinguishable from the genuine pre-rip "no tracks yet" case and
    reported skipped_reason=no_tracks -- a promise of a rip-complete
    fan-out that can never happen, because the rip is already done and the
    excluded track will never un-exclude itself. It must report the
    distinct, honest "no_outputs" reason instead, and the application must
    never be promoted to queued."""
    db = FakeSession()
    _seed(db, job_status=JobStatus.RIPPED)
    db.rows["tracks"][0].excluded = True
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_application"]["status"] == "waiting_identify"
    assert body["tasks"] == []
    assert db.rows["session_applications"][0].status == SessionApplicationStatus.WAITING_IDENTIFY
    assert db.rows["transcode_tasks"] == []

    # The drain must never promote this empty husk to queued: re-running the
    # fan-out (as rip-complete/resolve would) against the same tracks still
    # resolves zero outputs and must leave the application parked.
    import asyncio

    from arm_backend.auto_session import fan_out_waiting_identify_applications

    class _NoopHub:
        async def emit(self, *args: object, **kwargs: object) -> None:
            return None

    job = db.rows["jobs"][0]
    outcomes = asyncio.run(fan_out_waiting_identify_applications(db, job=job, hub=_NoopHub()))  # type: ignore[arg-type]
    assert len(outcomes) == 1
    assert outcomes[0].skipped_reason == "no_outputs"
    assert outcomes[0].application.status == SessionApplicationStatus.WAITING_IDENTIFY
    assert db.rows["session_applications"][0].status == SessionApplicationStatus.WAITING_IDENTIFY
    assert db.rows["transcode_tasks"] == []


def test_encode_apply_refused_when_disabled(signing_key: bytes, tmp_path: Path) -> None:
    """An encode-preset session (HANDBRAKE) is refused with a typed 422 when
    the operator has turned transcoding off; no application row is created."""
    db = FakeSession()
    _seed(db)
    _seed_config(db, transcode_enabled=False)
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 422, r.text
    assert "transcoding is disabled" in r.json()["detail"]
    assert db.rows["session_applications"] == []


def test_passthrough_apply_flows_when_disabled(signing_key: bytes, tmp_path: Path) -> None:
    """A passthrough preset (TranscodeTool.NONE) is never gated by the toggle."""
    db = FakeSession()
    _seed(db)
    db.rows["transcode_presets"].append(
        TranscodePreset(
            id="tpr_pass",
            name="Passthrough",
            media_type=MediaType.MOVIE,
            is_builtin=True,
            tool=TranscodeTool.NONE,
            container=ContainerFormat.MKV,
            hw_preference=HwPreference.CPU_ONLY,
        )
    )
    db.rows["sessions"].append(
        Session(
            id="ses_pass",
            name="Passthrough",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_x",
            transcode_preset_id="tpr_pass",
            output_path_template="{title} ({year})/{title} - {transcode_slug}.{ext}",
        )
    )
    _seed_config(db, transcode_enabled=False)
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_pass"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text


def test_no_preset_session_flows_when_disabled(signing_key: bytes, tmp_path: Path) -> None:
    """`transcode_preset_id=None` is passthrough by definition (worker main.py:198)."""
    db = FakeSession()
    _seed(db)
    db.rows["sessions"].append(
        Session(
            id="ses_nopreset",
            name="No preset",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_x",
            transcode_preset_id=None,
            output_path_template="{title} ({year})/{title}.mkv",
        )
    )
    _seed_config(db, transcode_enabled=False)
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_nopreset"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text


def test_null_toggle_column_means_enabled(signing_key: bytes, tmp_path: Path) -> None:
    """`config.transcode_enabled = None` (pre-backfill row) reads as enabled;
    an encode apply must still succeed."""
    db = FakeSession()
    _seed(db)
    _seed_config(db, transcode_enabled=None)
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
