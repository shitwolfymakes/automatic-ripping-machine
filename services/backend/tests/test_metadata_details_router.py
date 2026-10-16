"""GET /api/metadata/details (match picker spec 3.4)."""

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
from arm_backend.metadata.sources import build_online_sources  # noqa: E402
from arm_backend.routers import metadata as metadata_router  # noqa: E402
from arm_common import Config, User  # noqa: E402
from arm_common.models.user import GUEST_ROLE  # noqa: E402
from tests._fakes import FakeSession  # noqa: E402

_TVMAZE_SHOW = {
    "id": 1,
    "name": "Kolchak: The Night Stalker",
    "premiered": "1974-09-13",
    "ended": "1975-03-28",
    "summary": "<p>A reporter.</p>",
    "rating": {"average": 8},
    "externals": {"imdb": "tt0071003", "thetvdb": 77170},
    "image": {"medium": "https://static.tvmaze.com/a.jpg"},
    "_embedded": {"cast": [{"person": {"name": "Darren McGavin"}}], "episodes": [{"id": 1}, {"id": 2}]},
}


@pytest.fixture(autouse=True)
def _fresh_cache():
    metadata_router._details_cache.clear()
    yield
    metadata_router._details_cache.clear()


def _client(**keys: str | None) -> tuple[TestClient, dict[str, str], FastAPI]:
    db = FakeSession()
    db.rows["users"] = [
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False),
        # No Authorization header falls back to the guest account; disabled, it 401s.
        User(
            id="usr_guest",
            username="guest",
            password_hash="x",
            password_must_change=False,
            role=GUEST_ROLE,
            disabled=True,
        ),
    ]
    db.rows["config"] = [Config(id=1, musicbrainz_user_agent="arm/test", **keys)]
    key = secrets.token_bytes(32)
    app = FastAPI()
    app.state.signing_key = key
    app.state.http = httpx.AsyncClient(timeout=5.0)
    app.state.online_sources = build_online_sources(app.state.http)
    app.include_router(metadata_router.router)

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override
    token, _ = issue_access_token("usr_admin", "admin", key)
    return TestClient(app), {"Authorization": f"Bearer {token}"}, app


@respx.mock
def test_tvmaze_details_return_full_facts() -> None:
    respx.get("https://api.tvmaze.com/shows/1").mock(return_value=httpx.Response(200, json=_TVMAZE_SHOW))
    client, auth, _ = _client()
    with client:
        r = client.get("/api/metadata/details", params={"provider": "tvmaze", "type": "tv", "id": "1"}, headers=auth)
    assert r.status_code == 200, r.text
    [cand] = r.json()["candidates"]
    assert cand["provider"] == "tvmaze"
    assert cand["external_ids"]["tvmaze"] == "1" and cand["external_ids"]["imdb"] == "tt0071003"
    assert cand["facts"]["cast"] == ["Darren McGavin"] and cand["facts"]["episode_count"] == 2
    assert cand["facts"]["overview"] == "A reporter."


@respx.mock
def test_details_are_cached_per_provider_type_and_id() -> None:
    route = respx.get("https://api.tvmaze.com/shows/1").mock(return_value=httpx.Response(200, json=_TVMAZE_SHOW))
    client, auth, _ = _client()
    params = {"provider": "tvmaze", "type": "tv", "id": "1"}
    with client:
        client.get("/api/metadata/details", params=params, headers=auth)
        r = client.get("/api/metadata/details", params=params, headers=auth)
    assert r.json()["candidates"][0]["title"] == "Kolchak: The Night Stalker"
    assert route.call_count == 1


@respx.mock
def test_details_errors_are_reported_and_not_cached() -> None:
    route = respx.get("https://api.tvmaze.com/shows/1").mock(
        side_effect=[httpx.Response(500), httpx.Response(200, json=_TVMAZE_SHOW)]
    )
    client, auth, _ = _client()
    params = {"provider": "tvmaze", "type": "tv", "id": "1"}
    with client:
        first = client.get("/api/metadata/details", params=params, headers=auth).json()
        second = client.get("/api/metadata/details", params=params, headers=auth).json()
    assert first["candidates"] == [] and "tvmaze" in first["detail"]
    assert len(second["candidates"]) == 1
    assert route.call_count == 2


def test_details_missing_key_is_a_200_with_a_message() -> None:
    client, auth, _ = _client()
    with client:
        r = client.get("/api/metadata/details", params={"provider": "tvdb", "type": "tv", "id": "9"}, headers=auth)
    assert r.status_code == 200
    assert r.json() == {"candidates": [], "detail": "no tvdb key configured"}


@respx.mock
def test_details_transport_error_is_reported() -> None:
    respx.get("https://api.tvmaze.com/shows/1").mock(side_effect=httpx.ConnectError("boom"))
    client, auth, _ = _client()
    with client:
        r = client.get("/api/metadata/details", params={"provider": "tvmaze", "type": "tv", "id": "1"}, headers=auth)
    assert r.json()["candidates"] == [] and r.json()["detail"]


def test_details_bad_params() -> None:
    client, auth, _ = _client(tmdb_api_key="k")
    with client:
        assert (
            client.get(
                "/api/metadata/details", params={"provider": "imdb", "type": "tv", "id": "1"}, headers=auth
            ).status_code
            == 422
        )
        assert (
            client.get(
                "/api/metadata/details", params={"provider": "tvmaze", "type": "movie", "id": "1"}, headers=auth
            ).status_code
            == 400
        )
        assert (
            client.get("/api/metadata/details", params={"provider": "tmdb", "type": "tv"}, headers=auth).status_code
            == 422
        )


@pytest.mark.parametrize("bad", ["1/episodes", "", "a b", "x" * 33])
def test_details_rejects_malformed_id(bad: str) -> None:
    client, auth, _ = _client()
    with client:
        r = client.get("/api/metadata/details", params={"provider": "tvmaze", "type": "tv", "id": bad}, headers=auth)
    assert r.status_code == 422


def test_details_source_without_details_capability_is_400() -> None:
    class _NoDetails:
        id = "tvmaze"
        media_types = frozenset({"tv"})
        requires_key = None

        def configured(self, cfg: Config) -> None:
            return None

    client, auth, app = _client()
    app.state.online_sources = {"tvmaze": _NoDetails()}
    with client:
        r = client.get("/api/metadata/details", params={"provider": "tvmaze", "type": "tv", "id": "1"}, headers=auth)
    assert r.status_code == 400


def test_details_raw_httpx_error_is_reported() -> None:
    class _Raises:
        id = "tvmaze"
        media_types = frozenset({"tv"})
        requires_key = None

        def configured(self, cfg: Config) -> None:
            return None

        async def details(self, cfg: Config, kind: str, provider_id: str) -> None:
            raise httpx.ReadError("dropped")

    client, auth, app = _client()
    app.state.online_sources = {"tvmaze": _Raises()}
    with client:
        r = client.get("/api/metadata/details", params={"provider": "tvmaze", "type": "tv", "id": "1"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["candidates"] == [] and r.json()["detail"].startswith("tvmaze unavailable")


def test_details_requires_auth() -> None:
    client, _, _ = _client()
    with client:
        assert (
            client.get("/api/metadata/details", params={"provider": "tvmaze", "type": "tv", "id": "1"}).status_code
            == 401
        )
