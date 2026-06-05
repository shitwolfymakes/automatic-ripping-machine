"""Drives router: GET list + PATCH default_session_id / display_name (Phase 8)."""

from __future__ import annotations

import os
import secrets

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
    Drive,
    DriveStatus,
    HwPreference,
    IdentificationMode,
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
