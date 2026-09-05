"""POST /api/config/keys/{name}/check — per-key live validation probe.

Covers the three live providers (tmdb/omdb/tvdb) against respx-mocked upstream
responses, the missing-key path, the makemkv stored-verdict mapping, and the
guest -> 403 write gate. See the spec brief for exact status/detail mapping.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import httpx  # noqa: E402
import pytest  # noqa: E402
import respx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import config as config_router  # noqa: E402
from arm_common import Config, RetentionPolicy, User  # noqa: E402
from arm_common.models.user import GUEST_ROLE  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402

_TMDB_URL = "https://api.themoviedb.org/3/configuration"
_OMDB_URL = "https://www.omdbapi.com/"
_TVDB_URL = "https://api4.thetvdb.com/v4/login"


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession, **config_keys: object) -> None:
    base: dict[str, object] = dict(
        id=1,
        tmdb_api_key=None,
        omdb_api_key=None,
        tvdb_api_key=None,
        makemkv_key=None,
        musicbrainz_user_agent=None,
        auto_transcode_on_idle=False,
        auto_rip_on_insert=True,
        block_on_miss=True,
        default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
        notification_apprise_urls=[],
        notifications_enabled=False,
    )
    base.update(config_keys)
    db.rows["config"] = [Config(**base)]
    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.http = httpx.AsyncClient(timeout=5.0)
    app.include_router(config_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# tmdb
# ---------------------------------------------------------------------------


def test_tmdb_check_ok(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tmdb_api_key="stored-tmdb-key")
    app, token = _make_app(signing_key, db)
    with respx.mock:
        respx.get(_TMDB_URL).mock(return_value=httpx.Response(200, json={}))
        with TestClient(app) as c:
            r = c.post("/api/config/keys/tmdb/check", json={}, headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "tmdb"
    assert body["status"] == "ok"


def test_tmdb_check_invalid_401(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tmdb_api_key="bad-key")
    app, token = _make_app(signing_key, db)
    with respx.mock:
        respx.get(_TMDB_URL).mock(return_value=httpx.Response(401, json={}))
        with TestClient(app) as c:
            r = c.post("/api/config/keys/tmdb/check", json={}, headers=_auth(token))
    body = r.json()
    assert body["status"] == "invalid"
    assert body["detail"] == "TMDb rejected the key"


def test_tmdb_check_other_status_is_error(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tmdb_api_key="stored-tmdb-key")
    app, token = _make_app(signing_key, db)
    with respx.mock:
        respx.get(_TMDB_URL).mock(return_value=httpx.Response(503, json={}))
        with TestClient(app) as c:
            r = c.post("/api/config/keys/tmdb/check", json={}, headers=_auth(token))
    body = r.json()
    assert body["status"] == "error"
    assert "503" in body["detail"]


def test_tmdb_check_transport_error(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tmdb_api_key="stored-tmdb-key")
    app, token = _make_app(signing_key, db)
    with respx.mock:
        respx.get(_TMDB_URL).mock(side_effect=httpx.ConnectError("boom"))
        with TestClient(app) as c:
            r = c.post("/api/config/keys/tmdb/check", json={}, headers=_auth(token))
    body = r.json()
    assert body["status"] == "error"
    assert "boom" in body["detail"]


def test_tmdb_check_uses_unsaved_value_over_stored(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tmdb_api_key="stored-tmdb-key")
    app, token = _make_app(signing_key, db)
    with respx.mock:
        route = respx.get(_TMDB_URL).mock(return_value=httpx.Response(200, json={}))
        with TestClient(app) as c:
            r = c.post("/api/config/keys/tmdb/check", json={"value": "unsaved-key"}, headers=_auth(token))
    assert r.json()["status"] == "ok"
    assert route.calls.last.request.headers["Authorization"] == "Bearer unsaved-key"


# ---------------------------------------------------------------------------
# omdb
# ---------------------------------------------------------------------------


def test_omdb_check_ok(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, omdb_api_key="stored-omdb-key")
    app, token = _make_app(signing_key, db)
    with respx.mock:
        respx.get(_OMDB_URL).mock(return_value=httpx.Response(200, json={"Response": "True"}))
        with TestClient(app) as c:
            r = c.post("/api/config/keys/omdb/check", json={}, headers=_auth(token))
    assert r.json()["status"] == "ok"


def test_omdb_check_invalid_401(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, omdb_api_key="bad-key")
    app, token = _make_app(signing_key, db)
    with respx.mock:
        respx.get(_OMDB_URL).mock(return_value=httpx.Response(401, json={}))
        with TestClient(app) as c:
            r = c.post("/api/config/keys/omdb/check", json={}, headers=_auth(token))
    assert r.json()["status"] == "invalid"


def test_omdb_check_response_false_is_invalid(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, omdb_api_key="stored-omdb-key")
    app, token = _make_app(signing_key, db)
    with respx.mock:
        respx.get(_OMDB_URL).mock(
            return_value=httpx.Response(200, json={"Response": "False", "Error": "Invalid API key!"})
        )
        with TestClient(app) as c:
            r = c.post("/api/config/keys/omdb/check", json={}, headers=_auth(token))
    body = r.json()
    assert body["status"] == "invalid"
    assert body["detail"] == "Invalid API key!"


def test_omdb_check_other_status_is_error(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, omdb_api_key="stored-omdb-key")
    app, token = _make_app(signing_key, db)
    with respx.mock:
        respx.get(_OMDB_URL).mock(return_value=httpx.Response(503, json={}))
        with TestClient(app) as c:
            r = c.post("/api/config/keys/omdb/check", json={}, headers=_auth(token))
    assert r.json()["status"] == "error"


def test_omdb_check_transport_error(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, omdb_api_key="stored-omdb-key")
    app, token = _make_app(signing_key, db)
    with respx.mock:
        respx.get(_OMDB_URL).mock(side_effect=httpx.ConnectError("boom"))
        with TestClient(app) as c:
            r = c.post("/api/config/keys/omdb/check", json={}, headers=_auth(token))
    assert r.json()["status"] == "error"


def test_omdb_check_non_json_body_is_error(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, omdb_api_key="stored-omdb-key")
    app, token = _make_app(signing_key, db)
    with respx.mock:
        respx.get(_OMDB_URL).mock(return_value=httpx.Response(200, text="<html>not json</html>"))
        with TestClient(app) as c:
            r = c.post("/api/config/keys/omdb/check", json={}, headers=_auth(token))
    body = r.json()
    assert body["status"] == "error"
    assert "non-JSON" in body["detail"]


def test_omdb_check_unexpected_response_shape_is_error(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, omdb_api_key="stored-omdb-key")
    app, token = _make_app(signing_key, db)
    with respx.mock:
        respx.get(_OMDB_URL).mock(return_value=httpx.Response(200, json={"nothing": "useful"}))
        with TestClient(app) as c:
            r = c.post("/api/config/keys/omdb/check", json={}, headers=_auth(token))
    body = r.json()
    assert body["status"] == "error"
    assert body["detail"] == "omdb returned an unexpected response"


# ---------------------------------------------------------------------------
# tvdb
# ---------------------------------------------------------------------------


def test_tvdb_check_ok(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tvdb_api_key="stored-tvdb-key")
    app, token = _make_app(signing_key, db)
    with respx.mock:
        respx.post(_TVDB_URL).mock(return_value=httpx.Response(200, json={}))
        with TestClient(app) as c:
            r = c.post("/api/config/keys/tvdb/check", json={}, headers=_auth(token))
    assert r.json()["status"] == "ok"


def test_tvdb_check_invalid_401(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tvdb_api_key="bad-key")
    app, token = _make_app(signing_key, db)
    with respx.mock:
        respx.post(_TVDB_URL).mock(return_value=httpx.Response(401, json={}))
        with TestClient(app) as c:
            r = c.post("/api/config/keys/tvdb/check", json={}, headers=_auth(token))
    assert r.json()["status"] == "invalid"


def test_tvdb_check_other_status_is_error(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tvdb_api_key="stored-tvdb-key")
    app, token = _make_app(signing_key, db)
    with respx.mock:
        respx.post(_TVDB_URL).mock(return_value=httpx.Response(503, json={}))
        with TestClient(app) as c:
            r = c.post("/api/config/keys/tvdb/check", json={}, headers=_auth(token))
    assert r.json()["status"] == "error"


def test_tvdb_check_transport_error(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tvdb_api_key="stored-tvdb-key")
    app, token = _make_app(signing_key, db)
    with respx.mock:
        respx.post(_TVDB_URL).mock(side_effect=httpx.ConnectError("boom"))
        with TestClient(app) as c:
            r = c.post("/api/config/keys/tvdb/check", json={}, headers=_auth(token))
    body = r.json()
    assert body["status"] == "error"
    assert "boom" in body["detail"]


# ---------------------------------------------------------------------------
# missing key
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["tmdb", "omdb", "tvdb"])
def test_missing_key_no_stored_no_value(signing_key: bytes, name: str) -> None:
    db = FakeSession()
    _seed(db)  # all keys None
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.post(f"/api/config/keys/{name}/check", json={}, headers=_auth(token))
    body = r.json()
    assert body["status"] == "missing"
    assert body["detail"] == "no key set"


def test_missing_key_empty_string_value_falls_back_to_missing(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)  # tmdb_api_key None
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.post("/api/config/keys/tmdb/check", json={"value": ""}, headers=_auth(token))
    body = r.json()
    assert body["status"] == "missing"
    assert body["detail"] == "no key set"


# ---------------------------------------------------------------------------
# makemkv
# ---------------------------------------------------------------------------


def test_makemkv_check_stored_valid(signing_key: bytes) -> None:
    db = FakeSession()
    checked = datetime.now(timezone.utc)
    _seed(db, makemkv_key="M-x", makemkv_key_valid=True, makemkv_key_state="valid")
    db.rows["config"][0].makemkv_key_checked_at = checked
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.post("/api/config/keys/makemkv/check", json={}, headers=_auth(token))
    body = r.json()
    assert body["status"] == "ok"
    assert body["checked_at"] is not None


def test_makemkv_check_stored_invalid(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, makemkv_key="M-x", makemkv_key_valid=False, makemkv_key_state="binary_expired")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.post("/api/config/keys/makemkv/check", json={}, headers=_auth(token))
    body = r.json()
    assert body["status"] == "invalid"
    assert body["detail"]


def test_makemkv_check_unchecked(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, makemkv_key="M-x")  # no valid/state/checked_at
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.post("/api/config/keys/makemkv/check", json={}, headers=_auth(token))
    body = r.json()
    assert body["status"] == "unknown"
    assert body["detail"] == "not checked yet"


def test_makemkv_check_probe_failed(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, makemkv_key="M-x", makemkv_key_state="probe_failed")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.post("/api/config/keys/makemkv/check", json={}, headers=_auth(token))
    body = r.json()
    assert body["status"] == "unknown"
    assert body["detail"] == "probe failed"


def test_makemkv_check_unsaved_value_differs_is_unknown(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, makemkv_key="M-x", makemkv_key_valid=True, makemkv_key_state="valid")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.post("/api/config/keys/makemkv/check", json={"value": "M-different"}, headers=_auth(token))
    body = r.json()
    assert body["status"] == "unknown"
    assert body["detail"] == "save the key; the ripper verifies it before the next rip"


def test_makemkv_check_unsaved_value_same_as_stored_uses_stored_verdict(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, makemkv_key="M-x", makemkv_key_valid=True, makemkv_key_state="valid")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.post("/api/config/keys/makemkv/check", json={"value": "M-x"}, headers=_auth(token))
    body = r.json()
    assert body["status"] == "ok"


def test_makemkv_check_missing_no_stored_key(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)  # makemkv_key None
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.post("/api/config/keys/makemkv/check", json={}, headers=_auth(token))
    body = r.json()
    assert body["status"] == "missing"
    assert body["detail"] == "no key set"


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------


def test_guest_forbidden(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tmdb_api_key="stored-tmdb-key")
    db.rows["users"].append(
        User(id="usr_guest", username="guest", password_hash="x", password_must_change=False, role=GUEST_ROLE)
    )
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.http = httpx.AsyncClient(timeout=5.0)
    app.include_router(config_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_guest", "guest", signing_key)
    with TestClient(app) as c:
        r = c.post("/api/config/keys/tmdb/check", json={}, headers=_auth(token))
    assert r.status_code == 403


def test_unknown_name_is_422(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.post("/api/config/keys/bogus/check", json={}, headers=_auth(token))
    assert r.status_code == 422


def test_missing_singleton_is_500(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["config"] = []
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.post("/api/config/keys/tmdb/check", json={}, headers=_auth(token))
    assert r.status_code == 500
    assert "config singleton missing" in r.json()["detail"]
