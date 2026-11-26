"""POST /api/transcode-presets/import/parse: stateless parse of a HandBrake GUI export."""

from __future__ import annotations

import json
import secrets

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from arm_backend.db import get_session
from arm_backend.handbrake_schema_store import SchemaStore
from arm_backend.jwt_utils import issue_access_token
from arm_backend.routers import transcode_presets as tp_router
from arm_common import User

from tests._fakes import FakeSession
from tests._hb_schema import fixture_schema, plex_export

_URL = "/api/transcode-presets/import/parse"
_ONE_MB = 1_048_576


def _app(*, loaded: bool = True, role: str = "admin") -> tuple[FastAPI, dict[str, str], FakeSession]:
    key = secrets.token_bytes(32)
    db = FakeSession()
    db.rows["users"] = [User(id="usr_a", username="a", password_hash="x", password_must_change=False, role=role)]
    app = FastAPI()
    app.state.signing_key = key
    store = SchemaStore()
    if loaded:
        store.replace(fixture_schema())
    app.state.handbrake_schema_store = store
    app.include_router(tp_router.router)

    async def _session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _session
    token, _ = issue_access_token("usr_a", "a", key)
    return app, {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, db


def _post(content: bytes | str, **kwargs: object) -> object:
    app, headers, db = _app(**kwargs)  # type: ignore[arg-type]
    with TestClient(app) as client:
        r = client.post(_URL, content=content, headers=headers)
    assert db.rows.get("transcode_presets", []) == []
    return r


def test_plex_export_parses_to_a_proposal() -> None:
    r = _post(json.dumps(plex_export()))
    assert r.status_code == 200, r.text  # type: ignore[attr-defined]
    body = r.json()  # type: ignore[attr-defined]
    assert body["handbrake_version"] == {"export": "72.0.0", "schema": "72.0.0"}
    [preset] = body["presets"]
    assert preset["importable"] is True and preset["issues"] == []
    assert preset["proposal"]["encoder"] == "any_h264" and preset["proposal"]["container"] == "mkv"
    assert preset["proposal"]["handbrake_settings"]["encoders"]["nvenc_h264"]["VideoPreset"] == "slower"
    assert preset["dropped_keys"] == ["VideoColorMatrixCode"]


@pytest.mark.parametrize("body", ["[]", '"x"', "{}"])
def test_a_body_that_is_not_an_export_is_422(body: str) -> None:
    r = _post(body)
    assert r.status_code == 422  # type: ignore[attr-defined]
    assert isinstance(r.json()["detail"], str)  # type: ignore[attr-defined]


def test_a_body_over_one_megabyte_is_413() -> None:
    r = _post(b" " * (_ONE_MB + 1))
    assert r.status_code == 413  # type: ignore[attr-defined]
    assert r.json() == {"detail": "The file is larger than 1 MB"}  # type: ignore[attr-defined]


def test_a_body_of_exactly_one_megabyte_is_read() -> None:
    padded = json.dumps(plex_export()).encode() + b" " * (_ONE_MB - len(json.dumps(plex_export())))
    assert len(padded) == _ONE_MB
    assert _post(padded).status_code == 200  # type: ignore[attr-defined]


def test_a_body_that_is_not_json_is_422() -> None:
    r = _post("not json {")
    assert r.status_code == 422  # type: ignore[attr-defined]
    assert r.json() == {"detail": "The file is not valid JSON"}  # type: ignore[attr-defined]


def test_a_deeply_nested_body_is_422_not_500() -> None:
    r = _post("[" * 200_000)
    assert r.status_code == 422  # type: ignore[attr-defined]
    assert r.json() == {"detail": "The file is not valid JSON"}  # type: ignore[attr-defined]


def test_no_schema_is_503() -> None:
    r = _post(json.dumps(plex_export()), loaded=False)
    assert r.status_code == 503  # type: ignore[attr-defined]
    assert r.json() == {"detail": "No HandBrake schema loaded yet"}  # type: ignore[attr-defined]


def test_a_guest_is_refused() -> None:
    assert _post(json.dumps(plex_export()), role="guest").status_code == 403  # type: ignore[attr-defined]


def test_the_endpoint_is_documented_with_a_json_body() -> None:
    app, _, _ = _app()
    op = app.openapi()["paths"][_URL]["post"]
    assert "application/json" in op["requestBody"]["content"]
