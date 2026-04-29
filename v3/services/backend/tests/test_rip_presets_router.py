"""Rip-presets CRUD focusing on `track_filters_json` validation."""

from __future__ import annotations

import os
import secrets

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import pytest  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import rip_presets as rip_presets_router  # noqa: E402
from arm_common import (  # noqa: E402
    IdentificationMode,
    MediaType,
    OutputMode,
    RipPreset,
    Session,
    TrackSelection,
    User,
)

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(rip_presets_router.router)

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


def test_create_custom_preset_requires_filters(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    body = {
        "name": "Custom selection",
        "media_type": "movie",
        "track_selection": "custom",
        "identification_mode": "required",
        "output_mode": "tracks",
    }
    with TestClient(app) as client:
        r = client.post("/api/rip-presets", json=body, headers=_auth(token))
    assert r.status_code == 422
    assert "track_filters_json is required" in r.json()["detail"]


def test_create_non_custom_preset_rejects_filters(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    body = {
        "name": "Main feature",
        "media_type": "movie",
        "track_selection": "main_feature",
        "identification_mode": "required",
        "output_mode": "tracks",
        "track_filters_json": {"min_duration_seconds": 60},
    }
    with TestClient(app) as client:
        r = client.post("/api/rip-presets", json=body, headers=_auth(token))
    assert r.status_code == 422
    assert "only allowed when track_selection=custom" in r.json()["detail"]


def test_create_custom_preset_with_valid_filters(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    body = {
        "name": "Indices 1+3",
        "media_type": "movie",
        "track_selection": "custom",
        "identification_mode": "required",
        "output_mode": "tracks",
        "track_filters_json": {"title_indices": [1, 3]},
    }
    with TestClient(app) as client:
        r = client.post("/api/rip-presets", json=body, headers=_auth(token))
    assert r.status_code == 201
    out = r.json()
    assert out["track_filters_json"] == {"title_indices": [1, 3]}
    assert out["is_builtin"] is False


def test_delete_referenced_preset_409(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    rp = RipPreset(
        id="rpr_x",
        name="x",
        media_type=MediaType.MOVIE,
        is_builtin=False,
        track_selection=TrackSelection.MAIN_FEATURE,
        identification_mode=IdentificationMode.REQUIRED,
        output_mode=OutputMode.TRACKS,
    )
    db.rows["rip_presets"] = [rp]
    db.rows["sessions"] = [
        Session(
            id="ses_y",
            name="referrer",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_x",
            output_path_template="{title}.{ext}",
        )
    ]
    with TestClient(app) as client:
        r = client.delete("/api/rip-presets/rpr_x", headers=_auth(token))
    assert r.status_code == 409
    assert "session" in r.json()["detail"].lower()


def test_delete_builtin_preset_409(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["rip_presets"] = [
        RipPreset(
            id="rpr_builtin",
            name="builtin",
            media_type=MediaType.MOVIE,
            is_builtin=True,
            track_selection=TrackSelection.MAIN_FEATURE,
            identification_mode=IdentificationMode.REQUIRED,
            output_mode=OutputMode.TRACKS,
        )
    ]
    with TestClient(app) as client:
        r = client.delete("/api/rip-presets/rpr_builtin", headers=_auth(token))
    assert r.status_code == 409


def test_filter_list_by_media_type(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["rip_presets"] = [
        RipPreset(
            id="rpr_movie",
            name="movie",
            media_type=MediaType.MOVIE,
            is_builtin=True,
            track_selection=TrackSelection.MAIN_FEATURE,
            identification_mode=IdentificationMode.REQUIRED,
            output_mode=OutputMode.TRACKS,
        ),
        RipPreset(
            id="rpr_tv",
            name="tv",
            media_type=MediaType.TV,
            is_builtin=True,
            track_selection=TrackSelection.ALL_TRACKS,
            identification_mode=IdentificationMode.REQUIRED,
            output_mode=OutputMode.TRACKS,
        ),
    ]
    with TestClient(app) as client:
        r = client.get("/api/rip-presets?media_type=movie", headers=_auth(token))
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["media_type"] == "movie"
