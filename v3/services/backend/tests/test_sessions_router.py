"""Sessions CRUD router tests via TestClient + dep-overridden fake session."""

from __future__ import annotations

import os
import secrets
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import pytest  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import sessions as sessions_router  # noqa: E402
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


@pytest.fixture
def admin_user() -> User:
    return User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)


def _movie_rip_preset(builtin: bool = True) -> RipPreset:
    return RipPreset(
        id="rpr_movie",
        name="Movie main feature",
        media_type=MediaType.MOVIE,
        is_builtin=builtin,
        track_selection=TrackSelection.MAIN_FEATURE,
        identification_mode=IdentificationMode.REQUIRED,
        output_mode=OutputMode.TRACKS,
    )


def _movie_transcode_preset() -> TranscodePreset:
    return TranscodePreset(
        id="tpr_plex",
        name="Plex 1080p H.265",
        media_type=MediaType.MOVIE,
        is_builtin=True,
        tool=TranscodeTool.HANDBRAKE,
        container=ContainerFormat.MKV,
        hw_preference=HwPreference.CPU_ONLY,
    )


def _builtin_session() -> Session:
    return Session(
        id="ses_builtin",
        name="Movie → Plex 1080p",
        media_type=MediaType.MOVIE,
        is_builtin=True,
        rip_preset_id="rpr_movie",
        transcode_preset_id="tpr_plex",
        output_path_template="{title} ({year})/{title} - {transcode_slug}.{ext}",
    )


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(sessions_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session

    user = db.rows.setdefault("users", [])
    if not user:
        user.append(User(id="usr_admin", username="admin", password_hash="x", password_must_change=False))
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _seed(db: FakeSession) -> None:
    db.rows["rip_presets"] = [_movie_rip_preset()]
    db.rows["transcode_presets"] = [_movie_transcode_preset()]
    db.rows["sessions"] = [_builtin_session()]
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_list_sessions_returns_seeded_rows(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/sessions", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["name"] == "Movie → Plex 1080p"


def test_get_session_404(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/sessions/ses_does_not_exist", headers=_auth(token))
    assert r.status_code == 404


def test_create_session_happy_path(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    body: dict[str, Any] = {
        "name": "My Plex 1080p",
        "media_type": "movie",
        "rip_preset_id": "rpr_movie",
        "transcode_preset_id": "tpr_plex",
        "output_path_template": "{title} ({year})/{title} - {transcode_slug}.{ext}",
    }
    with TestClient(app) as client:
        r = client.post("/api/sessions", json=body, headers=_auth(token))
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["name"] == "My Plex 1080p"
    assert out["is_builtin"] is False
    assert out["created_by_user_id"] == "usr_admin"


def test_create_session_rejects_template_with_unknown_token(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    body = {
        "name": "Bad",
        "media_type": "movie",
        "rip_preset_id": "rpr_movie",
        "output_path_template": "{nope}.mkv",
    }
    with TestClient(app) as client:
        r = client.post("/api/sessions", json=body, headers=_auth(token))
    assert r.status_code == 422


def test_create_session_rejects_media_type_mismatch(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    body = {
        "name": "Mismatch",
        "media_type": "tv",
        "rip_preset_id": "rpr_movie",
        "output_path_template": "{show}/{track}.{ext}",
    }
    with TestClient(app) as client:
        r = client.post("/api/sessions", json=body, headers=_auth(token))
    assert r.status_code == 400


def test_patch_builtin_only_name_allowed(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/sessions/ses_builtin",
            json={"name": "Renamed"},
            headers=_auth(token),
        )
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"


def test_patch_builtin_other_field_409(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/sessions/ses_builtin",
            json={"output_path_template": "{title}.{ext}"},
            headers=_auth(token),
        )
    assert r.status_code == 409


def test_delete_builtin_409(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.delete("/api/sessions/ses_builtin", headers=_auth(token))
    assert r.status_code == 409


def test_delete_session_referenced_by_drive_409(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["sessions"].append(
        Session(
            id="ses_user",
            name="My session",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_movie",
            transcode_preset_id="tpr_plex",
            output_path_template="{title}.{ext}",
        )
    )
    db.rows["drives"] = [
        Drive(
            id="drv_x",
            hostname="arm-ripper-sr0",
            device_path="/dev/sr0",
            display_name="LG Drive",
            status=DriveStatus.ONLINE,
            default_session_id="ses_user",
        )
    ]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.delete("/api/sessions/ses_user", headers=_auth(token))
    assert r.status_code == 409
    assert "default" in r.json()["detail"].lower()


def test_clone_session_creates_non_builtin(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post(
            "/api/sessions/ses_builtin/clone",
            json={"name": "My Clone"},
            headers=_auth(token),
        )
    assert r.status_code == 201
    out = r.json()
    assert out["name"] == "My Clone"
    assert out["is_builtin"] is False
    assert out["created_by_user_id"] == "usr_admin"


def test_preview_template_returns_synthetic_expansion(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post(
            "/api/sessions/preview",
            json={
                "template": "{title} ({year}).{ext}",
                "media_type": "movie",
                "has_transcode_preset": True,
            },
            headers=_auth(token),
        )
    assert r.status_code == 200
    assert r.json()["expansion"] == "Iron Man (2008).mkv"


def test_preview_template_422_on_bad_token(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post(
            "/api/sessions/preview",
            json={"template": "{show}.{ext}", "media_type": "movie", "has_transcode_preset": True},
            headers=_auth(token),
        )
    assert r.status_code == 422
