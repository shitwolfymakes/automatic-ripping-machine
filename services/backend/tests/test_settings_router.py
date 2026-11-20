from __future__ import annotations


import secrets

from fastapi import FastAPI
from fastapi.testclient import TestClient

from arm_backend.db import get_session
from arm_backend.jwt_utils import issue_access_token
from arm_backend.routers import settings as settings_router
from arm_common import User
from arm_common.models.user import GUEST_ROLE

from tests._fakes import FakeSession


def _app() -> tuple[FastAPI, str]:
    key = secrets.token_bytes(32)
    db = FakeSession()
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

    app = FastAPI()
    app.state.signing_key = key
    app.include_router(settings_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", key)
    return app, token


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_schema_returns_grouped_fields():
    app, token = _app()
    with TestClient(app) as c:
        r = c.get("/api/settings/schema", headers=_auth(token))
    assert r.status_code == 200, r.text
    groups = {g["name"] for g in r.json()["groups"]}
    assert {"Identification", "Keys", "Ripping", "Transcoding", "Notifications", "System"} <= groups
    order = [g["name"] for g in r.json()["groups"]]
    assert order.index("Identification") < order.index("Keys") < order.index("Ripping")
    all_fields = [f for g in r.json()["groups"] for f in g["fields"]]
    by_key = {f["key"]: f for f in all_fields}
    assert by_key["omdb_api_key"]["tier"] == "secret"
    assert by_key["search_provider_movie"]["type"] == "enum"
    assert by_key["MEDIA_ROOT"]["editable"] is False


def test_schema_requires_jwt():
    """No Authorization header falls back to the guest account (read-only route)."""
    app, _ = _app()
    with TestClient(app) as c:
        r = c.get("/api/settings/schema")
    assert r.status_code == 200


def test_infra_returns_whitelisted_values_only():
    app, token = _app()
    with TestClient(app) as c:
        r = c.get("/api/settings/infra", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "MEDIA_ROOT" in body
    # moved to operator config (config.max_parallel_transcodes) — no longer infra
    assert "MAX_PARALLEL_TRANSCODES" not in body
    # secrets / bootstrap NEVER exposed
    for forbidden in ("DATABASE_URL", "ARM_SERVICE_TOKEN", "TLS_CERT_PATH", "TLS_KEY_PATH"):
        assert forbidden not in body


def test_infra_requires_jwt():
    """No Authorization header falls back to the guest account (read-only route)."""
    app, _ = _app()
    with TestClient(app) as c:
        r = c.get("/api/settings/infra")
    assert r.status_code == 200


def test_schema_puts_auto_apply_in_the_defaults_group():
    """Auto-apply lives with the routing defaults it governs, not on the Transcoding tab."""
    app, token = _app()
    with TestClient(app) as c:
        groups = c.get("/api/settings/schema", headers=_auth(token)).json()["groups"]
    by_name = {g["name"]: g for g in groups}
    order = [g["name"] for g in groups]
    assert [f["key"] for f in by_name["Defaults"]["fields"]] == [
        "auto_transcode_on_idle",
        "miss_media_type",
        "miss_titles_kept",
    ]
    field = by_name["Defaults"]["fields"][0]
    assert field["label"] == "Apply these defaults automatically after each rip"
    assert field["help"] == (
        "When a rip completes, apply its default session (the drive's default when it fits the disc, "
        "else the media-type route) and queue its transcodes. A session chosen for one rip always applies."
    )
    media, kept = by_name["Defaults"]["fields"][1:]
    assert (media["label"], media["type"], media["enum_values"]) == (
        "Treat unidentified video discs as",
        "enum",
        ["movie", "tv"],
    )
    assert media["help"] == (
        "The media type a DVD or Blu-ray that misses identification starts with. "
        "Flip it on the review screen before you start the rip."
    )
    assert (kept["label"], kept["type"], kept["enum_values"]) == (
        "Titles kept on an unidentified disc",
        "enum",
        ["all", "preset"],
    )
    assert kept["help"] == (
        "All keeps every title for you to review. Preset keeps what the routed session's rip preset would "
        "(for example only the main feature)."
    )
    assert "auto_transcode_on_idle" not in [f["key"] for f in by_name["Transcoding"]["fields"]]
    assert order.index("Defaults") + 1 == order.index("Transcoding")


def test_setup_transcoding_step_keeps_its_fields_after_the_move():
    """First-run setup's transcoding step still lists the toggle and concurrency, and not auto-apply."""
    app, token = _app()
    with TestClient(app) as c:
        groups = c.get("/api/settings/schema", headers=_auth(token)).json()["groups"]
    step = sorted(
        (f for g in groups for f in g["fields"] if f.get("setup_step") == "transcoding"),
        key=lambda f: f["setup_order"],
    )
    assert [f["key"] for f in step] == ["transcode_enabled", "max_parallel_transcodes"]
