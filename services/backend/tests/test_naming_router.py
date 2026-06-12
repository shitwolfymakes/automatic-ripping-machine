"""GET /api/naming/variables and GET /api/jobs/{id}/naming-preview."""

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
from arm_backend.routers import naming as naming_router  # noqa: E402
from arm_common import (  # noqa: E402
    ContainerFormat,
    HwPreference,
    Job,
    MediaType,
    Session,
    Track,
    TranscodePreset,
    TranscodeTool,
    User,
)
from arm_common.enums import DiscType, JobStatus, TrackKind  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402

# Valid ULID-shaped IDs (prefix + 26 Crockford base32 chars)
_JOB_ID_1 = "job_00000000000000000000000001"
_JOB_ID_2 = "job_00000000000000000000000002"
_JOB_ID_3 = "job_00000000000000000000000003"
_JOB_ID_4 = "job_00000000000000000000000004"
_TRK_ID_1 = "trk_00000000000000000000000001"
_TRK_ID_2 = "trk_00000000000000000000000002"
_TRK_ID_3 = "trk_00000000000000000000000003"
_TRK_ID_4 = "trk_00000000000000000000000004"
_SES_ID = "ses_00000000000000000000000001"
_SES_ID_2 = "ses_00000000000000000000000002"
_SES_ID_3 = "ses_00000000000000000000000003"
_TPR_ID = "tpr_00000000000000000000000001"
_TPR_ID_2 = "tpr_00000000000000000000000002"


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession) -> None:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(naming_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_variables_returns_all_media_types(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/naming/variables", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()["variables"]
    assert "movie" in body and "tv" in body and "music" in body
    movie_tokens = {v["token"] for v in body["movie"]}
    assert "title" in movie_tokens and "year" in movie_tokens


def test_variables_filter_by_media_type(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/naming/variables", params={"media_type": "music"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert set(r.json()["variables"].keys()) == {"music"}


def test_variables_unauthenticated_401(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, _ = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/naming/variables")
    assert r.status_code == 401


def _seed_job(db: FakeSession) -> None:
    db.rows["sessions"] = [
        Session(
            id=_SES_ID,
            name="Plex",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_x",
            transcode_preset_id=None,
            output_path_template="{title} ({year})/{title}.mkv",
        )
    ]
    db.rows["jobs"] = [
        Job(
            id=_JOB_ID_1,
            drive_id="drv_x",
            disc_type=DiscType.DVD,
            status=JobStatus.IDENTIFIED,
            title="Iron Man",
            year=2008,
            metadata_json={"pending_session_id": _SES_ID},
        )
    ]
    db.rows["tracks"] = [
        Track(
            id=_TRK_ID_1,
            job_id=_JOB_ID_1,
            kind=TrackKind.VIDEO_TITLE,
            index=1,
            source_ref="1",
        ),
    ]


def test_job_naming_preview_renders_filenames(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    _seed_job(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get(f"/api/jobs/{_JOB_ID_1}/naming-preview", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    items = body["items"]
    assert len(items) == 1
    assert items[0]["track_id"] == _TRK_ID_1
    assert "Iron Man" in items[0]["output_path"]
    assert set(items[0]) == {"track_id", "track_number", "output_path", "output_dir", "output_name"}
    assert "job_output_dir" in body
    assert body["job_output_name"] == "Iron Man"


def test_job_naming_preview_unknown_job_404(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get(f"/api/jobs/{_JOB_ID_2}/naming-preview", headers=_auth(token))
    assert r.status_code == 404


def test_job_naming_preview_unauthenticated_401(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, _ = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get(f"/api/jobs/{_JOB_ID_1}/naming-preview")
    assert r.status_code == 401


def test_job_naming_preview_no_session_409(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["jobs"] = [
        Job(
            id=_JOB_ID_2,
            drive_id="drv_x",
            disc_type=DiscType.DVD,
            status=JobStatus.IDENTIFIED,
            title="Iron Man",
            year=2008,
            metadata_json={},  # no pending_session_id
        )
    ]
    db.rows["tracks"] = []
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get(f"/api/jobs/{_JOB_ID_2}/naming-preview", headers=_auth(token))
    assert r.status_code == 409


def test_job_naming_preview_with_transcode_preset(signing_key: bytes) -> None:
    """When the session references a transcode preset, the preset is resolved and
    {transcode_slug}/{ext} tokens are available in the template."""
    from arm_common import ContainerFormat, HwPreference, TranscodePreset, TranscodeTool

    db = FakeSession()
    _seed(db)
    _tpr_id = "tpr_00000000000000000000000001"
    db.rows["transcode_presets"] = [
        TranscodePreset(
            id=_tpr_id,
            name="Plex 1080p",
            media_type=MediaType.MOVIE,
            is_builtin=True,
            tool=TranscodeTool.HANDBRAKE,
            container=ContainerFormat.MKV,
            hw_preference=HwPreference.CPU_ONLY,
        )
    ]
    db.rows["sessions"] = [
        Session(
            id=_SES_ID,
            name="Plex",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_x",
            transcode_preset_id=_tpr_id,
            output_path_template="{title} ({year})/{title}.{ext}",
        )
    ]
    db.rows["jobs"] = [
        Job(
            id=_JOB_ID_1,
            drive_id="drv_x",
            disc_type=DiscType.DVD,
            status=JobStatus.IDENTIFIED,
            title="Iron Man",
            year=2008,
            metadata_json={"pending_session_id": _SES_ID},
        )
    ]
    db.rows["tracks"] = [
        Track(
            id=_TRK_ID_1,
            job_id=_JOB_ID_1,
            kind=TrackKind.VIDEO_TITLE,
            index=1,
            source_ref="1",
        ),
    ]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get(f"/api/jobs/{_JOB_ID_1}/naming-preview", headers=_auth(token))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    assert "Iron Man" in items[0]["output_path"]
    assert "mkv" in items[0]["output_path"]


def test_job_naming_preview_bad_template_422(signing_key: bytes) -> None:
    """A template referencing an empty token raises TemplateValidationError → 422."""
    db = FakeSession()
    _seed(db)
    # Job with no year, but template uses {year} — year resolves empty → 422
    db.rows["sessions"] = [
        Session(
            id=_SES_ID,
            name="Plex",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_x",
            transcode_preset_id=None,
            output_path_template="{title} ({year})/{title}.mkv",
        )
    ]
    db.rows["jobs"] = [
        Job(
            id=_JOB_ID_1,
            drive_id="drv_x",
            disc_type=DiscType.DVD,
            status=JobStatus.IDENTIFIED,
            title="Iron Man",
            year=None,  # year missing → {year} resolves to "" → TemplateValidationError
            metadata_json={"pending_session_id": _SES_ID},
        )
    ]
    db.rows["tracks"] = [
        Track(
            id=_TRK_ID_1,
            job_id=_JOB_ID_1,
            kind=TrackKind.VIDEO_TITLE,
            index=1,
            source_ref="1",
        ),
    ]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get(f"/api/jobs/{_JOB_ID_1}/naming-preview", headers=_auth(token))
    assert r.status_code == 422, r.text


def test_naming_preview_split_and_job_fields(signing_key: bytes) -> None:
    """TV template with subfolder: per-track output_dir/output_name split + job-level fields."""
    db = FakeSession()
    _seed(db)
    db.rows["transcode_presets"] = [
        TranscodePreset(
            id=_TPR_ID_2,
            name="TV 1080p",
            media_type=MediaType.TV,
            is_builtin=True,
            tool=TranscodeTool.HANDBRAKE,
            container=ContainerFormat.MKV,
            hw_preference=HwPreference.CPU_ONLY,
        )
    ]
    db.rows["sessions"] = [
        Session(
            id=_SES_ID_2,
            name="TV Plex",
            media_type=MediaType.TV,
            is_builtin=False,
            rip_preset_id="rpr_x",
            transcode_preset_id=_TPR_ID_2,
            output_path_template="{show}/Season {season}/{show} - {track}.{ext}",
        )
    ]
    db.rows["jobs"] = [
        Job(
            id=_JOB_ID_3,
            drive_id="drv_x",
            disc_type=DiscType.BLURAY,
            status=JobStatus.IDENTIFIED,
            title="Battlestar",
            year=2004,
            metadata_json={"pending_session_id": _SES_ID_2, "season": "01"},
        )
    ]
    db.rows["tracks"] = [
        Track(
            id=_TRK_ID_3,
            job_id=_JOB_ID_3,
            kind=TrackKind.VIDEO_TITLE,
            index=1,
            source_ref="1",
        ),
        Track(
            id=_TRK_ID_4,
            job_id=_JOB_ID_3,
            kind=TrackKind.VIDEO_TITLE,
            index=2,
            source_ref="2",
        ),
    ]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get(f"/api/jobs/{_JOB_ID_3}/naming-preview", headers=_auth(token))
    body = r.json()
    assert r.status_code == 200, r.text
    assert set(body["items"][0]) == {"track_id", "track_number", "output_path", "output_dir", "output_name"}
    item = body["items"][0]
    # output_dir must be the directory portion of output_path
    assert item["output_dir"] == item["output_path"].rsplit("/", 1)[0]
    # output_name must be the basename
    assert item["output_name"] == item["output_path"].rsplit("/", 1)[1]
    # track_number is populated
    assert item["track_number"] is not None
    # job-level fields match items
    assert body["job_output_dir"] == body["items"][0]["output_dir"]
    assert body["job_output_name"] == "Battlestar"
    # Two tracks in result
    assert len(body["items"]) == 2


def test_naming_preview_flat_template(signing_key: bytes) -> None:
    """Flat (no-subfolder) template: output_dir is empty string for all items."""
    db = FakeSession()
    _seed(db)
    db.rows["transcode_presets"] = [
        TranscodePreset(
            id=_TPR_ID_2,
            name="Movie 1080p",
            media_type=MediaType.MOVIE,
            is_builtin=True,
            tool=TranscodeTool.HANDBRAKE,
            container=ContainerFormat.MKV,
            hw_preference=HwPreference.CPU_ONLY,
        )
    ]
    db.rows["sessions"] = [
        Session(
            id=_SES_ID_3,
            name="Flat",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_x",
            transcode_preset_id=_TPR_ID_2,
            output_path_template="{title} ({year}).{ext}",
        )
    ]
    db.rows["jobs"] = [
        Job(
            id=_JOB_ID_4,
            drive_id="drv_x",
            disc_type=DiscType.DVD,
            status=JobStatus.IDENTIFIED,
            title="Iron Man",
            year=2008,
            metadata_json={"pending_session_id": _SES_ID_3},
        )
    ]
    db.rows["tracks"] = [
        Track(
            id=_TRK_ID_3,
            job_id=_JOB_ID_4,
            kind=TrackKind.VIDEO_TITLE,
            index=1,
            source_ref="1",
        ),
    ]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get(f"/api/jobs/{_JOB_ID_4}/naming-preview", headers=_auth(token))
    body = r.json()
    assert r.status_code == 200, r.text
    assert body["job_output_dir"] == ""
    assert body["items"][0]["output_dir"] == ""
    assert body["items"][0]["output_name"] == body["items"][0]["output_path"]


def test_naming_validate_ok(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    body = {"template": "{title} ({year}).{ext}", "media_type": "movie", "has_transcode_preset": True}
    with TestClient(app) as client:
        r = client.post("/api/naming/validate", json=body, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json() == {"valid": True}


def test_naming_validate_rejects_unknown_token(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    body = {"template": "{nope}.{ext}", "media_type": "movie", "has_transcode_preset": True}
    with TestClient(app) as client:
        r = client.post("/api/naming/validate", json=body, headers=_auth(token))
    assert r.status_code == 422
    assert "nope" in r.json()["detail"]


def test_naming_validate_requires_auth() -> None:
    import secrets as _secrets

    app, _ = _make_app(_secrets.token_bytes(32), FakeSession())
    with TestClient(app) as client:
        r = client.post("/api/naming/validate", json={"template": "x", "media_type": "movie"})
    assert r.status_code == 401
