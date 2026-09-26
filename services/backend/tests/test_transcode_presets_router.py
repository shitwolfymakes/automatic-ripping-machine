"""Transcode-presets CRUD: list/get/create/patch/delete, built-in protection,
and the session-reference delete guard. Mirrors test_rip_presets_router.py."""

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
from arm_backend.routers import transcode_presets as tp_router  # noqa: E402
from arm_common import (  # noqa: E402
    ContainerFormat,
    MediaType,
    Session,
    TranscodePreset,
    TranscodeTool,
    User,
)

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(tp_router.router)

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


def _preset(
    preset_id: str = "tpr_x",
    *,
    name: str = "x",
    media_type: MediaType = MediaType.MOVIE,
    is_builtin: bool = False,
) -> TranscodePreset:
    return TranscodePreset(
        id=preset_id,
        name=name,
        media_type=media_type,
        is_builtin=is_builtin,
        tool=TranscodeTool.HANDBRAKE,
        preset_ref="Fast 1080p30",
        container=ContainerFormat.MKV,
    )


_CREATE_BODY = {
    "name": "Custom HB",
    "media_type": "movie",
    "tool": "handbrake",
    "preset_ref": "Fast 1080p30",
    "container": "mkv",
}


def test_list_all_and_filter_by_media_type(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["transcode_presets"] = [
        _preset("tpr_movie", name="movie", media_type=MediaType.MOVIE),
        _preset("tpr_tv", name="tv", media_type=MediaType.TV),
    ]
    with TestClient(app) as client:
        all_rows = client.get("/api/transcode-presets", headers=_auth(token))
        filtered = client.get("/api/transcode-presets?media_type=tv", headers=_auth(token))
    assert all_rows.status_code == 200
    assert len(all_rows.json()) == 2
    assert filtered.status_code == 200
    assert [r["media_type"] for r in filtered.json()] == ["tv"]


def test_get_found_and_404(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["transcode_presets"] = [_preset("tpr_a", name="a")]
    with TestClient(app) as client:
        found = client.get("/api/transcode-presets/tpr_a", headers=_auth(token))
        missing = client.get("/api/transcode-presets/tpr_missing", headers=_auth(token))
    assert found.status_code == 200
    assert found.json()["id"] == "tpr_a"
    assert missing.status_code == 404
    assert "unknown transcode_preset_id" in missing.json()["detail"]


def test_create_201(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post("/api/transcode-presets", json=_CREATE_BODY, headers=_auth(token))
    assert r.status_code == 201
    out = r.json()
    assert out["name"] == "Custom HB"
    assert out["is_builtin"] is False
    assert out["created_by_user_id"] == "usr_admin"
    # Omitted encoder: the HandBrake preset's own encoder.
    assert out["encoder"] == "preset"


def test_create_persists_encoder(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post("/api/transcode-presets", json={**_CREATE_BODY, "encoder": "qsv_h265"}, headers=_auth(token))
    assert r.status_code == 201
    assert r.json()["encoder"] == "qsv_h265"
    assert db.rows["transcode_presets"][0].encoder == "qsv_h265"


def test_create_unknown_encoder_422(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post("/api/transcode-presets", json={**_CREATE_BODY, "encoder": "vce_h265"}, headers=_auth(token))
    assert r.status_code == 422
    assert "unknown encoder" in r.json()["detail"]
    assert db.rows.get("transcode_presets", []) == []


def test_create_non_handbrake_tool_rejects_codec_encoder_422(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    body = {**_CREATE_BODY, "tool": "abcde", "media_type": "music", "container": "flac", "encoder": "cpu_h265"}
    with TestClient(app) as client:
        r = client.post("/api/transcode-presets", json=body, headers=_auth(token))
    assert r.status_code == 422
    assert r.json()["detail"] == "encoder 'cpu_h265' is not valid for tool abcde; only 'preset' is"


def test_patch_encoder_validated_against_stored_tool(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["transcode_presets"] = [_preset("tpr_enc", name="enc")]
    with TestClient(app) as client:
        ok = client.patch("/api/transcode-presets/tpr_enc", json={"encoder": "cpu_av1"}, headers=_auth(token))
        unknown = client.patch("/api/transcode-presets/tpr_enc", json={"encoder": "nope"}, headers=_auth(token))
    assert ok.status_code == 200
    assert ok.json()["encoder"] == "cpu_av1"
    assert unknown.status_code == 422
    assert "unknown encoder" in unknown.json()["detail"]
    assert db.rows["transcode_presets"][0].encoder == "cpu_av1"


def test_patch_encoder_validated_against_requested_tool(signing_key: bytes) -> None:
    """Switching the tool away from HandBrake while keeping a codec encoder is
    rejected; switching tool and encoder together to `preset` is accepted."""
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    row = _preset("tpr_sw", name="sw")
    row.encoder = "any_h265"
    db.rows["transcode_presets"] = [row]
    with TestClient(app) as client:
        rejected = client.patch(
            "/api/transcode-presets/tpr_sw", json={"tool": "none", "encoder": "any_h265"}, headers=_auth(token)
        )
        rejected_tool_only = client.patch("/api/transcode-presets/tpr_sw", json={"tool": "none"}, headers=_auth(token))
        ok = client.patch(
            "/api/transcode-presets/tpr_sw", json={"tool": "none", "encoder": "preset"}, headers=_auth(token)
        )
    assert rejected.status_code == 422
    assert "not valid for tool none" in rejected.json()["detail"]
    assert rejected_tool_only.status_code == 422
    assert ok.status_code == 200
    assert ok.json()["tool"] == "none"
    assert ok.json()["encoder"] == "preset"


def test_patch_null_encoder_leaves_it_unchanged(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    row = _preset("tpr_null", name="null")
    row.encoder = "cpu_h264"
    db.rows["transcode_presets"] = [row]
    with TestClient(app) as client:
        r = client.patch(
            "/api/transcode-presets/tpr_null", json={"name": "renamed", "encoder": None}, headers=_auth(token)
        )
    assert r.status_code == 200
    assert r.json()["encoder"] == "cpu_h264"
    assert r.json()["name"] == "renamed"


def test_patch_builtin_encoder_409(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["transcode_presets"] = [_preset("tpr_bi", name="builtin", is_builtin=True)]
    with TestClient(app) as client:
        r = client.patch("/api/transcode-presets/tpr_bi", json={"encoder": "cpu_h265"}, headers=_auth(token))
    assert r.status_code == 409
    assert "only `name` can be edited" in r.json()["detail"]


def test_patch_updates_fields(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["transcode_presets"] = [_preset("tpr_e", name="old")]
    with TestClient(app) as client:
        r = client.patch(
            "/api/transcode-presets/tpr_e",
            json={"name": "new", "extra_args": "--quality 20"},
            headers=_auth(token),
        )
    assert r.status_code == 200
    assert r.json()["name"] == "new"
    assert r.json()["extra_args"] == "--quality 20"


def test_patch_404(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.patch("/api/transcode-presets/tpr_missing", json={"name": "x"}, headers=_auth(token))
    assert r.status_code == 404


def test_patch_builtin_name_only_allowed(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["transcode_presets"] = [_preset("tpr_b", name="builtin", is_builtin=True)]
    with TestClient(app) as client:
        ok = client.patch("/api/transcode-presets/tpr_b", json={"name": "renamed"}, headers=_auth(token))
        rejected = client.patch(
            "/api/transcode-presets/tpr_b",
            json={"extra_args": "--nope"},
            headers=_auth(token),
        )
    assert ok.status_code == 200
    assert ok.json()["name"] == "renamed"
    assert rejected.status_code == 409
    assert "only `name` can be edited" in rejected.json()["detail"]


def test_delete_404(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.delete("/api/transcode-presets/tpr_missing", headers=_auth(token))
    assert r.status_code == 404


def test_delete_builtin_409(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["transcode_presets"] = [_preset("tpr_b", name="builtin", is_builtin=True)]
    with TestClient(app) as client:
        r = client.delete("/api/transcode-presets/tpr_b", headers=_auth(token))
    assert r.status_code == 409
    assert "built-in" in r.json()["detail"]


def test_delete_referenced_by_session_409(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["transcode_presets"] = [_preset("tpr_ref", name="ref")]
    db.rows["sessions"] = [
        Session(
            id="ses_r",
            name="referrer",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_any",
            transcode_preset_id="tpr_ref",
            output_path_template="{title}.{ext}",
        )
    ]
    with TestClient(app) as client:
        r = client.delete("/api/transcode-presets/tpr_ref", headers=_auth(token))
    assert r.status_code == 409
    assert "referenced by session" in r.json()["detail"]
    assert "referrer" in r.json()["detail"]


def test_delete_success_204(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["transcode_presets"] = [_preset("tpr_del", name="del")]
    db.rows["sessions"] = []
    with TestClient(app) as client:
        r = client.delete("/api/transcode-presets/tpr_del", headers=_auth(token))
    assert r.status_code == 204
