"""Drives router: GET list + PATCH default_session_id / display_name (Phase 8)."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import drives as drives_router  # noqa: E402
from arm_common import (  # noqa: E402
    ContainerFormat,
    DiscType,
    Drive,
    DriveMode,
    DriveStatus,
    HwPreference,
    IdentificationMode,
    Job,
    JobStatus,
    MediaType,
    OutputMode,
    RipPreset,
    Session,
    TrackSelection,
    TranscodePreset,
    TranscodeTool,
    User,
)

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession) -> None:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["drives"] = [
        Drive(
            id="drv_x",
            hostname="ripper-host",
            device_path="/dev/sr0",
            display_name=None,
            status=DriveStatus.ONLINE,
            default_session_id=None,
        )
    ]
    db.rows["rip_presets"] = [
        RipPreset(
            id="rpr_movie",
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
            id="tpr_plex",
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
            rip_preset_id="rpr_movie",
            transcode_preset_id="tpr_plex",
            output_path_template="{title} ({year})/{title}.mkv",
        )
    ]


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(drives_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_patch_display_name_only(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/drives/drv_x",
            json={"display_name": "Living-room ripper"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    assert r.json()["display_name"] == "Living-room ripper"
    assert r.json()["default_session_id"] is None


def test_patch_default_session_id_to_valid(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/drives/drv_x",
            json={"default_session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    assert r.json()["default_session_id"] == "ses_x"


def test_patch_default_session_id_to_null_clears(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["drives"][0].default_session_id = "ses_x"
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/drives/drv_x",
            json={"default_session_id": None},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    assert r.json()["default_session_id"] is None


def test_patch_default_session_id_to_unknown_returns_400(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/drives/drv_x",
            json={"default_session_id": "ses_does_not_exist"},
            headers=_auth(token),
        )
    assert r.status_code == 400


def test_patch_unknown_drive_returns_404(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/drives/drv_missing",
            json={"display_name": "x"},
            headers=_auth(token),
        )
    assert r.status_code == 404


def test_patch_unauthenticated_returns_401(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, _token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/drives/drv_x", json={"display_name": "x"})
    assert r.status_code == 401


def test_delete_drive_ok(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows.setdefault("drives", []).append(Drive(id="drv_1", device_path="/dev/sr0", hostname="h1"))
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.delete("/api/drives/drv_1", headers=_auth(token))
    assert r.status_code == 204
    assert db.rows["drives"] == []


def test_delete_drive_404(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.delete("/api/drives/drv_x", headers=_auth(token))
    assert r.status_code == 404


def test_delete_drive_with_active_job_409(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows.setdefault("drives", []).append(Drive(id="drv_1", device_path="/dev/sr0", hostname="h1"))
    db.rows.setdefault("jobs", []).append(
        Job(id="job_1", drive_id="drv_1", status=JobStatus.RIPPING, disc_type=DiscType.DVD)
    )
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.delete("/api/drives/drv_1", headers=_auth(token))
    assert r.status_code == 409
    assert db.rows["drives"]  # not deleted


def test_delete_drive_with_non_ripping_job_succeeds(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )
    db.rows.setdefault("drives", []).append(Drive(id="drv_1", device_path="/dev/sr0", hostname="h1"))
    # a RIPPED (terminal) job on the drive must NOT block deletion — only RIPPING does
    db.rows.setdefault("jobs", []).append(
        Job(id="job_1", drive_id="drv_1", status=JobStatus.RIPPED, disc_type=DiscType.DVD)
    )
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.delete("/api/drives/drv_1", headers=_auth(token))
    assert r.status_code == 204, r.text
    assert db.rows["drives"] == []


def _job(job_id: str, *, drive_id: str = "drv_x", status: JobStatus, title: str | None = "T", created: int = 0) -> Job:
    return Job(
        id=job_id,
        drive_id=drive_id,
        disc_type=DiscType.DVD,
        status=status,
        title=title,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=created),
    )


def test_list_returns_driveview_with_null_tuning(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/drives", headers=_auth(token))
    assert r.status_code == 200, r.text
    row = r.json()[0]
    for f in ("rip_speed", "drive_mode", "uhd_capable", "prescan_cache_mb",
              "prescan_timeout", "prescan_retries", "disc_enum_timeout"):
        assert row[f] is None
    assert row["current_job"] is None
    assert "rip_params_json" not in row


def test_current_job_is_active_job(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["jobs"] = [_job("job_a", status=JobStatus.RIPPING, title="Iron Man")]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/drives", headers=_auth(token))
    row = next(d for d in r.json() if d["id"] == "drv_x")
    assert row["current_job"] == {"id": "job_a", "title": "Iron Man", "status": "ripping"}


def test_current_job_none_when_only_terminal(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["jobs"] = [
        _job("job_done", status=JobStatus.RIPPED),
        _job("job_fail", status=JobStatus.FAILED),
    ]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/drives", headers=_auth(token))
    row = next(d for d in r.json() if d["id"] == "drv_x")
    assert row["current_job"] is None


def test_current_job_picks_most_recent_active(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["jobs"] = [
        _job("job_old", status=JobStatus.IDENTIFIED, created=0),
        _job("job_new", status=JobStatus.RIPPING, created=100),
    ]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/drives", headers=_auth(token))
    row = next(d for d in r.json() if d["id"] == "drv_x")
    assert row["current_job"]["id"] == "job_new"


def test_current_job_grouped_per_drive_no_crossleak(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["drives"].append(
        Drive(id="drv_y", hostname="host-2", device_path="/dev/sr1", status=DriveStatus.ONLINE)
    )
    db.rows["jobs"] = [_job("job_x", drive_id="drv_x", status=JobStatus.RIPPING)]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/drives", headers=_auth(token))
    by_id = {d["id"]: d for d in r.json()}
    assert by_id["drv_x"]["current_job"]["id"] == "job_x"
    assert by_id["drv_y"]["current_job"] is None


def test_patch_tuning_fields_persisted(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    body = {
        "rip_speed": 8,
        "drive_mode": "manual",
        "uhd_capable": True,
        "prescan_cache_mb": 1024,
        "prescan_timeout": 30,
        "prescan_retries": 3,
        "disc_enum_timeout": 60,
    }
    with TestClient(app) as c:
        r = c.patch("/api/drives/drv_x", json=body, headers=_auth(token))
    assert r.status_code == 200, r.text
    row = r.json()
    for k, v in body.items():
        assert row[k] == v
    assert db.rows["drives"][0].rip_speed == 8
    assert db.rows["drives"][0].drive_mode == DriveMode.MANUAL


def test_patch_invalid_drive_mode_422(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.patch("/api/drives/drv_x", json={"drive_mode": "bogus"}, headers=_auth(token))
    assert r.status_code == 422


def test_patch_partial_leaves_others_untouched(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["drives"][0].drive_mode = DriveMode.AUTO
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.patch("/api/drives/drv_x", json={"rip_speed": 4}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["rip_speed"] == 4
    assert r.json()["drive_mode"] == "auto"


def test_patch_explicit_null_clears_tuning(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["drives"][0].rip_speed = 9
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.patch("/api/drives/drv_x", json={"rip_speed": None}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["rip_speed"] is None


def test_patch_unknown_tuning_field_422(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.patch("/api/drives/drv_x", json={"bogus_field": 1}, headers=_auth(token))
    assert r.status_code == 422
