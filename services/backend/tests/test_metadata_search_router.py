"""GET /api/metadata/search, /lookup, /music/search."""

from __future__ import annotations

import os
import secrets
import unittest.mock as mock

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import httpx  # noqa: E402
import pytest  # noqa: E402
import respx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.metadata import musicbrainz as mb_mod  # noqa: E402
from arm_backend.metadata import omdb as omdb_mod  # noqa: E402
from arm_backend.metadata.base import LookupError as MetaLookupError  # noqa: E402
from arm_backend.routers import metadata as metadata_router  # noqa: E402
from arm_common import Config, User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession, **keys: str | None) -> None:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["config"] = [Config(id=1, musicbrainz_user_agent="arm/test", **keys)]


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.http = httpx.AsyncClient(timeout=5.0)
    app.include_router(metadata_router.router)

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


@respx.mock
def test_search_tmdb_returns_candidates(signing_key: bytes) -> None:
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"title": "The Matrix", "release_date": "1999-03-31", "id": 603, "poster_path": "/a.jpg"},
                ]
            },
        )
    )
    db = FakeSession()
    _seed(db, tmdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "matrix", "type": "movie"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    cands = r.json()["candidates"]
    assert cands[0]["title"] == "The Matrix"
    assert cands[0]["poster_url"]


def test_search_no_key_returns_400(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tmdb_api_key=None)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "x", "type": "movie"}, headers=_auth(token))
    assert r.status_code == 400


@respx.mock
def test_search_provider_error_returns_200_empty(signing_key: bytes) -> None:
    respx.get("https://api.themoviedb.org/3/search/movie").mock(side_effect=httpx.ConnectError("down"))
    db = FakeSession()
    _seed(db, tmdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "x", "type": "movie"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"] == []
    assert r.json()["detail"]


def test_search_unknown_type_returns_422(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tmdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "x", "type": "bogus"}, headers=_auth(token))
    assert r.status_code == 422


@respx.mock
def test_lookup_by_imdb_id(signing_key: bytes) -> None:
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(200, json={"Response": "True", "Title": "The Matrix", "Year": "1999"})
    )
    db = FakeSession()
    _seed(db, metadata_provider="omdb", omdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/lookup", params={"imdb_id": "tt0133093"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"][0]["title"] == "The Matrix"


def test_lookup_neither_param_returns_422(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, omdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/lookup", headers=_auth(token))
    assert r.status_code == 422


def test_lookup_both_params_returns_422(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, omdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/lookup", params={"imdb_id": "tt1", "crc64": "abc"}, headers=_auth(token))
    assert r.status_code == 422


@respx.mock
def test_music_search(signing_key: bytes) -> None:
    respx.get("https://musicbrainz.org/ws/2/release").mock(
        return_value=httpx.Response(
            200,
            json={
                "releases": [
                    {"title": "Wish You Were Here", "date": "1975-09-12", "id": "mb-2"},
                ]
            },
        )
    )
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/music/search", params={"query": "wish you were here"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"][0]["title"] == "Wish You Were Here"


def test_search_unauthenticated_401(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, tmdb_api_key="k")
    app, _ = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "x", "type": "movie"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Coverage gap-fillers: crc64 lookup, omdb-provider search, no-omdb-key 400,
# music provider error, search tv path
# ---------------------------------------------------------------------------


@respx.mock
def test_lookup_by_crc64(signing_key: bytes) -> None:
    """ArmServerClient.lookup_by_crc64 path."""
    respx.get("https://1337server.pythonanywhere.com/api/v1/").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "results": {"0": {"title": "Frozen", "year": 2013, "video_type": "movie"}},
            },
        )
    )
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/lookup", params={"crc64": "deadbeef12345678"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"][0]["title"] == "Frozen"


@respx.mock
def test_search_omdb_provider_returns_candidates(signing_key: bytes) -> None:
    """provider=omdb path in search_metadata."""
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={
                "Response": "True",
                "Search": [{"Title": "Blade Runner", "Year": "1982", "imdbID": "tt0083658", "Type": "movie"}],
            },
        )
    )
    db = FakeSession()
    _seed(db, omdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get(
            "/api/metadata/search",
            params={"title": "blade runner", "type": "movie", "provider": "omdb"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    assert r.json()["candidates"][0]["title"] == "Blade Runner"


def test_lookup_imdb_no_omdb_key_returns_400(signing_key: bytes) -> None:
    """imdb_id path with provider=omdb and no omdb key → 400. Must seed
    metadata_provider="omdb" so this exercises the OMDb branch's missing-key
    guard; without it the default ("tmdb") would route to the tmdb branch and
    400 there, leaving the omdb guard untested."""
    db = FakeSession()
    _seed(db, metadata_provider="omdb", omdb_api_key=None)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/lookup", params={"imdb_id": "tt0133093"}, headers=_auth(token))
    assert r.status_code == 400


@respx.mock
def test_music_search_provider_error_returns_200_empty(signing_key: bytes) -> None:
    """MusicBrainz transport error → 200 + empty candidates + detail."""
    respx.get("https://musicbrainz.org/ws/2/release").mock(side_effect=httpx.ConnectError("down"))
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/music/search", params={"query": "something"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"] == []
    assert r.json()["detail"]


@respx.mock
def test_search_tmdb_tv_candidates(signing_key: bytes) -> None:
    """type=tv hits search_tv_candidates."""
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"name": "Breaking Bad", "first_air_date": "2008-01-20", "id": 1396},
                ]
            },
        )
    )
    db = FakeSession()
    _seed(db, tmdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "breaking bad", "type": "tv"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"][0]["title"] == "Breaking Bad"


def test_search_config_not_initialised_returns_400(signing_key: bytes) -> None:
    """No Config row → search_metadata raises 400."""
    db = FakeSession()
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    # no config row
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "x", "type": "movie"}, headers=_auth(token))
    assert r.status_code == 400
    assert "config" in r.json()["detail"].lower()


def test_lookup_config_not_initialised_returns_400(signing_key: bytes) -> None:
    """No Config row → lookup_metadata raises 400."""
    db = FakeSession()
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    # no config row
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/lookup", params={"imdb_id": "tt1"}, headers=_auth(token))
    assert r.status_code == 400
    assert "config" in r.json()["detail"].lower()


@respx.mock
def test_search_httpx_error_returns_200_empty(signing_key: bytes) -> None:
    """httpx.HTTPError escaping the OMDB client → 200 + empty (safety net branch)."""
    db = FakeSession()
    _seed(db, omdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with mock.patch.object(omdb_mod.OMDBClient, "search_candidates", side_effect=httpx.RemoteProtocolError("bad")):
        with TestClient(app) as c:
            r = c.get(
                "/api/metadata/search",
                params={"title": "x", "type": "movie", "provider": "omdb"},
                headers=_auth(token),
            )
    assert r.status_code == 200, r.text
    assert r.json()["candidates"] == []
    assert r.json()["detail"]


@respx.mock
def test_lookup_httpx_error_returns_200_empty(signing_key: bytes) -> None:
    """httpx.HTTPError in lookup_metadata safety net."""
    db = FakeSession()
    _seed(db, metadata_provider="omdb", omdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with mock.patch.object(omdb_mod.OMDBClient, "lookup_by_imdb_id", side_effect=httpx.RemoteProtocolError("bad")):
        with TestClient(app) as c:
            r = c.get("/api/metadata/lookup", params={"imdb_id": "tt1"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"] == []
    assert r.json()["detail"]


def test_music_search_lookup_error_returns_200_empty(signing_key: bytes) -> None:
    """MetaLookupError in search_music → 200 + empty + detail."""
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with mock.patch.object(mb_mod.MusicBrainzClient, "search_releases", side_effect=MetaLookupError("mb down")):
        with TestClient(app) as c:
            r = c.get("/api/metadata/music/search", params={"query": "x"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"] == []
    assert "mb down" in r.json()["detail"]


def test_lookup_lookup_error_returns_200_empty(signing_key: bytes) -> None:
    """MetaLookupError in lookup_metadata → 200 + empty + detail."""
    db = FakeSession()
    _seed(db, metadata_provider="omdb", omdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with mock.patch.object(omdb_mod.OMDBClient, "lookup_by_imdb_id", side_effect=MetaLookupError("omdb miss")):
        with TestClient(app) as c:
            r = c.get("/api/metadata/lookup", params={"imdb_id": "tt1"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"] == []
    assert "omdb miss" in r.json()["detail"]


def test_music_search_httpx_error_returns_200_empty(signing_key: bytes) -> None:
    """httpx.HTTPError in search_music safety net → 200 + empty + detail."""
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with mock.patch.object(mb_mod.MusicBrainzClient, "search_releases", side_effect=httpx.RemoteProtocolError("bad")):
        with TestClient(app) as c:
            r = c.get("/api/metadata/music/search", params={"query": "x"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"] == []
    assert r.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/metadata/music/{release_id} — release detail by MBID
# ---------------------------------------------------------------------------


@respx.mock
def test_music_release_detail_ok(signing_key: bytes) -> None:
    respx.get("https://musicbrainz.org/ws/2/release/mbid-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "mbid-1",
                "title": "The Dark Side of the Moon",
                "date": "1973-03-01",
                "artist-credit": [{"name": "Pink Floyd"}],
                "media": [{"tracks": [{"position": "1", "title": "Speak to Me"}]}],
            },
        )
    )
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/music/mbid-1", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["release_id"] == "mbid-1"
    assert body["title"] == "The Dark Side of the Moon"
    assert body["year"] == 1973
    assert body["artist"] == "Pink Floyd"
    # M5 fix: the detail view must carry the track listing get_release fetched.
    assert len(body["tracks"]) > 0
    assert body["tracks"][0]["title"] == "Speak to Me"
    assert body["tracks"][0]["position"] == 1


# ---------------------------------------------------------------------------
# imdb-id round-trip: TMDb search enrichment + provider-driven lookup
# ---------------------------------------------------------------------------


@respx.mock
def test_search_tmdb_candidates_carry_imdb_id(signing_key: bytes) -> None:
    """TMDb search candidates are enriched with their imdb_id (via external_ids),
    and _to_candidate prefers it: provider_id is the imdb id, not the tmdb id."""
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"id": 1726, "title": "Iron Man", "release_date": "2008-04-30"}]},
        )
    )
    respx.get("https://api.themoviedb.org/3/movie/1726/external_ids").mock(
        return_value=httpx.Response(200, json={"imdb_id": "tt0371746"})
    )
    db = FakeSession()
    _seed(db, metadata_provider="tmdb", tmdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "iron man", "type": "movie"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    cands = r.json()["candidates"]
    assert cands[0]["title"] == "Iron Man"
    assert cands[0]["provider_id"] == "tt0371746"


@respx.mock
def test_search_tmdb_enrichment_failure_is_tolerated(signing_key: bytes) -> None:
    """One candidate's external_ids fetch failing (500) must not fail the whole
    search (200). The failed candidate is NOT enriched with an imdb id — its
    imdb_id stays None, so _to_candidate falls back to the bare tmdb id; the
    other candidate keeps its enriched imdb id."""
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"id": 1726, "title": "Iron Man", "release_date": "2008-04-30"},
                    {"id": 1727, "title": "Iron Man 2", "release_date": "2010-04-28"},
                ]
            },
        )
    )
    respx.get("https://api.themoviedb.org/3/movie/1726/external_ids").mock(
        return_value=httpx.Response(200, json={"imdb_id": "tt0371746"})
    )
    respx.get("https://api.themoviedb.org/3/movie/1727/external_ids").mock(return_value=httpx.Response(500))
    db = FakeSession()
    _seed(db, metadata_provider="tmdb", tmdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "iron man", "type": "movie"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    cands = r.json()["candidates"]
    assert cands[0]["provider_id"] == "tt0371746"
    # Enrichment failed for 1727 → no imdb id; _to_candidate falls back to the
    # tmdb id, and critically it is NOT the failed-but-tolerated imdb value.
    assert cands[1]["provider_id"] == "1727"


@respx.mock
def test_lookup_uses_tmdb_find_when_provider_tmdb(signing_key: bytes) -> None:
    """metadata_provider=tmdb → /lookup?imdb_id resolves via TMDb /find."""
    respx.get("https://api.themoviedb.org/3/find/tt0371746").mock(
        return_value=httpx.Response(
            200,
            json={"movie_results": [{"id": 1726, "title": "Iron Man", "release_date": "2008-04-30"}]},
        )
    )
    db = FakeSession()
    _seed(db, metadata_provider="tmdb", tmdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/lookup", params={"imdb_id": "tt0371746"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"][0]["title"] == "Iron Man"


@respx.mock
def test_lookup_uses_omdb_when_provider_omdb(signing_key: bytes) -> None:
    """metadata_provider=omdb → /lookup?imdb_id resolves via OMDb i=."""
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={
                "Response": "True",
                "Title": "Iron Man",
                "Year": "2008",
                "Type": "movie",
                "imdbID": "tt0371746",
            },
        )
    )
    db = FakeSession()
    _seed(db, metadata_provider="omdb", omdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/lookup", params={"imdb_id": "tt0371746"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"][0]["title"] == "Iron Man"


@respx.mock
def test_music_release_detail_404(signing_key: bytes) -> None:
    """Unknown MBID → upstream 404 → 404."""
    respx.get("https://musicbrainz.org/ws/2/release/missing").mock(return_value=httpx.Response(404))
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/music/missing", headers=_auth(token))
    assert r.status_code == 404, r.text


@respx.mock
def test_music_release_detail_unavailable_502(signing_key: bytes) -> None:
    """Transport failure (collapsed into LookupError by _get) → 502, not 404."""
    respx.get("https://musicbrainz.org/ws/2/release/mbid-1").mock(side_effect=httpx.ConnectError("boom"))
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/music/mbid-1", headers=_auth(token))
    assert r.status_code == 502, r.text
