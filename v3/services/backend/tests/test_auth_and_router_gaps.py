"""Residual branch coverage for auth.py (require_jwt principal failures,
drive-owner verification) and the small router gaps in auth/config/drives/
sessions that the existing per-router suites don't reach.
"""

from __future__ import annotations

import os
import secrets
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import jwt as pyjwt  # noqa: E402
from argon2 import PasswordHasher  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import (  # noqa: E402
    auth as auth_router,
    config as config_router,
    diagnostics as diagnostics_router,
    drives as drives_router,
    ripper as ripper_router,
    sessions as sessions_router,
)
from arm_common import (  # noqa: E402
    DiscType,
    Drive,
    DriveStatus,
    Job,
    JobStatus,
    MediaType,
    Session,
    TranscodePreset,
    TranscodeTool,
    User,
)
from arm_common import ContainerFormat  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402

_KEY = secrets.token_bytes(32)
_SVC = {"Authorization": "Bearer tok-service"}


def _app(db: FakeSession, *router_mods: Any, signing_key: bytes | None = _KEY) -> FastAPI:
    app = FastAPI()
    if signing_key is not None:
        app.state.signing_key = signing_key
    app.state.ws_hub = None
    app.state.dispatcher = None
    for m in router_mods:
        app.include_router(m.router)

    async def _ov() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _ov
    return app


def _jwt(**claims: Any) -> str:
    from datetime import datetime, timedelta, timezone

    payload = {"exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()), **claims}
    return pyjwt.encode(payload, _KEY, algorithm="HS256")


# --- auth.py: require_jwt principal failures ---------------------------------


def test_require_jwt_rejects_service_token_on_ui_endpoint() -> None:
    db = FakeSession()
    app = _app(db, diagnostics_router)
    with TestClient(app) as client:
        r = client.get("/api/diagnostics", headers=_SVC)
    assert r.status_code == 401
    assert "requires user JWT" in r.json()["detail"]


def test_require_jwt_500_when_signing_key_missing() -> None:
    db = FakeSession()
    app = _app(db, diagnostics_router, signing_key=None)
    token, _ = issue_access_token("u", "admin", _KEY)
    with TestClient(app) as client:
        r = client.get("/api/diagnostics", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 500
    assert "signing key not initialized" in r.json()["detail"]


def test_require_jwt_invalid_token_401() -> None:
    db = FakeSession()
    app = _app(db, diagnostics_router)
    with TestClient(app) as client:
        r = client.get("/api/diagnostics", headers={"Authorization": "Bearer a.b.c"})
    assert r.status_code == 401
    assert "invalid jwt" in r.json()["detail"]


def test_require_jwt_missing_sub_401() -> None:
    db = FakeSession()
    app = _app(db, diagnostics_router)
    with TestClient(app) as client:
        r = client.get("/api/diagnostics", headers={"Authorization": f"Bearer {_jwt(username='x')}"})
    assert r.status_code == 401
    assert "missing sub" in r.json()["detail"]


def test_require_jwt_unknown_user_401() -> None:
    db = FakeSession()
    db.rows["users"] = []
    app = _app(db, diagnostics_router)
    token, _ = issue_access_token("usr_ghost", "ghost", _KEY)
    with TestClient(app) as client:
        r = client.get("/api/diagnostics", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert "unknown user" in r.json()["detail"]


# --- auth.py: drive-owner verification ---------------------------------------


def _job(job_id: str = "job_01JZXR7K3M5Q8N4VWA00000001", drive_id: str = "drv_x") -> Job:
    return Job(
        id=job_id,
        drive_id=drive_id,
        disc_type=DiscType.DVD,
        title="X",
        year=2000,
        status=JobStatus.RIPPING,
        metadata_json={},
        resumed_from_crash=False,
    )


def test_drive_owner_missing_hostname_header_401() -> None:
    db = FakeSession()
    db.rows["jobs"] = [_job()]
    db.rows["drives"] = [Drive(id="drv_x", hostname="h", device_path="/dev/sr0", status=DriveStatus.ONLINE)]
    app = _app(db, ripper_router)
    with TestClient(app) as client:
        r = client.post("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA00000001/rip-start", headers=_SVC)  # no X-ARM-Hostname
    assert r.status_code == 401
    assert "missing X-ARM-Hostname" in r.json()["detail"]


def test_drive_owner_unknown_drive_404() -> None:
    db = FakeSession()
    db.rows["jobs"] = [_job(drive_id="drv_gone")]
    db.rows["drives"] = []
    app = _app(db, ripper_router)
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA00000001/rip-start",
            headers={**_SVC, "X-ARM-Hostname": "h"},
        )
    assert r.status_code == 404
    assert "unknown drive_id" in r.json()["detail"]


def test_drive_owner_hostname_mismatch_403() -> None:
    db = FakeSession()
    db.rows["jobs"] = [_job()]
    db.rows["drives"] = [Drive(id="drv_x", hostname="owner-host", device_path="/dev/sr0", status=DriveStatus.ONLINE)]
    app = _app(db, ripper_router)
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA00000001/rip-start",
            headers={**_SVC, "X-ARM-Hostname": "intruder-host"},
        )
    assert r.status_code == 403
    assert "does not own this drive" in r.json()["detail"]


def test_drive_owner_by_track_unknown_track_404() -> None:
    db = FakeSession()
    db.rows["tracks"] = []
    app = _app(db, ripper_router)
    with TestClient(app) as client:
        r = client.patch(
            "/api/ripper/tracks/trk_gone",
            json={"status": "in_progress"},
            headers={**_SVC, "X-ARM-Hostname": "h"},
        )
    assert r.status_code == 404
    assert "unknown track_id" in r.json()["detail"]


# --- routers/auth.py: rehash branch ------------------------------------------


def test_login_rehashes_legacy_hash() -> None:
    db = FakeSession()
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("hunter2")
    db.rows["users"] = [User(id="u1", username="admin", password_hash=weak, password_must_change=False)]
    app = _app(db, auth_router)
    with TestClient(app) as client:
        r = client.post("/api/auth/login", json={"username": "admin", "password": "hunter2"})
    assert r.status_code == 200
    # The stored hash was upgraded in-place to the default cost.
    assert db.rows["users"][0].password_hash != weak


# --- routers/config.py: missing singleton ------------------------------------


def test_config_get_missing_singleton_500() -> None:
    db = FakeSession()
    db.rows["config"] = []
    app = _app(db, config_router)
    token, _ = issue_access_token("u1", "admin", _KEY)
    db.rows["users"] = [User(id="u1", username="admin", password_hash="x", password_must_change=False)]
    with TestClient(app) as client:
        r = client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 500
    assert "config singleton missing" in r.json()["detail"]


def test_config_patch_missing_singleton_500() -> None:
    db = FakeSession()
    db.rows["config"] = []
    db.rows["users"] = [User(id="u1", username="admin", password_hash="x", password_must_change=False)]
    app = _app(db, config_router)
    token, _ = issue_access_token("u1", "admin", _KEY)
    with TestClient(app) as client:
        r = client.patch("/api/config", json={"block_on_miss": True}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 500


# --- routers/drives.py: list ------------------------------------------------


def test_list_drives() -> None:
    db = FakeSession()
    db.rows["users"] = [User(id="u1", username="admin", password_hash="x", password_must_change=False)]
    db.rows["drives"] = [
        Drive(id="drv_1", hostname="a", device_path="/dev/sr0", status=DriveStatus.ONLINE),
        Drive(id="drv_2", hostname="b", device_path="/dev/sr1", status=DriveStatus.OFFLINE),
    ]
    app = _app(db, drives_router)
    token, _ = issue_access_token("u1", "admin", _KEY)
    with TestClient(app) as client:
        r = client.get("/api/drives", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert {d["id"] for d in r.json()} == {"drv_1", "drv_2"}


# --- routers/sessions.py: patch branches ------------------------------------


def test_patch_session_transcode_media_mismatch_400() -> None:
    """Patch only transcode_preset_id (rip_preset_id absent → 139->146) with a
    mismatched-media transcode preset → 400 (line 152)."""
    db = FakeSession()
    db.rows["users"] = [User(id="u1", username="admin", password_hash="x", password_must_change=False)]
    db.rows["sessions"] = [
        Session(
            id="ses_x",
            name="S",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_x",
            transcode_preset_id=None,
            output_path_template="{title}.{ext}",
        )
    ]
    db.rows["transcode_presets"] = [
        TranscodePreset(
            id="tpr_tv",
            name="tv preset",
            media_type=MediaType.TV,
            is_builtin=True,
            tool=TranscodeTool.HANDBRAKE,
            container=ContainerFormat.MKV,
        )
    ]
    app = _app(db, sessions_router)
    token, _ = issue_access_token("u1", "admin", _KEY)
    with TestClient(app) as client:
        r = client.patch(
            "/api/sessions/ses_x",
            json={"transcode_preset_id": "tpr_tv"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert r.status_code == 400
    assert "transcode_preset.media_type=tv" in r.json()["detail"]
