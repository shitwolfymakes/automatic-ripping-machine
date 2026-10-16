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
from arm_backend.metadata.sources import build_online_sources  # noqa: E402
from arm_backend.routers import metadata as metadata_router  # noqa: E402
from arm_common import Config, User  # noqa: E402
from arm_common.models.user import GUEST_ROLE  # noqa: E402

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
    app.state.online_sources = build_online_sources(app.state.http)
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
    assert r.json()["detail"] == "no tmdb key configured"


def test_search_no_key_names_chosen_provider(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, search_provider_movie="omdb", tmdb_api_key=None, omdb_api_key=None)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "x"}, headers=_auth(token))
    assert r.status_code == 400
    assert r.json()["detail"] == "no omdb key configured"


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
    _seed(db, search_provider_movie="omdb", omdb_api_key="k")
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
    """No Authorization header falls back to the guest account; with guest
    access disabled (the seeded default), the request still 401s before the
    route body (and its outbound metadata-provider call) ever runs."""
    db = FakeSession()
    _seed(db, tmdb_api_key="k")
    db.rows["users"].append(
        User(
            id="usr_guest",
            username="guest",
            password_hash="x",
            password_must_change=False,
            role=GUEST_ROLE,
            disabled=True,
        )
    )
    app, _ = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "x", "type": "movie"})
    assert r.status_code == 401
    assert r.json()["detail"] == "authentication required"


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
def test_search_tv_with_tvdb_provider(signing_key: bytes) -> None:
    respx.post("https://api4.thetvdb.com/v4/login").mock(
        return_value=httpx.Response(200, json={"data": {"token": "t"}})
    )
    respx.get("https://api4.thetvdb.com/v4/search").mock(
        return_value=httpx.Response(200, json={"data": [{"tvdb_id": "73739", "name": "Lost", "year": "2004"}]})
    )
    db = FakeSession()
    _seed(db, tvdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get(
            "/api/metadata/search",
            params={"title": "lost", "type": "tv", "provider": "tvdb"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    cand = r.json()["candidates"][0]
    assert cand["title"] == "Lost" and cand["external_ids"]["tvdb"] == "73739"


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
    """imdb_id path with no key for any listed source → 400 naming the
    provider the operator chose (omdb)."""
    db = FakeSession()
    _seed(db, search_provider_movie="omdb", omdb_api_key=None)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/lookup", params={"imdb_id": "tt0133093"}, headers=_auth(token))
    assert r.status_code == 400
    assert r.json()["detail"] == "no omdb key configured"


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


@respx.mock
def test_tv_search_falls_back_when_the_tv_provider_has_no_adapter(signing_key: bytes) -> None:
    """A row may hold an id the registry does not know (a downgrade, a hand edit); the box falls back to the first usable ranked source."""
    tmdb_route = respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=httpx.Response(
            200, json={"results": [{"name": "Lost", "first_air_date": "2004-09-22", "id": 4607}]}
        )
    )
    db = FakeSession()
    _seed(db, tmdb_api_key="k", search_provider_tv="bogus")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "lost", "type": "tv"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"][0]["title"] == "Lost"
    assert tmdb_route.called


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
    _seed(db, search_provider_movie="omdb", omdb_api_key="k")
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
    _seed(db, search_provider_movie="omdb", omdb_api_key="k")
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
    respx.get("https://api.themoviedb.org/3/movie/1726").mock(
        return_value=httpx.Response(200, json={"id": 1726, "external_ids": {"imdb_id": "tt0371746"}})
    )
    db = FakeSession()
    _seed(db, search_provider_movie="tmdb", tmdb_api_key="k")
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
    respx.get("https://api.themoviedb.org/3/movie/1726").mock(
        return_value=httpx.Response(200, json={"id": 1726, "external_ids": {"imdb_id": "tt0371746"}})
    )
    respx.get("https://api.themoviedb.org/3/movie/1727").mock(return_value=httpx.Response(500))
    db = FakeSession()
    _seed(db, search_provider_movie="tmdb", tmdb_api_key="k")
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
    """search_provider_movie=tmdb → /lookup?imdb_id resolves via TMDb /find."""
    respx.get("https://api.themoviedb.org/3/find/tt0371746").mock(
        return_value=httpx.Response(
            200,
            json={"movie_results": [{"id": 1726, "title": "Iron Man", "release_date": "2008-04-30"}]},
        )
    )
    db = FakeSession()
    _seed(db, search_provider_movie="tmdb", tmdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/lookup", params={"imdb_id": "tt0371746"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"][0]["title"] == "Iron Man"


@respx.mock
def test_lookup_uses_omdb_when_tmdb_unkeyed(signing_key: bytes) -> None:
    """No TMDb key, OMDb keyed → /lookup?imdb_id resolves via OMDb i= (walk)."""
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
    _seed(db, search_provider_movie="omdb", omdb_api_key="k")
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


@respx.mock
def test_music_search_threads_artist_and_track_count(signing_key: bytes) -> None:
    route = respx.get("https://musicbrainz.org/ws/2/release").mock(
        return_value=httpx.Response(200, json={"releases": []})
    )
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get(
            "/api/metadata/music/search",
            params={"query": "abbey road", "artist": "the beatles", "track_count": 17},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    sent = route.calls.last.request.url.params["query"]
    assert "abbey road" in sent
    assert 'artist:"the beatles"' in sent
    assert "tracks:17" in sent


@respx.mock
def test_music_detail_maps_enriched_fields(signing_key: bytes) -> None:
    respx.get("https://musicbrainz.org/ws/2/release/mbid-9").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "mbid-9",
                "title": "Abbey Road",
                "date": "1969-09-26",
                "artist-credit": [{"name": "The Beatles"}],
                "country": "GB",
                "barcode": "0094638246619",
                "status": "Official",
                "label-info": [{"catalog-number": "PCS 7088"}],
                "media": [{"format": "CD", "tracks": [{"position": "1", "title": "Come Together", "length": 259000}]}],
            },
        )
    )
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/music/mbid-9", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["country"] == "GB"
    assert body["barcode"] == "0094638246619"
    assert body["status"] == "Official"
    assert body["catalog_number"] == "PCS 7088"
    assert body["format"] == "CD"
    assert body["disc_count"] == 1
    assert body["track_count"] == 1
    assert body["tracks"][0]["length_ms"] == 259000
    assert body["tracks"][0]["disc_number"] == 1


def _present(ids: dict[str, str | None]) -> dict[str, str]:
    return {k: v for k, v in ids.items() if v is not None}


@respx.mock
def test_tv_search_candidates_carry_all_ids(signing_key: bytes) -> None:
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"id": 5084, "name": "Kolchak: The Night Stalker", "first_air_date": "1974-09-13"}]},
        )
    )
    respx.get("https://api.themoviedb.org/3/tv/5084").mock(
        return_value=httpx.Response(200, json={"id": 5084, "external_ids": {"imdb_id": "tt0071003", "tvdb_id": 77170}})
    )
    db = FakeSession()
    _seed(db, tmdb_api_key="k")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "kolchak", "type": "tv"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    [cand] = r.json()["candidates"]
    assert _present(cand["external_ids"]) == {
        "tmdb": "5084",
        "imdb": "tt0071003",
        "tvdb": "77170",
        "tmdb_kind": "tv",
    }


@respx.mock
def test_omdb_candidates_carry_imdb_without_tmdb_kind(signing_key: bytes) -> None:
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
    [cand] = r.json()["candidates"]
    assert _present(cand["external_ids"]) == {"imdb": "tt0083658"}


def test_search_provider_literal_matches_registry() -> None:
    """One spelling of the movie/TV source ids (spec S-8): the OpenAPI enum
    and the registry cannot drift apart."""
    from typing import get_args

    from arm_backend.identity.sources.registry import known_source_ids

    reg = build_online_sources(httpx.AsyncClient())
    assert set(get_args(metadata_router.SearchProvider)) == set(known_source_ids("movie", reg)) | set(
        known_source_ids("tv", reg)
    )


def test_key_check_map_matches_registry_requires_key() -> None:
    """The key-check route's name -> Config attribute map (routers/config.py
    `_KEY_ATTR`) must agree with each keyed source's `requires_key`, so the
    Keys tab checks the same key the source reads."""
    from arm_backend.routers.config import _KEY_ATTR

    reg = build_online_sources(httpx.AsyncClient())
    for sid, source in reg.items():
        if source.requires_key is not None:
            assert _KEY_ATTR[sid] == source.requires_key, sid


@respx.mock
def test_search_provider_omdb_without_key_makes_no_call(signing_key: bytes) -> None:
    omdb_route = respx.get("https://www.omdbapi.com/").mock(return_value=httpx.Response(200, json={}))
    db = FakeSession()
    _seed(db, tmdb_api_key="k", omdb_api_key=None)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "x", "provider": "omdb"}, headers=_auth(token))
    assert r.status_code == 400 and r.json()["detail"] == "no omdb key configured"
    assert not omdb_route.called


@respx.mock
def test_search_default_provider_is_first_configured_source(signing_key: bytes) -> None:
    """No `provider` param and no TMDb key: the first usable listed source (OMDb) answers."""
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={
                "Response": "True",
                "Search": [{"Title": "Heat", "Year": "1995", "imdbID": "tt0113277", "Type": "movie"}],
            },
        )
    )
    db = FakeSession()
    _seed(db, tmdb_api_key=None, omdb_api_key="k", search_provider_movie="tmdb")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "heat"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"][0]["title"] == "Heat"


@respx.mock
def test_lookup_imdb_walks_to_omdb_when_tmdb_unkeyed(signing_key: bytes) -> None:
    """/lookup?imdb_id tries the listed sources in order; with no TMDb key,
    OMDb `i=` answers (today's search_provider_movie=omdb behaviour, now by walk)."""
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200, json={"Response": "True", "Title": "Heat", "Year": "1995", "Type": "movie", "imdbID": "tt0113277"}
        )
    )
    db = FakeSession()
    _seed(db, tmdb_api_key=None, omdb_api_key="k", search_provider_movie="omdb")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/lookup", params={"imdb_id": "tt0113277"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"][0]["title"] == "Heat"


@respx.mock
def test_search_default_provider_honours_search_provider_movie(signing_key: bytes) -> None:
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={
                "Response": "True",
                "Search": [{"Title": "Heat", "Year": "1995", "imdbID": "tt0113277", "Type": "movie"}],
            },
        )
    )
    tmdb_route = respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(200, json={}))
    db = FakeSession()
    _seed(db, tmdb_api_key="k", omdb_api_key="k", search_provider_movie="omdb")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "heat"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"][0]["title"] == "Heat"
    assert not tmdb_route.called


@respx.mock
def test_lookup_prefers_search_provider_movie_when_both_keyed(signing_key: bytes) -> None:
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200, json={"Response": "True", "Title": "Heat", "Year": "1995", "Type": "movie", "imdbID": "tt0113277"}
        )
    )
    tmdb_route = respx.get(url__startswith="https://api.themoviedb.org/3/find/").mock(
        return_value=httpx.Response(200, json={})
    )
    db = FakeSession()
    _seed(db, tmdb_api_key="k", omdb_api_key="k", search_provider_movie="omdb")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/lookup", params={"imdb_id": "tt0113277"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"][0]["title"] == "Heat"
    assert not tmdb_route.called


@respx.mock
def test_search_tv_with_tvmaze_provider(signing_key: bytes) -> None:
    route = respx.get("https://api.tvmaze.com/search/shows").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "score": 1,
                    "show": {
                        "id": 4607,
                        "name": "Lost",
                        "premiered": "2004-09-22",
                        "externals": {"imdb": "tt0411008", "thetvdb": 73739},
                        "image": {"medium": "https://static.tvmaze.com/l.jpg"},
                    },
                }
            ],
        )
    )
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get(
            "/api/metadata/search",
            params={"title": "lost", "type": "tv", "provider": "tvmaze"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    cand = r.json()["candidates"][0]
    assert cand["title"] == "Lost" and cand["poster_url"] == "https://static.tvmaze.com/l.jpg"
    assert cand["external_ids"]["tvmaze"] == "4607" and cand["external_ids"]["imdb"] == "tt0411008"
    assert route.called


def test_search_rejects_a_provider_that_does_not_serve_the_type(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get(
            "/api/metadata/search",
            params={"title": "x", "type": "movie", "provider": "tvmaze"},
            headers=_auth(token),
        )
    assert r.status_code == 400 and r.json()["detail"] == "tvmaze does not search movie"


@respx.mock
def test_search_default_tv_provider_tvmaze_without_tmdb_key(signing_key: bytes) -> None:
    respx.get("https://api.tvmaze.com/search/shows").mock(
        return_value=httpx.Response(
            200, json=[{"score": 1, "show": {"id": 1, "name": "Lost", "externals": {}, "image": None}}]
        )
    )
    db = FakeSession()
    _seed(db, tmdb_api_key=None, search_provider_tv="tvmaze")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "lost", "type": "tv"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"][0]["title"] == "Lost"


@respx.mock
def test_search_tv_uses_omdb_although_episode_sources_omit_it(signing_key: bytes) -> None:
    """The Search card is independent of Online lookup: OMDb is never in
    `episode_sources`, yet `search_provider_tv=omdb` serves the TV search box."""
    route = respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={
                "Response": "True",
                "Search": [{"Title": "Lost", "Year": "2004", "imdbID": "tt0411008", "Type": "series"}],
            },
        )
    )
    db = FakeSession()
    _seed(db, omdb_api_key="k", search_provider_tv="omdb", episode_sources=["tmdb", "tvmaze", "tvdb"])
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "lost", "type": "tv"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert route.called
    assert r.json()["candidates"][0]["title"] == "Lost"


@respx.mock
def test_search_candidates_carry_provider_and_facts(signing_key: bytes) -> None:
    respx.get("https://api.tvmaze.com/search/shows").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "show": {
                        "id": 1,
                        "name": "Kolchak",
                        "premiered": "1974-09-13",
                        "ended": "1975-03-28",
                        "rating": {"average": 8},
                        "genres": ["Horror"],
                    }
                }
            ],
        )
    )
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get(
            "/api/metadata/search",
            params={"title": "kolchak", "type": "tv", "provider": "tvmaze"},
            headers=_auth(token),
        )
    cand = r.json()["candidates"][0]
    assert cand["provider"] == "tvmaze"
    assert (
        cand["facts"]["end_year"] == 1975 and cand["facts"]["rating"] == 8.0 and cand["facts"]["genres"] == ["Horror"]
    )


@respx.mock
def test_search_year_sorts_nearest_first_and_drops_nothing(signing_key: bytes) -> None:
    shows = [
        {"show": {"id": 1, "name": "Night Stalker", "premiered": "2005-09-29"}},
        {"show": {"id": 2, "name": "No Year"}},
        {"show": {"id": 3, "name": "Kolchak", "premiered": "1974-09-13"}},
        {"show": {"id": 4, "name": "The Night Stalker", "premiered": "1972-01-11"}},
        {"show": {"id": 5, "name": "Also 1974", "premiered": "1974-01-01"}},
    ]
    route = respx.get("https://api.tvmaze.com/search/shows").mock(return_value=httpx.Response(200, json=shows))
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get(
            "/api/metadata/search",
            params={"title": "night stalker", "type": "tv", "provider": "tvmaze", "year": 1974},
            headers=_auth(token),
        )
    titles = [c["title"] for c in r.json()["candidates"]]
    assert titles == ["Kolchak", "Also 1974", "The Night Stalker", "Night Stalker", "No Year"]
    assert "year" not in route.calls.last.request.url.params


@respx.mock
def test_search_without_year_keeps_provider_order(signing_key: bytes) -> None:
    respx.get("https://api.tvmaze.com/search/shows").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"show": {"id": 1, "name": "B", "premiered": "2005-01-01"}},
                {"show": {"id": 2, "name": "A", "premiered": "1974-01-01"}},
            ],
        )
    )
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get(
            "/api/metadata/search", params={"title": "x", "type": "tv", "provider": "tvmaze"}, headers=_auth(token)
        )
    assert [c["title"] for c in r.json()["candidates"]] == ["B", "A"]
