"""Sessions CRUD router tests via TestClient + dep-overridden fake session."""

from __future__ import annotations

import secrets
from typing import Any


from fastapi import FastAPI
from fastapi.testclient import TestClient

import pytest

from arm_backend.db import get_session
from arm_backend.jwt_utils import issue_access_token
from arm_backend.routers import sessions as sessions_router
from arm_common import (
    ContainerFormat,
    Drive,
    DriveStatus,
    IdentificationMode,
    MediaType,
    OutputMode,
    RipPreset,
    Session,
    SessionApplication,
    TrackSelection,
    TranscodePreset,
    TranscodeTool,
    User,
)
from arm_common.enums import MusicCoverMaxSize, MusicCoverSize
from arm_common.models.user import GUEST_ROLE

from tests._fakes import FakeSession


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
        encoder="preset",
    )


def _tv_rip_preset() -> RipPreset:
    return RipPreset(
        id="rpr_tv",
        name="TV all titles",
        media_type=MediaType.TV,
        is_builtin=True,
        track_selection=TrackSelection.ALL_TRACKS,
        identification_mode=IdentificationMode.REQUIRED,
        output_mode=OutputMode.TRACKS,
    )


def _tv_transcode_preset() -> TranscodePreset:
    return TranscodePreset(
        id="tpr_tv",
        name="Plex 720p H.265",
        media_type=MediaType.TV,
        is_builtin=True,
        tool=TranscodeTool.HANDBRAKE,
        container=ContainerFormat.MKV,
        encoder="preset",
    )


def _builtin_session() -> Session:
    return Session(
        id="ses_builtin",
        name="Movie to Plex 1080p",
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
    db.rows["users"] = [
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False),
        User(
            id="usr_guest",
            username="guest",
            password_hash="x",
            password_must_change=False,
            role=GUEST_ROLE,
            disabled=False,
        ),
    ]


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
    assert body[0]["name"] == "Movie to Plex 1080p"


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


def test_patch_builtin_name_409(signing_key: bytes) -> None:
    # The seeder re-syncs a built-in's name on every boot, so a rename would
    # silently revert; the router refuses it instead.
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/sessions/ses_builtin",
            json={"name": "Renamed"},
            headers=_auth(token),
        )
    assert r.status_code == 409
    assert "read-only" in r.json()["detail"]
    assert next(s for s in db.rows["sessions"] if s.id == "ses_builtin").name != "Renamed"


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


def test_delete_session_with_applications_409(signing_key: bytes) -> None:
    # session_applications.session_id is ON DELETE RESTRICT, so a session
    # that was ever applied must be refused with a 409, not left to 500.
    db = FakeSession()
    _seed(db)
    db.rows["sessions"].append(
        Session(
            id="ses_user",
            name="Used session",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_movie",
            transcode_preset_id="tpr_plex",
            output_path_template="{title}.{ext}",
        )
    )
    db.rows["session_applications"] = [
        SessionApplication(id="sap_1", session_id="ses_user", job_id="job_a", overwrite=False),
        SessionApplication(id="sap_2", session_id="ses_user", job_id="job_a", overwrite=True),
        SessionApplication(id="sap_3", session_id="ses_user", job_id="job_b", overwrite=False),
        SessionApplication(id="sap_4", session_id="ses_other", job_id="job_c", overwrite=False),
    ]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.delete("/api/sessions/ses_user", headers=_auth(token))
    assert r.status_code == 409
    assert "2 job(s)" in r.json()["detail"]
    assert any(s.id == "ses_user" for s in db.rows["sessions"])


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
    assert r.json()["expansion_without_optional"] is None


def test_preview_template_returns_expansion_without_optional(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post(
            "/api/sessions/preview",
            json={"template": "{title} ({year?}).{ext}", "media_type": "movie", "has_transcode_preset": True},
            headers=_auth(token),
        )
    assert r.status_code == 200
    assert r.json() == {"expansion": "Iron Man (2008).mkv", "expansion_without_optional": "Iron Man.mkv"}


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


def test_get_session_happy_path(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/sessions/ses_builtin", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "ses_builtin"
    assert body["name"] == "Movie to Plex 1080p"
    assert body["is_builtin"] is True
    assert body["rip_preset_id"] == "rpr_movie"
    assert body["transcode_preset_id"] == "tpr_plex"


def test_list_sessions_requires_auth(signing_key: bytes) -> None:
    """No Authorization header falls back to the guest account (read-only route)."""
    db = FakeSession()
    _seed(db)
    app, _token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/sessions")  # no Authorization header
    assert r.status_code == 200


def test_create_rejects_unknown_rip_preset(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    body = {
        "name": "Bogus rip preset",
        "media_type": "movie",
        "rip_preset_id": "rpr_does_not_exist",
        "transcode_preset_id": "tpr_plex",
        "output_path_template": "{title} ({year}).{ext}",
    }
    with TestClient(app) as client:
        r = client.post("/api/sessions", json=body, headers=_auth(token))
    assert r.status_code == 400
    assert "unknown rip_preset_id" in r.json()["detail"]


def test_create_rejects_unknown_transcode_preset(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    body = {
        "name": "Bogus transcode preset",
        "media_type": "movie",
        "rip_preset_id": "rpr_movie",
        "transcode_preset_id": "tpr_does_not_exist",
        "output_path_template": "{title} ({year}).{ext}",
    }
    with TestClient(app) as client:
        r = client.post("/api/sessions", json=body, headers=_auth(token))
    assert r.status_code == 400
    assert "unknown transcode_preset_id" in r.json()["detail"]


def test_create_accepts_a_tv_transcode_preset_on_a_movie_session(signing_key: bytes) -> None:
    """Encoding settings do not depend on movie vs TV: a preset of either fits a session of either."""
    db = FakeSession()
    _seed(db)
    db.rows["transcode_presets"].append(_tv_transcode_preset())
    app, token = _make_app(signing_key, db)
    body = {
        "name": "Movie session w/ TV transcode",
        "media_type": "movie",
        "rip_preset_id": "rpr_movie",
        "transcode_preset_id": "tpr_tv",
        "output_path_template": "{title} ({year}).{ext}",
    }
    with TestClient(app) as client:
        r = client.post("/api/sessions", json=body, headers=_auth(token))
    assert r.status_code == 201, r.text
    assert r.json()["transcode_preset_id"] == "tpr_tv"


def test_create_rejects_a_music_transcode_preset_on_a_movie_session(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["transcode_presets"].append(
        TranscodePreset(
            id="tpr_flac",
            name="FLAC",
            media_type=MediaType.MUSIC,
            is_builtin=True,
            tool=TranscodeTool.ABCDE,
            container=ContainerFormat.FLAC,
            encoder="preset",
        )
    )
    app, token = _make_app(signing_key, db)
    body = {
        "name": "Movie session w/ FLAC",
        "media_type": "movie",
        "rip_preset_id": "rpr_movie",
        "transcode_preset_id": "tpr_flac",
        "output_path_template": "{title} ({year}).{ext}",
    }
    with TestClient(app) as client:
        r = client.post("/api/sessions", json=body, headers=_auth(token))
    assert r.status_code == 400
    assert "transcode_preset.media_type=music" in r.json()["detail"]


def test_patch_accepts_a_tv_transcode_preset_on_a_movie_session(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["transcode_presets"].append(_tv_transcode_preset())
    db.rows["sessions"].append(
        Session(
            id="ses_movie_user",
            name="Mine",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_movie",
            transcode_preset_id=None,
            output_path_template="{title} ({year}).mkv",
        )
    )
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/sessions/ses_movie_user", json={"transcode_preset_id": "tpr_tv"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["transcode_preset_id"] == "tpr_tv"


def test_create_without_transcode_preset(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    body = {
        "name": "Rip-only movie",
        "media_type": "movie",
        "rip_preset_id": "rpr_movie",
        # transcode_preset_id omitted → None
        "output_path_template": "{title} ({year})/{track}",
    }
    with TestClient(app) as client:
        r = client.post("/api/sessions", json=body, headers=_auth(token))
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["transcode_preset_id"] is None
    assert out["is_builtin"] is False


def test_patch_non_builtin_updates_all_fields(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["sessions"].append(
        Session(
            id="ses_user",
            name="Original",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_movie",
            transcode_preset_id="tpr_plex",
            output_path_template="{title}.{ext}",
            overrides_json=None,
        )
    )
    app, token = _make_app(signing_key, db)
    body = {
        "name": "Renamed",
        "output_path_template": "{title} ({year}).{ext}",
        "overrides_json": {"crf": 22},
    }
    with TestClient(app) as client:
        r = client.patch("/api/sessions/ses_user", json=body, headers=_auth(token))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["name"] == "Renamed"
    assert out["output_path_template"] == "{title} ({year}).{ext}"
    assert out["overrides_json"] == {"crf": 22}
    assert out["is_builtin"] is False


def test_patch_session_404(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/sessions/ses_missing",
            json={"name": "Renamed"},
            headers=_auth(token),
        )
    assert r.status_code == 404


def test_patch_template_revalidated_on_transcode_change(signing_key: bytes) -> None:
    # Drop the transcode preset while the template still references {ext} →
    # validate_template should reject because {ext} requires has_transcode_preset.
    db = FakeSession()
    _seed(db)
    db.rows["sessions"].append(
        Session(
            id="ses_user",
            name="Has transcode",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_movie",
            transcode_preset_id="tpr_plex",
            output_path_template="{title}.{ext}",
            overrides_json=None,
        )
    )
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/sessions/ses_user",
            json={"transcode_preset_id": None},
            headers=_auth(token),
        )
    assert r.status_code == 422
    assert "{ext}" in r.json()["detail"]


def test_patch_rejects_rip_preset_media_mismatch(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["rip_presets"].append(_tv_rip_preset())
    db.rows["sessions"].append(
        Session(
            id="ses_user",
            name="Movie session",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_movie",
            transcode_preset_id="tpr_plex",
            output_path_template="{title}.{ext}",
            overrides_json=None,
        )
    )
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/sessions/ses_user",
            json={"rip_preset_id": "rpr_tv"},
            headers=_auth(token),
        )
    assert r.status_code == 400
    assert "rip_preset.media_type=tv" in r.json()["detail"]


def test_delete_non_builtin_204(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["sessions"].append(
        Session(
            id="ses_user",
            name="Disposable",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_movie",
            transcode_preset_id="tpr_plex",
            output_path_template="{title}.{ext}",
            overrides_json=None,
        )
    )
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.delete("/api/sessions/ses_user", headers=_auth(token))
    assert r.status_code == 204
    assert all(s.id != "ses_user" for s in db.rows["sessions"])


def test_delete_session_404(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.delete("/api/sessions/ses_missing", headers=_auth(token))
    assert r.status_code == 404


def test_clone_session_404(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post(
            "/api/sessions/ses_missing/clone",
            json={"name": "Won't get here"},
            headers=_auth(token),
        )
    assert r.status_code == 404


def test_clone_preserves_overrides_json(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["sessions"].append(
        Session(
            id="ses_with_overrides",
            name="With overrides",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_movie",
            transcode_preset_id="tpr_plex",
            output_path_template="{title}.{ext}",
            overrides_json={"crf": 18, "preset": "veryslow"},
        )
    )
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post(
            "/api/sessions/ses_with_overrides/clone",
            json={"name": "Cloned"},
            headers=_auth(token),
        )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["overrides_json"] == {"crf": 18, "preset": "veryslow"}
    # Clone should not share the same dict object as the source — router does
    # `dict(src.overrides_json)` to defend against later mutation.
    src = next(s for s in db.rows["sessions"] if s.id == "ses_with_overrides")
    clone = next(s for s in db.rows["sessions"] if s.id == out["id"])
    assert clone.overrides_json is not src.overrides_json


# --- music file tags ---

_ALL_TAGS = [
    "artist",
    "album_artist",
    "album",
    "title",
    "track_number",
    "track_total",
    "disc_number",
    "year",
    "musicbrainz_release_id",
    "cover",
]
_MUSIC_TEMPLATE = "{artist}/{album}/{track} - {track_title}"


def _seed_music(db: FakeSession) -> None:
    _seed(db)
    db.rows["rip_presets"].append(
        RipPreset(
            id="rpr_music",
            name="Music: Standard CD",
            media_type=MediaType.MUSIC,
            is_builtin=True,
            track_selection=TrackSelection.ALL_TRACKS,
            identification_mode=IdentificationMode.REQUIRED,
            output_mode=OutputMode.TRACKS,
        )
    )
    db.rows["sessions"].append(
        Session(
            id="ses_music",
            name="My music",
            media_type=MediaType.MUSIC,
            is_builtin=False,
            rip_preset_id="rpr_music",
            output_path_template=_MUSIC_TEMPLATE,
            music_tag_fields=["artist", "title", "cover"],
        )
    )


def _create_music(client: TestClient, token: str, **extra: Any) -> Any:
    body = {
        "name": "Music, tags trimmed",
        "media_type": "music",
        "rip_preset_id": "rpr_music",
        "output_path_template": _MUSIC_TEMPLATE,
        **extra,
    }
    return client.post("/api/sessions", json=body, headers=_auth(token))


def test_create_music_session_writes_every_tag_by_default(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_music(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = _create_music(client, token)
    assert r.status_code == 201, r.text
    assert r.json()["music_tag_fields"] == _ALL_TAGS


def test_create_music_session_stores_the_chosen_tags(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_music(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = _create_music(client, token, music_tag_fields=["title", "track_number"])
    assert r.status_code == 201, r.text
    assert r.json()["music_tag_fields"] == ["title", "track_number"]
    row = next(s for s in db.rows["sessions"] if s.id == r.json()["id"])
    assert row.music_tag_fields == ["title", "track_number"]
    assert all(type(v) is str for v in row.music_tag_fields)  # plain values, not enum members


def test_create_rejects_music_tags_on_a_movie_session(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    body = {
        "name": "Movie",
        "media_type": "movie",
        "rip_preset_id": "rpr_movie",
        "output_path_template": "{title} ({year})/{title}.{ext}",
        "music_tag_fields": ["artist"],
    }
    with TestClient(app) as client:
        r = client.post("/api/sessions", json=body, headers=_auth(token))
    assert r.status_code == 400
    assert r.json()["detail"] == "music_tag_fields applies to music sessions only"
    assert len(db.rows["sessions"]) == 1


def test_update_music_session_tags(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_music(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/sessions/ses_music", json={"music_tag_fields": []}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["music_tag_fields"] == []
    assert next(s for s in db.rows["sessions"] if s.id == "ses_music").music_tag_fields == []


def test_update_stores_the_tags_as_plain_values(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_music(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/sessions/ses_music", json={"music_tag_fields": ["title", "cover"]}, headers=_auth(token))
    assert r.status_code == 200, r.text
    row = next(s for s in db.rows["sessions"] if s.id == "ses_music")
    assert row.music_tag_fields == ["title", "cover"]
    assert all(type(v) is str for v in row.music_tag_fields)  # plain values, not enum members


def test_update_leaves_music_tags_alone_when_not_sent(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_music(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/sessions/ses_music", json={"name": "Renamed"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["music_tag_fields"] == ["artist", "title", "cover"]


@pytest.mark.parametrize(
    ("value", "status", "detail"),
    [
        (None, 400, "music_tag_fields must not be null"),
        (["artist", "artist"], 400, "music_tag_fields: duplicate values"),
        (["genre"], 422, None),
    ],
)
def test_update_rejects_a_bad_tag_list(signing_key: bytes, value: object, status: int, detail: str | None) -> None:
    db = FakeSession()
    _seed_music(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/sessions/ses_music", json={"music_tag_fields": value}, headers=_auth(token))
    assert r.status_code == status
    if detail is not None:
        assert r.json()["detail"] == detail
    assert next(s for s in db.rows["sessions"] if s.id == "ses_music").music_tag_fields == ["artist", "title", "cover"]


def test_update_rejects_music_tags_on_a_movie_session(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["sessions"].append(
        Session(
            id="ses_movie",
            name="Movie",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_movie",
            output_path_template="{title}.{ext}",
        )
    )
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/sessions/ses_movie", json={"music_tag_fields": ["artist"]}, headers=_auth(token))
    assert r.status_code == 400
    assert r.json()["detail"] == "music_tag_fields applies to music sessions only"


def test_clone_keeps_the_music_tags(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_music(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post("/api/sessions/ses_music/clone", json={"name": "Copy"}, headers=_auth(token))
    assert r.status_code == 201, r.text
    assert r.json()["music_tag_fields"] == ["artist", "title", "cover"]
    src = next(s for s in db.rows["sessions"] if s.id == "ses_music")
    clone = next(s for s in db.rows["sessions"] if s.id == r.json()["id"])
    assert clone.music_tag_fields is not src.music_tag_fields


def test_update_accepts_a_rip_preset_of_the_session_media_type(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_music(db)
    db.rows["rip_presets"].append(
        RipPreset(
            id="rpr_music_fast",
            name="Music: Fast",
            media_type=MediaType.MUSIC,
            is_builtin=False,
            track_selection=TrackSelection.ALL_TRACKS,
            identification_mode=IdentificationMode.REQUIRED,
            output_mode=OutputMode.TRACKS,
        )
    )
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/sessions/ses_music", json={"rip_preset_id": "rpr_music_fast"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["rip_preset_id"] == "rpr_music_fast"


# --- music cover size ---


def test_create_music_session_embeds_the_500px_cover_by_default(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_music(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = _create_music(client, token)
    assert r.status_code == 201, r.text
    assert r.json()["music_cover_size"] == "500"


def test_create_music_session_stores_the_chosen_cover_size(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_music(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = _create_music(client, token, music_cover_size="source")
    assert r.status_code == 201, r.text
    assert r.json()["music_cover_size"] == "source"
    assert next(s for s in db.rows["sessions"] if s.id == r.json()["id"]).music_cover_size == "source"


def test_create_rejects_a_cover_size_on_a_movie_session(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    body = {
        "name": "Movie",
        "media_type": "movie",
        "rip_preset_id": "rpr_movie",
        "output_path_template": "{title} ({year})/{title}.{ext}",
        "music_cover_size": "1200",
    }
    with TestClient(app) as client:
        r = client.post("/api/sessions", json=body, headers=_auth(token))
    assert r.status_code == 400
    assert r.json()["detail"] == "music_cover_size applies to music sessions only"


def test_update_music_session_cover_size(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_music(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/sessions/ses_music", json={"music_cover_size": "1200"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["music_cover_size"] == "1200"
    assert next(s for s in db.rows["sessions"] if s.id == "ses_music").music_cover_size == "1200"


@pytest.mark.parametrize(
    ("value", "status", "detail"),
    [(None, 400, "music_cover_size must not be null"), ("300", 422, None), ("front", 422, None)],
)
def test_update_rejects_a_bad_cover_size(signing_key: bytes, value: object, status: int, detail: str | None) -> None:
    db = FakeSession()
    _seed_music(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/sessions/ses_music", json={"music_cover_size": value}, headers=_auth(token))
    assert r.status_code == status
    if detail is not None:
        assert r.json()["detail"] == detail
    assert next(s for s in db.rows["sessions"] if s.id == "ses_music").music_cover_size == "500"


def test_clone_keeps_the_cover_size(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_music(db)
    next(s for s in db.rows["sessions"] if s.id == "ses_music").music_cover_size = MusicCoverSize.PX_1200
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post("/api/sessions/ses_music/clone", json={"name": "Copy"}, headers=_auth(token))
    assert r.status_code == 201, r.text
    assert r.json()["music_cover_size"] == "1200"


# --- music cover file size limit ---


def test_create_music_session_limits_the_cover_to_2mb_by_default(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_music(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = _create_music(client, token)
    assert r.status_code == 201, r.text
    assert r.json()["music_cover_max_size"] == "2mb"


def test_create_music_session_stores_the_chosen_cover_limit(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_music(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = _create_music(client, token, music_cover_size="source", music_cover_max_size="unlimited")
    assert r.status_code == 201, r.text
    assert r.json()["music_cover_max_size"] == "unlimited"
    row = next(s for s in db.rows["sessions"] if s.id == r.json()["id"])
    # Stored as plain values, the way an update stores them.
    assert (row.music_cover_size, row.music_cover_max_size) == ("source", "unlimited")
    assert type(row.music_cover_max_size) is str


def test_create_rejects_a_cover_limit_on_a_movie_session(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    body = {
        "name": "Movie",
        "media_type": "movie",
        "rip_preset_id": "rpr_movie",
        "output_path_template": "{title} ({year})/{title}.{ext}",
        "music_cover_max_size": "5mb",
    }
    with TestClient(app) as client:
        r = client.post("/api/sessions", json=body, headers=_auth(token))
    assert r.status_code == 400
    assert r.json()["detail"] == "music_cover_max_size applies to music sessions only"


def test_update_music_session_cover_limit(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_music(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/sessions/ses_music", json={"music_cover_max_size": "10mb"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["music_cover_max_size"] == "10mb"
    assert next(s for s in db.rows["sessions"] if s.id == "ses_music").music_cover_max_size == "10mb"


@pytest.mark.parametrize(
    ("value", "status", "detail"),
    [(None, 400, "music_cover_max_size must not be null"), ("3mb", 422, None), ("2097152", 422, None)],
)
def test_update_rejects_a_bad_cover_limit(signing_key: bytes, value: object, status: int, detail: str | None) -> None:
    db = FakeSession()
    _seed_music(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/sessions/ses_music", json={"music_cover_max_size": value}, headers=_auth(token))
    assert r.status_code == status
    if detail is not None:
        assert r.json()["detail"] == detail
    assert next(s for s in db.rows["sessions"] if s.id == "ses_music").music_cover_max_size == "2mb"


def test_clone_keeps_the_cover_limit(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_music(db)
    next(s for s in db.rows["sessions"] if s.id == "ses_music").music_cover_max_size = MusicCoverMaxSize.MB_5
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post("/api/sessions/ses_music/clone", json={"name": "Copy"}, headers=_auth(token))
    assert r.status_code == 201, r.text
    assert r.json()["music_cover_max_size"] == "5mb"
