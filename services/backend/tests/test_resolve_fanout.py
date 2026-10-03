"""End-to-end tests for resolve's `waiting_identify` → `queued` fan-out.

Resolve transitions a job from `awaiting_user_id` (or `ripped_awaiting_identify`)
to `identified` and, in the same handler, promotes every parked
`session_application` for that job: load its session/preset/tracks, run the
shared `_fan_out_tasks_for_application` helper, and either flip it to `queued`
with TranscodeTask rows or leave it parked with a per-application
`skipped_reason` in the response body. Identify itself never fails because of
a fan-out problem.
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
from arm_common import (  # noqa: E402
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


def _seed(
    db: FakeSession,
    *,
    job_status: JobStatus = JobStatus.AWAITING_USER_ID,
    job_title: str | None = None,
    template: str = "{title} ({year})/{title} - {transcode_slug}.{ext}",
    extra_sessions: int = 0,
) -> None:
    """Seed a job + (parked) session_application + a session referencing presets/tracks.

    `extra_sessions` adds N additional sessions/applications all parked on the
    same job (for the multi-fan-out case). They share rip/transcode presets
    and the same template.
    """
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["jobs"] = [
        Job(
            id="job_01JZXR7K3M5Q8N4VWA00000001",
            drive_id="drv_x",
            disc_type=DiscType.DVD,
            title=job_title,
            year=None,
            status=job_status,
            metadata_json={},
            resumed_from_crash=False,
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
    sessions = [
        Session(
            id="ses_x",
            name="My Plex",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_x",
            transcode_preset_id="tpr_x",
            output_path_template=template,
        )
    ]
    apps = [
        SessionApplication(
            id="sap_x",
            session_id="ses_x",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            status=SessionApplicationStatus.WAITING_IDENTIFY,
            overwrite=False,
        )
    ]
    for i in range(extra_sessions):
        sessions.append(
            Session(
                id=f"ses_extra_{i}",
                name=f"Extra {i}",
                media_type=MediaType.MOVIE,
                is_builtin=False,
                rip_preset_id="rpr_x",
                transcode_preset_id="tpr_x",
                output_path_template=f"{template}.copy{i}",
            )
        )
        apps.append(
            SessionApplication(
                id=f"sap_extra_{i}",
                session_id=f"ses_extra_{i}",
                job_id="job_01JZXR7K3M5Q8N4VWA00000001",
                status=SessionApplicationStatus.WAITING_IDENTIFY,
                overwrite=False,
            )
        )
    db.rows["sessions"] = sessions
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
    db.rows["session_applications"] = apps
    db.rows["drives"] = []


class _CapturingHub:
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
    hub: _CapturingHub,
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


def test_resolve_promotes_waiting_identify_to_queued(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    hub = _CapturingHub()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp_path, hub)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/resolve",
            json={"title": "Iron Man", "year": 2008},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job"]["status"] == "identified"
    assert body["job"]["title"] == "Iron Man"

    assert len(body["fan_out"]) == 1
    out = body["fan_out"][0]
    assert out["session_application_id"] == "sap_x"
    assert out["session_id"] == "ses_x"
    assert out["status"] == "queued"
    assert out["task_count"] == 1
    assert out["skipped_reason"] is None
    assert out["error_detail"] is None

    # Application row was promoted in place (same id, status flipped).
    app_row = next(a for a in db.rows["session_applications"] if a.id == "sap_x")
    assert app_row.status == SessionApplicationStatus.QUEUED

    # Task fanned out at the expected path.
    tasks = [t for t in db.rows["transcode_tasks"] if t.session_application_id == "sap_x"]
    assert len(tasks) == 1
    assert tasks[0].output_path == "Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv"
    assert tasks[0].status == TranscodeTaskStatus.QUEUED

    types = [e["event_type"] for e in hub.events]
    assert "identify.resolved" in types
    assert "rip.identify_resolved" in types
    queued_events = [e for e in hub.events if e["event_type"] == "session.queued"]
    assert len(queued_events) == 1
    assert queued_events[0]["payload"]["source"] == "manual"


def test_resolve_fans_out_multiple_waiting_identify_applications(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    hub = _CapturingHub()
    _seed(db, extra_sessions=2)
    app, token = _make_app(signing_key, db, tmp_path, hub)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/resolve",
            json={"title": "Iron Man", "year": 2008},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["fan_out"]) == 3
    assert all(o["status"] == "queued" for o in body["fan_out"])
    assert all(o["skipped_reason"] is None for o in body["fan_out"])
    # 3 session.queued events (one per promoted application).
    queued_events = [e for e in hub.events if e["event_type"] == "session.queued"]
    assert len(queued_events) == 3
    # Three TranscodeTask rows total (one per application; each session has 1 track).
    assert len(db.rows["transcode_tasks"]) == 3


def test_resolve_ripped_awaiting_identify_status_fans_out(signing_key: bytes, tmp_path: Path) -> None:
    """Fan-out isn't gated on AWAITING_USER_ID specifically — a ripped
    placeholder drains the same way, promoting to RIPPED (its rip is done;
    G-09) rather than IDENTIFIED."""
    db = FakeSession()
    hub = _CapturingHub()
    _seed(db, job_status=JobStatus.RIPPED_AWAITING_IDENTIFY)
    app, token = _make_app(signing_key, db, tmp_path, hub)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/resolve",
            json={"title": "Iron Man", "year": 2008},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job"]["status"] == "ripped"
    assert len(body["fan_out"]) == 1
    assert body["fan_out"][0]["status"] == "queued"


def test_resolve_fan_out_template_error_returns_outcome_not_500(signing_key: bytes, tmp_path: Path) -> None:
    """A parked session whose template references a token that resolves to
    empty against the resolved metadata (e.g. `{album}` on a movie) should
    surface as a per-application `skipped_reason='template'` outcome — NOT
    raise a 500. Identify itself still succeeds."""
    db = FakeSession()
    hub = _CapturingHub()
    _seed(db, template="{album}/{title}.mkv")
    app, token = _make_app(signing_key, db, tmp_path, hub)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/resolve",
            json={"title": "Iron Man", "year": 2008},  # no album in metadata
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job"]["status"] == "identified"
    assert len(body["fan_out"]) == 1
    out = body["fan_out"][0]
    assert out["status"] == "waiting_identify"
    assert out["task_count"] == 0
    assert out["skipped_reason"] == "template"
    assert out["error_detail"] is not None
    assert "album" in out["error_detail"]

    # Application stays parked in DB.
    app_row = next(a for a in db.rows["session_applications"] if a.id == "sap_x")
    assert app_row.status == SessionApplicationStatus.WAITING_IDENTIFY
    assert db.rows["transcode_tasks"] == []


def test_resolve_fan_out_collision_returns_outcome_not_409(signing_key: bytes, tmp_path: Path) -> None:
    """A pre-existing DONE TranscodeTask at the would-be output path is a
    collision — the parked application stays in waiting_identify, the
    response surfaces `skipped_reason='collisions'`, no exception."""
    db = FakeSession()
    hub = _CapturingHub()
    _seed(db)
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="tsk_existing",
            session_application_id="sap_other",
            source_track_id="trk_other",
            status=TranscodeTaskStatus.DONE,
            output_path="Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv",
            attempts=1,
            progress_pct=100,
        )
    ]
    app, token = _make_app(signing_key, db, tmp_path, hub)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/resolve",
            json={"title": "Iron Man", "year": 2008},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job"]["status"] == "identified"
    assert len(body["fan_out"]) == 1
    out = body["fan_out"][0]
    assert out["status"] == "waiting_identify"
    assert out["skipped_reason"] == "collisions"
    assert "collision" in (out["error_detail"] or "")
    # No new task was created (the existing collision row is still the only one).
    assert len(db.rows["transcode_tasks"]) == 1


def test_resolve_partial_fan_out_mixed_success_and_failure(signing_key: bytes, tmp_path: Path) -> None:
    """Two parked applications — one with a clean template, one referencing
    a token that will resolve empty. Identify succeeds; the clean one is
    promoted with tasks; the broken one stays parked with skipped_reason."""
    db = FakeSession()
    hub = _CapturingHub()
    _seed(db)
    # Add a second session with a broken template, parked on the same job.
    db.rows["sessions"].append(
        Session(
            id="ses_bad",
            name="Bad",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_x",
            transcode_preset_id="tpr_x",
            output_path_template="{album}/{title}.mkv",
        )
    )
    db.rows["session_applications"].append(
        SessionApplication(
            id="sap_bad",
            session_id="ses_bad",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            status=SessionApplicationStatus.WAITING_IDENTIFY,
            overwrite=False,
        )
    )
    app, token = _make_app(signing_key, db, tmp_path, hub)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/resolve",
            json={"title": "Iron Man", "year": 2008},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job"]["status"] == "identified"
    assert len(body["fan_out"]) == 2
    by_id = {o["session_application_id"]: o for o in body["fan_out"]}
    assert by_id["sap_x"]["status"] == "queued"
    assert by_id["sap_x"]["task_count"] == 1
    assert by_id["sap_x"]["skipped_reason"] is None
    assert by_id["sap_bad"]["status"] == "waiting_identify"
    assert by_id["sap_bad"]["skipped_reason"] == "template"

    # Only one session.queued event (for the successful application).
    queued_events = [e for e in hub.events if e["event_type"] == "session.queued"]
    assert len(queued_events) == 1
    assert queued_events[0]["payload"]["session_application_id"] == "sap_x"


def test_resolve_fan_out_session_missing_returns_outcome(signing_key: bytes, tmp_path: Path) -> None:
    """A parked application whose Session row was deleted out from under it
    surfaces as `skipped_reason='session_missing'` rather than raising."""
    db = FakeSession()
    hub = _CapturingHub()
    _seed(db)
    # Drop the session out from under the parked application.
    db.rows["sessions"] = []
    app, token = _make_app(signing_key, db, tmp_path, hub)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/resolve",
            json={"title": "Iron Man", "year": 2008},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job"]["status"] == "identified"
    assert len(body["fan_out"]) == 1
    out = body["fan_out"][0]
    assert out["skipped_reason"] == "session_missing"
    assert "ses_x" in (out["error_detail"] or "")


def test_resolve_media_mismatch_keeps_application_parked(signing_key: bytes, tmp_path: Path) -> None:
    """G-04: resolve sets `job.media_type` from the identify call, then
    drains parked applications. A session applied before identity was known
    (e.g. a movie session routed to what turns out to be a music CD) must
    stay parked with `skipped_reason='media_mismatch'` instead of fanning
    out a movie transcode against a music job."""
    db = FakeSession()
    hub = _CapturingHub()
    _seed(db)
    db.rows["sessions"][0].media_type = MediaType.MOVIE
    app, token = _make_app(signing_key, db, tmp_path, hub)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/resolve",
            json={"title": "Various Artists", "year": 2008, "media_type": "music"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job"]["media_type"] == "music"

    assert len(body["fan_out"]) == 1
    out = body["fan_out"][0]
    assert out["session_application_id"] == "sap_x"
    assert out["status"] == "waiting_identify"
    assert out["task_count"] == 0
    assert out["skipped_reason"] == "media_mismatch"
    assert out["error_detail"] is not None
    assert "movie" in out["error_detail"]
    assert "music" in out["error_detail"]

    app_row = next(a for a in db.rows["session_applications"] if a.id == "sap_x")
    assert app_row.status == SessionApplicationStatus.WAITING_IDENTIFY
    assert db.rows["transcode_tasks"] == []
    assert not any(e["event_type"] == "session.queued" for e in hub.events)


def test_resolve_fan_out_session_without_transcode_preset(signing_key: bytes, tmp_path: Path) -> None:
    """A session with `transcode_preset_id=None` (rip-only, no transcode
    pass) is a real production case — the fan-out must promote it without
    loading a transcode_preset. Covers the `transcode_preset_id is None`
    branch in `fan_out_waiting_identify_applications`."""
    db = FakeSession()
    hub = _CapturingHub()
    _seed(db, template="{title} ({year})/{title}.mkv")
    # Strip transcode_preset_id from the session so the fan-out skips the lookup.
    db.rows["sessions"][0].transcode_preset_id = None
    app, token = _make_app(signing_key, db, tmp_path, hub)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/resolve",
            json={"title": "Iron Man", "year": 2008},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    out = body["fan_out"][0]
    assert out["status"] == "queued"
    assert out["task_count"] == 1
    assert out["skipped_reason"] is None


def test_resolve_fan_out_transcode_preset_missing_returns_outcome(signing_key: bytes, tmp_path: Path) -> None:
    """A parked application whose transcode_preset was deleted out from
    under it surfaces as `skipped_reason='session_missing'`."""
    db = FakeSession()
    hub = _CapturingHub()
    _seed(db)
    db.rows["transcode_presets"] = []
    app, token = _make_app(signing_key, db, tmp_path, hub)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/resolve",
            json={"title": "Iron Man", "year": 2008},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    out = body["fan_out"][0]
    assert out["skipped_reason"] == "session_missing"
    assert "tpr_x" in (out["error_detail"] or "")


def test_resolve_before_rip_keeps_application_parked(signing_key: bytes, tmp_path: Path) -> None:
    """Resolve on a job whose rip has not started yet.

    The ripper persists Track rows at rip-start, so at this point there is
    nothing to fan out. The parked application must survive (still
    `waiting_identify`, drained later by rip-complete) instead of being
    promoted to an empty `queued` husk that never gets any tasks.
    """
    db = FakeSession()
    hub = _CapturingHub()
    _seed(db)
    db.rows["tracks"] = []
    app, token = _make_app(signing_key, db, tmp_path, hub)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/resolve",
            json={"title": "Iron Man", "year": 2008},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job"]["status"] == "identified"

    assert len(body["fan_out"]) == 1
    out = body["fan_out"][0]
    assert out["session_application_id"] == "sap_x"
    assert out["status"] == "waiting_identify"
    assert out["task_count"] == 0
    assert out["skipped_reason"] == "no_tracks"
    assert out["error_detail"] is not None and "rip" in out["error_detail"]

    app_row = next(a for a in db.rows["session_applications"] if a.id == "sap_x")
    assert app_row.status == SessionApplicationStatus.WAITING_IDENTIFY
    assert db.rows["transcode_tasks"] == []
    assert not any(e["event_type"] == "session.queued" for e in hub.events)


def test_resolve_commits_identity_before_after_rip_drain_raises(
    signing_key: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix 75-2 regression: a drain exception inside after_rip must not
    destroy the operator's resolve.

    `drain_parked_applications_after_rip` wraps `fan_out_waiting_identify_applications`
    in try/except and calls `db.rollback()` on any exception. Before the fix,
    resolve ran the job identity mutations (title/status) and after_rip in
    the same uncommitted transaction, so that rollback would discard the
    resolve too -- yet the endpoint still returned 200 built from the
    in-Python (but no-longer-durable) job object. Forcing the drain to raise
    here and asserting the resolve committed BEFORE the drain ran (and that
    the response reflects the resolved title) pins the fix.
    """
    db = FakeSession()
    hub = _CapturingHub()
    _seed(db, job_status=JobStatus.RIPPED_AWAITING_IDENTIFY)
    db.rows["jobs"][0].metadata_json = {"unidentified": True}
    app, token = _make_app(signing_key, db, tmp_path, hub)

    commits_before_drain: list[int] = []

    async def _raising_fan_out(*args: object, **kwargs: object) -> None:
        # Record how many commits had already landed by the time the drain
        # ran, then blow up -- exactly what drain_parked_applications_after_rip
        # catches and rolls back from.
        commits_before_drain.append(db.committed)
        raise RuntimeError("boom: simulated drain failure")

    monkeypatch.setattr(
        "arm_backend.auto_session.fan_out_waiting_identify_applications",
        _raising_fan_out,
    )

    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/resolve",
            json={"title": "Iron Man", "year": 2008},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    # The resolve landed: RIPPED_AWAITING_IDENTIFY -> RIPPED, title applied.
    assert body["job"]["status"] == "ripped"
    assert body["job"]["title"] == "Iron Man"
    # The drain found at least one commit already on the books before it ran
    # (the resolve's own commit) -- pre-fix, this would be 0.
    assert commits_before_drain == [1]
    # The fan-out itself failed and stayed parked; no outcome promoted.
    assert body["fan_out"] == []

    job_row = db.rows["jobs"][0]
    assert job_row.status == JobStatus.RIPPED
    assert job_row.title == "Iron Man"


def test_resolve_ripped_placeholder_promotes_to_ripped_and_runs_after_rip(signing_key: bytes, tmp_path: Path) -> None:
    """G-09: resolving a ripped_awaiting_identify placeholder promotes it to
    RIPPED (its rip is done — IDENTIFIED would claim otherwise), clears the
    spent `unidentified` flag, and runs the same post-rip pass rip-complete
    runs: the parked application fans out against the just-resolved title."""
    db = FakeSession()
    hub = _CapturingHub()
    _seed(db, job_status=JobStatus.RIPPED_AWAITING_IDENTIFY)
    db.rows["jobs"][0].metadata_json = {"unidentified": True}
    app, token = _make_app(signing_key, db, tmp_path, hub)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/resolve",
            json={"title": "Iron Man", "year": 2008},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job"]["status"] == "ripped"
    assert body["job"]["metadata_json"].get("unidentified") is None

    assert len(body["fan_out"]) == 1
    out = body["fan_out"][0]
    assert out["status"] == "queued"
    assert out["task_count"] == 1
    assert out["skipped_reason"] is None

    app_row = next(a for a in db.rows["session_applications"] if a.id == "sap_x")
    assert app_row.status == SessionApplicationStatus.QUEUED
    tasks = [t for t in db.rows["transcode_tasks"] if t.session_application_id == "sap_x"]
    assert len(tasks) == 1
    assert any(e["event_type"] == "session.queued" for e in hub.events)
