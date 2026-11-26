"""Transcode-preset HandBrake settings: stored whole on create and patch, and
`preset_json` is gone from the wire."""

from __future__ import annotations

import secrets

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from arm_backend.db import get_session
from arm_backend.handbrake_schema_store import SchemaStore
from arm_backend.jwt_utils import issue_access_token
from arm_backend.routers import transcode_presets as tp_router
from arm_common import ContainerFormat, Gpu, GpuVendor, MediaType, TranscodePreset, TranscodeTool, User

from tests._fakes import FakeSession
from tests._hb_schema import fixture_schema, schema_without_nvenc_h264_preset

_SETTINGS = {
    "common": {
        "PictureWidth": 1280,
        "PictureHeight": 720,
        "VideoFramerateMode": "cfr",
        "AudioList": [{"AudioEncoder": "av_aac", "AudioMixdown": "5point1", "AudioBitrate": 384}],
    },
    "encoders": {"x265": {"VideoPreset": "slow", "VideoQualitySlider": 20}},
}

_BODY = {
    "name": "Plex 720p",
    "media_type": "movie",
    "tool": "handbrake",
    "container": "mkv",
    "encoder": "any_h265",
    "handbrake_settings": _SETTINGS,
}


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _make_app(
    signing_key: bytes, db: FakeSession, *, store: SchemaStore | None = None
) -> tuple[FastAPI, dict[str, str]]:
    app = FastAPI()
    app.state.signing_key = signing_key
    if store is None:
        store = SchemaStore()
        store.replace(fixture_schema())
    app.state.handbrake_schema_store = store
    app.include_router(tp_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, {"Authorization": f"Bearer {token}"}


def _stored(settings: dict | None) -> TranscodePreset:
    return TranscodePreset(
        id="tpr_s",
        name="s",
        media_type=MediaType.MOVIE,
        is_builtin=False,
        tool=TranscodeTool.HANDBRAKE,
        container=ContainerFormat.MKV,
        handbrake_settings=settings,
    )


def test_create_round_trips_settings(signing_key: bytes) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post("/api/transcode-presets", json=_BODY, headers=headers)
    assert r.status_code == 201
    assert r.json()["handbrake_settings"] == {
        "common": _SETTINGS["common"],
        "encoders": _SETTINGS["encoders"],
    }
    assert r.json()["issues"] == []
    assert r.json()["host_notes"] == ["encodes_on_cpu_here"]  # no GPUs on this host
    assert db.rows["transcode_presets"][0].handbrake_settings == r.json()["handbrake_settings"]


def test_create_without_settings_stores_null(signing_key: bytes) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db)
    body = {k: v for k, v in _BODY.items() if k != "handbrake_settings"}
    with TestClient(app) as client:
        r = client.post("/api/transcode-presets", json=body, headers=headers)
    assert r.status_code == 201
    assert r.json()["handbrake_settings"] is None


def test_patch_replaces_settings_whole(signing_key: bytes) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db)
    db.rows["transcode_presets"] = [_stored(_SETTINGS)]
    with TestClient(app) as client:
        r = client.patch(
            "/api/transcode-presets/tpr_s",
            json={"handbrake_settings": {"common": {"PictureWidth": 640}}},
            headers=headers,
        )
    assert r.status_code == 200
    assert r.json()["handbrake_settings"] == {"common": {"PictureWidth": 640}, "encoders": {}}


def test_patch_null_clears(signing_key: bytes) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db)
    db.rows["transcode_presets"] = [_stored(_SETTINGS)]
    with TestClient(app) as client:
        r = client.patch("/api/transcode-presets/tpr_s", json={"handbrake_settings": None}, headers=headers)
    assert r.status_code == 200
    assert r.json()["handbrake_settings"] is None


def test_view_has_no_preset_json(signing_key: bytes) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db)
    db.rows["transcode_presets"] = [_stored(None)]
    with TestClient(app) as client:
        r = client.get("/api/transcode-presets/tpr_s", headers=headers)
    assert "preset_json" not in r.json()
    assert not hasattr(TranscodePreset, "preset_json")


# --- save-time validation, read-time issues ---------------------------------------------------------

_H264 = {
    "name": "Plex h264",
    "media_type": "movie",
    "tool": "handbrake",
    "container": "mkv",
    "encoder": "any_h264",
}
_BAD = {"encoders": {"nvenc_h264": {"VideoPreset": "warp"}}}
_GOOD = {"encoders": {"nvenc_h264": {"VideoPreset": "slower"}}}


def _stored_h264(settings: dict | None, **extra: object) -> TranscodePreset:
    preset = _stored(settings)
    preset.encoder = "any_h264"
    for key, value in extra.items():
        setattr(preset, key, value)
    return preset


def _empty_store() -> SchemaStore:
    return SchemaStore()


def test_create_with_a_bad_value_is_422_with_the_issue_list(signing_key: bytes) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post("/api/transcode-presets", json={**_H264, "handbrake_settings": _BAD}, headers=headers)
    assert r.status_code == 422
    [issue] = r.json()["detail"]["issues"]
    assert (issue["encoder"], issue["key"], issue["code"]) == ("nvenc_h264", "VideoPreset", "not_in_list")
    assert db.rows.get("transcode_presets", []) == []


def test_create_with_settings_and_no_schema_is_503(signing_key: bytes) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db, store=_empty_store())
    with TestClient(app) as client:
        r = client.post("/api/transcode-presets", json={**_H264, "handbrake_settings": _GOOD}, headers=headers)
    assert r.status_code == 503
    assert db.rows.get("transcode_presets", []) == []


def test_create_without_settings_needs_no_schema(signing_key: bytes) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db, store=_empty_store())
    with TestClient(app) as client:
        r = client.post("/api/transcode-presets", json=_H264, headers=headers)
    assert r.status_code == 201
    assert r.json()["issues"] == []


@pytest.mark.parametrize("empty", [{}, {"common": {}, "encoders": {}}])
def test_create_stores_empty_settings_as_null_without_a_schema(signing_key: bytes, empty: dict) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db, store=_empty_store())
    with TestClient(app) as client:
        r = client.post("/api/transcode-presets", json={**_H264, "handbrake_settings": empty}, headers=headers)
    assert r.status_code == 201
    assert r.json()["handbrake_settings"] is None
    assert db.rows["transcode_presets"][0].handbrake_settings is None


def test_create_drops_an_empty_unreachable_block_instead_of_422(signing_key: bytes) -> None:
    """A raw client's empty x265 block on an h264 preset is pruned, as the UI does, not rejected."""
    db = FakeSession()
    app, headers = _make_app(signing_key, db)
    settings = {"encoders": {**_GOOD["encoders"], "x265": {}}}
    with TestClient(app) as client:
        r = client.post("/api/transcode-presets", json={**_H264, "handbrake_settings": settings}, headers=headers)
    assert r.status_code == 201
    assert db.rows["transcode_presets"][0].handbrake_settings == {"common": {}, **_GOOD}


def test_patch_empty_settings_clears_to_null_without_a_schema(signing_key: bytes) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db, store=_empty_store())
    db.rows["transcode_presets"] = [_stored_h264(_GOOD)]
    with TestClient(app) as client:
        r = client.patch("/api/transcode-presets/tpr_s", json={"handbrake_settings": {}}, headers=headers)
    assert r.status_code == 200
    assert db.rows["transcode_presets"][0].handbrake_settings is None


def test_create_with_an_unknown_preset_ref_is_422(signing_key: bytes) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db)
    body = {**_H264, "preset_ref": "No Such Preset", "handbrake_settings": _GOOD}
    with TestClient(app) as client:
        r = client.post("/api/transcode-presets", json=body, headers=headers)
    assert r.status_code == 422
    assert [(i["key"], i["code"]) for i in r.json()["detail"]["issues"]] == [("preset_ref", "not_in_list")]


def test_patch_to_a_tool_that_ignores_settings_is_422(signing_key: bytes) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db)
    db.rows["transcode_presets"] = [_stored_h264(_GOOD)]
    with TestClient(app) as client:
        r = client.patch("/api/transcode-presets/tpr_s", json={"tool": "none", "encoder": "preset"}, headers=headers)
    assert r.status_code == 422
    assert [i["code"] for i in r.json()["detail"]["issues"]] == ["engine_ignores_settings"]
    assert db.rows["transcode_presets"][0].tool == TranscodeTool.HANDBRAKE


def test_patch_to_a_vaapi_encoder_is_422(signing_key: bytes) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db)
    db.rows["transcode_presets"] = [_stored_h264(_GOOD)]
    with TestClient(app) as client:
        r = client.patch("/api/transcode-presets/tpr_s", json={"encoder": "vaapi_h264"}, headers=headers)
    assert r.status_code == 422
    assert [i["code"] for i in r.json()["detail"]["issues"]] == ["engine_ignores_settings"]


def test_patch_that_leaves_settings_valid_applies(signing_key: bytes) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db)
    db.rows["transcode_presets"] = [_stored_h264(_GOOD)]
    with TestClient(app) as client:
        r = client.patch("/api/transcode-presets/tpr_s", json={"name": "renamed"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["name"] == "renamed"


def test_patch_with_a_bad_value_is_422_and_leaves_the_row(signing_key: bytes) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db)
    db.rows["transcode_presets"] = [_stored_h264(_GOOD)]
    with TestClient(app) as client:
        r = client.patch("/api/transcode-presets/tpr_s", json={"handbrake_settings": _BAD}, headers=headers)
    assert r.status_code == 422
    assert db.rows["transcode_presets"][0].handbrake_settings == _GOOD


def test_patch_of_the_encoder_of_a_preset_with_settings_and_no_schema_is_503(signing_key: bytes) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db, store=_empty_store())
    db.rows["transcode_presets"] = [_stored_h264(_GOOD)]
    with TestClient(app) as client:
        r = client.patch("/api/transcode-presets/tpr_s", json={"encoder": "any_h265"}, headers=headers)
    assert r.status_code == 503


def test_rename_with_no_schema_skips_validation(signing_key: bytes) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db, store=_empty_store())
    db.rows["transcode_presets"] = [_stored_h264(_GOOD)]
    with TestClient(app) as client:
        r = client.patch("/api/transcode-presets/tpr_s", json={"name": "renamed"}, headers=headers)
    assert r.status_code == 200 and r.json()["name"] == "renamed"


def test_rename_of_a_preset_with_stale_settings_still_saves_and_lists_the_issue(signing_key: bytes) -> None:
    db = FakeSession()
    store = SchemaStore()
    store.replace(schema_without_nvenc_h264_preset("slower"))
    app, headers = _make_app(signing_key, db, store=store)
    db.rows["transcode_presets"] = [_stored_h264(_GOOD)]
    with TestClient(app) as client:
        r = client.patch("/api/transcode-presets/tpr_s", json={"name": "renamed"}, headers=headers)
    assert r.status_code == 200
    assert [(i["key"], i["code"]) for i in r.json()["issues"]] == [("VideoPreset", "not_in_list")]


def test_read_reports_issues_against_the_current_schema(signing_key: bytes) -> None:
    db = FakeSession()
    store = SchemaStore()
    store.replace(fixture_schema())
    app, headers = _make_app(signing_key, db, store=store)
    db.rows["transcode_presets"] = [_stored_h264(_GOOD)]
    with TestClient(app) as client:
        assert client.get("/api/transcode-presets/tpr_s", headers=headers).json()["issues"] == []
        store.replace(schema_without_nvenc_h264_preset("slower"))
        got = client.get("/api/transcode-presets/tpr_s", headers=headers).json()
        listed = client.get("/api/transcode-presets", headers=headers).json()
    assert [(i["key"], i["code"]) for i in got["issues"]] == [("VideoPreset", "not_in_list")]
    assert listed[0]["issues"] == got["issues"]


def test_read_with_no_schema_has_no_issues(signing_key: bytes) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db, store=_empty_store())
    db.rows["transcode_presets"] = [_stored_h264(_GOOD)]
    with TestClient(app) as client:
        r = client.get("/api/transcode-presets/tpr_s", headers=headers)
    assert r.json()["issues"] == []


def test_read_carries_the_host_note_from_the_gpus_table(signing_key: bytes) -> None:
    db = FakeSession()
    app, headers = _make_app(signing_key, db)
    db.rows["transcode_presets"] = [_stored_h264(_GOOD)]
    db.rows["gpus"] = [Gpu(id="gpu_amd", vendor=GpuVendor.VAAPI, device_path="/dev/dri/renderD128")]
    with TestClient(app) as client:
        got = client.get("/api/transcode-presets/tpr_s", headers=headers).json()
        listed = client.get("/api/transcode-presets", headers=headers).json()
    assert got["host_notes"] == ["encodes_on_cpu_here"]
    assert listed[0]["host_notes"] == ["encodes_on_cpu_here"]
