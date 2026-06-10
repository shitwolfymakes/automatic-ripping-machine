"""GET /api/metadata/test-key — validate omdb/tmdb/tvdb/makemkv keys."""

from __future__ import annotations

import os
import secrets

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import httpx  # noqa: E402
import pytest  # noqa: E402
import respx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import metadata as metadata_router  # noqa: E402
from arm_common import Config, User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession, **config_keys: str | None) -> None:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["config"] = [Config(id=1, **config_keys)]


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.http = httpx.AsyncClient(timeout=5.0)
    app.include_router(metadata_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@respx.mock
def test_tmdb_valid_key(signing_key: bytes) -> None:
    respx.get("https://api.themoviedb.org/3/configuration").mock(return_value=httpx.Response(200, json={}))
    db = FakeSession()
    _seed(db, tmdb_api_key="good")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/metadata/test-key", params={"provider": "tmdb"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json() == {"provider": "tmdb", "valid": True, "detail": None}


@respx.mock
def test_tmdb_bad_key_returns_200_invalid(signing_key: bytes) -> None:
    respx.get("https://api.themoviedb.org/3/configuration").mock(return_value=httpx.Response(401))
    db = FakeSession()
    _seed(db, tmdb_api_key="bad")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/metadata/test-key", params={"provider": "tmdb"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["valid"] is False
    assert r.json()["detail"]


def test_missing_key_returns_400(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tmdb_api_key=None)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/metadata/test-key", params={"provider": "tmdb"}, headers=_auth(token))
    assert r.status_code == 400


def test_unknown_provider_returns_422(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/metadata/test-key", params={"provider": "nope"}, headers=_auth(token))
    assert r.status_code == 422


def test_makemkv_valid_format(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, makemkv_key="M-abcd1234EFGH")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/metadata/test-key", params={"provider": "makemkv"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["valid"] is True
    assert "rip time" in r.json()["detail"]


def test_makemkv_bad_format_invalid(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, makemkv_key="not-a-serial")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/metadata/test-key", params={"provider": "makemkv"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["valid"] is False


def test_unauthenticated_returns_401(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, _token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/metadata/test-key", params={"provider": "tmdb"})
    assert r.status_code == 401


def test_config_not_initialised_returns_400(signing_key: bytes) -> None:
    """No Config row at all → 400 'config not initialised'."""
    db = FakeSession()
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    # intentionally no config row
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/metadata/test-key", params={"provider": "tmdb"}, headers=_auth(token))
    assert r.status_code == 400
    assert "config" in r.json()["detail"].lower()


def test_makemkv_missing_key_returns_400(signing_key: bytes) -> None:
    """makemkv_key is None → 400 'no makemkv key configured'."""
    db = FakeSession()
    _seed(db, makemkv_key=None)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/metadata/test-key", params={"provider": "makemkv"}, headers=_auth(token))
    assert r.status_code == 400


@respx.mock
def test_omdb_valid_key(signing_key: bytes) -> None:
    """OMDB returns Response:True → valid=True."""
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(200, json={"Response": "True", "Title": "The Matrix"})
    )
    db = FakeSession()
    _seed(db, omdb_api_key="good-omdb-key")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/metadata/test-key", params={"provider": "omdb"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["valid"] is True
    assert r.json()["detail"] is None


@respx.mock
def test_omdb_bad_key_returns_200_invalid(signing_key: bytes) -> None:
    """OMDB returns Response:False + 'Invalid API key!' → valid=False."""
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(200, json={"Response": "False", "Error": "Invalid API key!"})
    )
    db = FakeSession()
    _seed(db, omdb_api_key="bad-omdb-key")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/metadata/test-key", params={"provider": "omdb"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["valid"] is False
    assert "API key" in r.json()["detail"]


@respx.mock
def test_tvdb_valid_key(signing_key: bytes) -> None:
    """TVDB POST /v4/login → 200 means valid=True."""
    respx.post("https://api4.thetvdb.com/v4/login").mock(return_value=httpx.Response(200, json={"status": "success"}))
    db = FakeSession()
    _seed(db, tvdb_api_key="good-tvdb-key")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/metadata/test-key", params={"provider": "tvdb"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["valid"] is True


@respx.mock
def test_tvdb_bad_key_returns_200_invalid(signing_key: bytes) -> None:
    """TVDB POST /v4/login → 401 means valid=False."""
    respx.post("https://api4.thetvdb.com/v4/login").mock(return_value=httpx.Response(401))
    db = FakeSession()
    _seed(db, tvdb_api_key="bad-tvdb-key")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/metadata/test-key", params={"provider": "tvdb"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["valid"] is False


@respx.mock
def test_tmdb_timeout_returns_200_invalid(signing_key: bytes) -> None:
    """httpx.TimeoutException → valid=False, detail='request timed out'."""
    respx.get("https://api.themoviedb.org/3/configuration").mock(side_effect=httpx.ReadTimeout("timed out"))
    db = FakeSession()
    _seed(db, tmdb_api_key="some-key")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/metadata/test-key", params={"provider": "tmdb"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["valid"] is False
    assert "timed out" in r.json()["detail"]


@respx.mock
def test_tmdb_transport_error_returns_200_invalid(signing_key: bytes) -> None:
    """httpx.HTTPError (non-timeout) → valid=False, detail contains 'transport error'."""
    respx.get("https://api.themoviedb.org/3/configuration").mock(side_effect=httpx.ConnectError("refused"))
    db = FakeSession()
    _seed(db, tmdb_api_key="some-key")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/metadata/test-key", params={"provider": "tmdb"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["valid"] is False
    assert "transport error" in r.json()["detail"]


@respx.mock
def test_tvdb_timeout_returns_200_invalid(signing_key: bytes) -> None:
    """TVDB timeout → TVDBClient wraps into LookupTimeout (MetaLookupError) → valid=False."""
    respx.post("https://api4.thetvdb.com/v4/login").mock(side_effect=httpx.TimeoutException("slow"))
    db = FakeSession()
    _seed(db, tvdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/metadata/test-key", params={"provider": "tvdb"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["valid"] is False


@respx.mock
def test_omdb_5xx_returns_200_invalid(signing_key: bytes) -> None:
    """OMDB 5xx with HTML body → status guard raises MetaLookupError → valid=False."""
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(503, text="<html>Service Unavailable</html>")
    )
    db = FakeSession()
    _seed(db, omdb_api_key="some-omdb-key")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/metadata/test-key", params={"provider": "omdb"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["valid"] is False
    assert "503" in r.json()["detail"]
