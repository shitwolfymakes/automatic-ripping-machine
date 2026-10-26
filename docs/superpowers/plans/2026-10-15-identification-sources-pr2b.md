# Identification Sources PR 2b: TVmaze and TVDB Title Search — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give TVmaze and TVDB a title search so the operator's TV list (`episode_sources`) drives real TV identification, the job page's TV search box can use them, and a hit from any source gets its missing ids filled from the others.

**Architecture:** Two thin HTTP clients (`metadata/tvmaze.py`, and TV-search methods on the existing `metadata/tvdb.py`) normalise their responses into `MetadataResult` payloads that carry `imdb_id`, `tvdb_id`, `tvmaze_id` and a full `poster_url`. Two adapters (`TvmazeSource`, `TvdbSource`) in `metadata/sources.py` expose `search_title`, `search_candidates` and `lookup_imdb` for the `tv` media type only; `build_online_sources` registers them, so `sources_for(cfg, "tv", …)` stops skipping them and the TV search select may offer them. `external_ids_of` learns the TVmaze and TVDB id fields and `extract_poster_url` accepts a generic `poster_url`. The dispatcher's TMDb-only enrichment becomes `fill_external_ids`: a TMDb hit keeps today's `external_ids` call; a non-TMDb hit with an IMDb id asks the TMDb adapter for the TMDb id so the episode stage can use every provider. The TV search provider enum and the `SearchProvider` wire literal gain the two ids, which regenerates the OpenAPI snapshot and the TypeScript types.

**Tech Stack:** Python 3.14, httpx, pytest with `respx` and fake sources, ruff 0.15.11 via pre-commit, mypy; `bash devtools/regen-openapi-snapshot.sh` and `bash services/ui-neu/scripts/codegen.sh`; SvelteKit types only on the UI side (`searchMetadata`'s provider type).

**Spec:** `docs/superpowers/specs/2026-10-14-identification-sources-design.md` (S-10, §5.1 adapters, §5.3, §6 PR 2b, §10). Branch: `feat/identification-sources-pr2b` from `feat/identification-sources-pr2` (PR #363).

## Global Constraints

- Source ids `tvmaze` (keyless, `requires_key=None`) and `tvdb` (`requires_key="tvdb_api_key"`); `media_types = frozenset({"tv"})` for both. Their `search_title` returns `None` for `kind == "movie"` without an HTTP call.
- TVmaze endpoints (base `settings.ARM_TVMAZE_BASE_URL`, default `https://api.tvmaze.com`): `GET /singlesearch/shows?q=<title>` (one show or 404), `GET /search/shows?q=<title>` (list of `{score, show}`), `GET /lookup/shows?imdb=<id>` (one show or 404, follows redirects). A show maps to `MetadataResult(title=show["name"], year=int(show["premiered"][:4]) if present, kind="tv", payload={…show, "tvmaze_id": str(show["id"]), "imdb_id": show["externals"]["imdb"], "tvdb_id": str(show["externals"]["thetvdb"]), "poster_url": show["image"]["medium"]})`, each id key present only when the value is set.
- TVDB v4 endpoints (base `settings.ARM_TVDB_BASE_URL`): `POST /login {"apikey"}` → `data.token`; `GET /search?query=<title>&type=series` → `data: [{tvdb_id, name, year, image_url, remote_ids: [{id, sourceName}]}]`; `GET /search/remoteid/<imdb>` → `data: [{series: {id, name, year, image}}]`. A series maps to `MetadataResult(title=name, year=int(year) if digits, kind="tv", payload={…entry, "tvdb_id": str(id), "imdb_id": <remote id whose sourceName is "IMDB", when present>, "poster_url": image_url or image})`. The bearer token is cached per client instance for the process lifetime of that instance (clients are built per call, so one login per call; acceptable for a search box and identify).
- Clients raise `LookupError` on a miss / non-200 / malformed body and `LookupTimeout` on timeout, like the TMDb and OMDb clients; they never return `None`.
- `external_ids_of`: `tvmaze = payload["tvmaze_id"]` or `payload["id"]` when provider is `tvmaze`; `tvdb = payload["tvdb_id"]` or `payload["id"]` when provider is `tvdb`. `extract_poster_url`: after the OMDb branch, a `payload["poster_url"]` that is a string starting with `http` is returned.
- `fill_external_ids(hit, cfg)` replaces `_with_tmdb_ids`: (1) a `tmdb` hit with a payload `id` → TMDb `external_ids` fills `imdb_id` / `tvdb_id` (today's behaviour, same tests); (2) any other `movie`/`tv` hit with an `imdb_id` and no `tmdb_id`, when the `tmdb` source is configured → the tmdb adapter's `lookup_imdb`; if its result has the same kind, set `payload["tmdb_id"] = str(result.payload["id"])` and fill `tvdb_id` from that result's payload when absent. Both bounded by `PROVIDER_TIMEOUT_SECONDS`; a failure, timeout or `LookupError` changes nothing. Ids already in the payload always win.
- `search_provider_tv` enum values `["tmdb", "omdb", "tvmaze", "tvdb"]`, labels, `enum_requires` tmdb/omdb/tvdb; `ONLINE_SOURCE_VALUES["tv"]` the same; `SearchProvider = Literal["tmdb", "omdb", "tvmaze", "tvdb"]`; `/search` rejects a provider that does not serve the requested type with 400 `{provider} does not search {type}`. `episode_sources` is unchanged.
- OpenAPI snapshot and `api.gen.ts` regenerated and committed; UI `searchMetadata(query, type?, provider?)` provider type widened; no other UI change.
- No migration. Error strings elsewhere unchanged. Tests zero-infra (respx for clients, fakes for the dispatcher). Commits carry no attribution trailers.

## Review Focus

1. A TVmaze `singlesearch` 404 for an unknown title must surface as a `LookupError` that the dispatcher's `_call` swallows, so the walk moves to the next source (Task 1 client test + Task 3 adapter test through `_call`).
2. A TVDB 401 after the token expired mid-process must not leave a stale token: the client re-logs in once and otherwise raises `LookupError` (Task 2 test).
3. A TVmaze hit for a show with no `externals.imdb` must still be a valid result (no `imdb_id` key, `fill_external_ids` leaves it alone) and the episode stage can resolve via `tvmaze` (Task 1 mapping test; Task 3 `external_ids_of` test).
4. `/search?type=movie&provider=tvmaze` must be a 400, never a TVmaze call (Task 5 router test).
5. An operator whose TV list is `tvmaze, tmdb` with no TMDb key gets a TVmaze hit, and `fill_external_ids` must not call TMDb (unconfigured) — the walk and the fill both respect `configured` (Task 4 test).

---

### Task 1: TVmaze client

**Files:**
- Create: `services/backend/arm_backend/metadata/tvmaze.py`
- Test: `services/backend/tests/test_metadata_clients_tvmaze.py`

**Interfaces:**
- Produces: `TVMazeClient(http)` with `async search_show(title) -> MetadataResult`, `async search_candidates(title, limit=10) -> list[MetadataResult]`, `async lookup_by_imdb_id(imdb_id) -> MetadataResult`; module function `show_to_result(show: dict) -> MetadataResult | None`.

- [ ] **Step 1: Write the failing tests**

```python
"""TVmaze title-search client (PR 2b). respx-mocked; no network."""

import httpx
import pytest
import respx

from arm_backend.metadata.base import LookupError, LookupTimeout
from arm_backend.metadata.tvmaze import TVMazeClient, show_to_result

_BASE = "https://api.tvmaze.com"
_SHOW = {
    "id": 4607,
    "name": "Lost",
    "premiered": "2004-09-22",
    "externals": {"tvrage": 2600, "thetvdb": 73739, "imdb": "tt0411008"},
    "image": {"medium": "https://static.tvmaze.com/uploads/images/medium_portrait/1/2.jpg"},
}


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client


def test_show_to_result_maps_ids_year_and_poster():
    result = show_to_result(_SHOW)
    assert result is not None
    assert (result.title, result.year, result.kind) == ("Lost", 2004, "tv")
    assert result.payload["tvmaze_id"] == "4607"
    assert result.payload["imdb_id"] == "tt0411008"
    assert result.payload["tvdb_id"] == "73739"
    assert result.payload["poster_url"].startswith("https://static.tvmaze.com/")


def test_show_to_result_tolerates_missing_fields():
    result = show_to_result({"id": 1, "name": "Untitled", "externals": {"imdb": None}, "image": None})
    assert result is not None and result.year is None
    assert "imdb_id" not in result.payload and "tvdb_id" not in result.payload and "poster_url" not in result.payload
    assert show_to_result({"id": 2}) is None  # no name
    assert show_to_result("not a dict") is None


@respx.mock
async def test_search_show_uses_singlesearch(http_client):
    route = respx.get(f"{_BASE}/singlesearch/shows").mock(return_value=httpx.Response(200, json=_SHOW))
    result = await TVMazeClient(http_client).search_show("lost")
    assert result.title == "Lost" and result.payload["tvmaze_id"] == "4607"
    assert route.calls.last.request.url.params["q"] == "lost"


@respx.mock
async def test_search_show_404_is_a_lookup_error(http_client):
    respx.get(f"{_BASE}/singlesearch/shows").mock(return_value=httpx.Response(404, json={"name": "Not Found"}))
    with pytest.raises(LookupError):
        await TVMazeClient(http_client).search_show("nothing here")


@respx.mock
async def test_search_candidates_unwraps_show_entries(http_client):
    respx.get(f"{_BASE}/search/shows").mock(
        return_value=httpx.Response(200, json=[{"score": 1.0, "show": _SHOW}, {"score": 0.5, "show": {"id": 9}}])
    )
    results = await TVMazeClient(http_client).search_candidates("lost", limit=5)
    assert [r.title for r in results] == ["Lost"]


@respx.mock
async def test_lookup_by_imdb_id_follows_redirects(http_client):
    respx.get(f"{_BASE}/lookup/shows").mock(return_value=httpx.Response(200, json=_SHOW))
    result = await TVMazeClient(http_client).lookup_by_imdb_id("tt0411008")
    assert result.payload["imdb_id"] == "tt0411008"
    assert respx.calls.last.request.url.params["imdb"] == "tt0411008"


@respx.mock
async def test_timeout_and_transport_errors(http_client):
    respx.get(f"{_BASE}/singlesearch/shows").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(LookupTimeout):
        await TVMazeClient(http_client).search_show("lost")
    respx.get(f"{_BASE}/search/shows").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(LookupError):
        await TVMazeClient(http_client).search_candidates("lost")
    respx.get(f"{_BASE}/lookup/shows").mock(return_value=httpx.Response(500))
    with pytest.raises(LookupError):
        await TVMazeClient(http_client).lookup_by_imdb_id("tt1")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest services/backend/tests/test_metadata_clients_tvmaze.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError: No module named 'arm_backend.metadata.tvmaze'`.

- [ ] **Step 3: Write the client**

```python
"""TVmaze title search (PR 2b). Keyless; TVmaze asks for at most 20
requests per 10 s, which a search box and identify stay well under.
Episode listing lives in identity/episodes/providers/tvmaze.py."""

import logging
from typing import Any

import httpx

from arm_backend.config import settings
from arm_backend.metadata.base import LookupError, LookupTimeout, MetadataResult

logger = logging.getLogger("arm_backend.metadata.tvmaze")


def _base_url() -> str:
    return settings.ARM_TVMAZE_BASE_URL


def show_to_result(show: Any) -> MetadataResult | None:
    """One TVmaze show object → MetadataResult, or None without a name.
    Ids and the poster are normalised into the keys `external_ids_of` and
    `extract_poster_url` read; the raw object is kept alongside."""
    if not isinstance(show, dict):
        return None
    name = show.get("name")
    if not isinstance(name, str) or not name:
        return None
    premiered = show.get("premiered") or ""
    year = int(premiered[:4]) if isinstance(premiered, str) and premiered[:4].isdigit() else None
    payload: dict[str, Any] = dict(show)
    if show.get("id") is not None:
        payload["tvmaze_id"] = str(show["id"])
    externals = show.get("externals") if isinstance(show.get("externals"), dict) else {}
    imdb = externals.get("imdb")
    if isinstance(imdb, str) and imdb:
        payload["imdb_id"] = imdb
    tvdb = externals.get("thetvdb")
    if isinstance(tvdb, int) or (isinstance(tvdb, str) and tvdb):
        payload["tvdb_id"] = str(tvdb)
    image = show.get("image") if isinstance(show.get("image"), dict) else {}
    poster = image.get("medium") or image.get("original")
    if isinstance(poster, str) and poster.startswith("http"):
        payload["poster_url"] = poster
    return MetadataResult(title=name, year=year, kind="tv", payload=payload)


class TVMazeClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        try:
            r = await self._http.get(f"{_base_url()}{path}", params=params, follow_redirects=True)
        except httpx.TimeoutException as e:
            raise LookupTimeout("tvmaze timeout") from e
        except httpx.HTTPError as e:
            raise LookupError(f"tvmaze transport error: {e}") from e
        if r.status_code == 404:
            raise LookupError("tvmaze miss")
        if r.status_code != 200:
            raise LookupError(f"tvmaze status={r.status_code}")
        try:
            return r.json()
        except ValueError as e:
            raise LookupError("tvmaze malformed response") from e

    async def search_show(self, title: str) -> MetadataResult:
        result = show_to_result(await self._get("/singlesearch/shows", {"q": title}))
        if result is None:
            raise LookupError("tvmaze hit missing name")
        return result

    async def search_candidates(self, title: str, limit: int = 10) -> list[MetadataResult]:
        body = await self._get("/search/shows", {"q": title})
        if not isinstance(body, list):
            raise LookupError("tvmaze malformed response")
        out: list[MetadataResult] = []
        for entry in body:
            result = show_to_result(entry.get("show") if isinstance(entry, dict) else None)
            if result is not None:
                out.append(result)
            if len(out) >= limit:
                break
        return out

    async def lookup_by_imdb_id(self, imdb_id: str) -> MetadataResult:
        result = show_to_result(await self._get("/lookup/shows", {"imdb": imdb_id}))
        if result is None:
            raise LookupError("tvmaze lookup missing name")
        return result
```

- [ ] **Step 4: Run, lint, commit**

Run: `uv run pytest services/backend/tests/test_metadata_clients_tvmaze.py -q -p no:cacheprovider && uv run pre-commit run ruff --files services/backend/arm_backend/metadata/tvmaze.py services/backend/tests/test_metadata_clients_tvmaze.py && uv run pre-commit run ruff-format --files services/backend/arm_backend/metadata/tvmaze.py services/backend/tests/test_metadata_clients_tvmaze.py && uv run mypy services/backend/arm_backend/metadata/tvmaze.py`
Expected: 8 passed; clean.

```bash
git add services/backend/arm_backend/metadata/tvmaze.py services/backend/tests/test_metadata_clients_tvmaze.py
git commit -m "feat(metadata): TVmaze title-search client"
```

---

### Task 2: TVDB title search on the existing client

**Files:**
- Modify: `services/backend/arm_backend/metadata/tvdb.py`
- Test: `services/backend/tests/test_metadata_clients_tvdb.py`

**Interfaces:**
- Produces on `TVDBClient`: `async search_series(title) -> MetadataResult`, `async search_candidates(title, limit=10) -> list[MetadataResult]`, `async lookup_by_imdb_id(imdb_id) -> MetadataResult`; module function `series_to_result(entry: dict) -> MetadataResult | None`. `validate_key` unchanged.

- [ ] **Step 1: Write the failing tests**

```python
"""TVDB v4 title-search methods (PR 2b). respx-mocked; no network."""

import httpx
import pytest
import respx

from arm_backend.metadata.base import LookupError, LookupTimeout
from arm_backend.metadata.tvdb import TVDBClient, series_to_result

_BASE = "https://api4.thetvdb.com/v4"
_LOGIN = {"status": "success", "data": {"token": "tok-1"}}
_ENTRY = {
    "tvdb_id": "73739",
    "name": "Lost",
    "year": "2004",
    "image_url": "https://artworks.thetvdb.com/banners/posters/73739-1.jpg",
    "remote_ids": [{"id": "tt0411008", "type": 2, "sourceName": "IMDB"}],
}


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client


def test_series_to_result_maps_ids_year_and_poster():
    result = series_to_result(_ENTRY)
    assert result is not None
    assert (result.title, result.year, result.kind) == ("Lost", 2004, "tv")
    assert result.payload["tvdb_id"] == "73739"
    assert result.payload["imdb_id"] == "tt0411008"
    assert result.payload["poster_url"].startswith("https://artworks.thetvdb.com/")
    assert series_to_result({"tvdb_id": "1"}) is None  # no name
    # The remoteid shape nests the series under "series" with "id" and "image".
    nested = series_to_result({"id": 73739, "name": "Lost", "year": "2004", "image": "https://x/y.jpg"})
    assert nested is not None and nested.payload["tvdb_id"] == "73739" and nested.payload["poster_url"] == "https://x/y.jpg"


@respx.mock
async def test_search_series_logs_in_then_searches(http_client):
    login = respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json=_LOGIN))
    search = respx.get(f"{_BASE}/search").mock(return_value=httpx.Response(200, json={"data": [_ENTRY]}))
    client = TVDBClient("key", http_client)
    result = await client.search_series("lost")
    assert result.title == "Lost"
    assert login.call_count == 1
    assert search.calls.last.request.headers["Authorization"] == "Bearer tok-1"
    assert search.calls.last.request.url.params["type"] == "series"
    # A second call on the same client reuses the token.
    await client.search_series("lost again")
    assert login.call_count == 1


@respx.mock
async def test_search_series_relogs_in_once_on_401(http_client):
    respx.post(f"{_BASE}/login").mock(
        side_effect=[httpx.Response(200, json=_LOGIN), httpx.Response(200, json={"data": {"token": "tok-2"}})]
    )
    search = respx.get(f"{_BASE}/search").mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json={"data": [_ENTRY]})]
    )
    result = await TVDBClient("key", http_client).search_series("lost")
    assert result.title == "Lost"
    assert search.calls[1].request.headers["Authorization"] == "Bearer tok-2"


@respx.mock
async def test_search_series_second_401_is_a_lookup_error(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json=_LOGIN))
    respx.get(f"{_BASE}/search").mock(return_value=httpx.Response(401))
    with pytest.raises(LookupError):
        await TVDBClient("key", http_client).search_series("lost")


@respx.mock
async def test_search_series_empty_data_is_a_miss(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json=_LOGIN))
    respx.get(f"{_BASE}/search").mock(return_value=httpx.Response(200, json={"data": []}))
    with pytest.raises(LookupError):
        await TVDBClient("key", http_client).search_series("nothing")


@respx.mock
async def test_search_candidates_and_limit(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json=_LOGIN))
    respx.get(f"{_BASE}/search").mock(return_value=httpx.Response(200, json={"data": [_ENTRY, {**_ENTRY, "name": "Lost 2"}]}))
    results = await TVDBClient("key", http_client).search_candidates("lost", limit=1)
    assert [r.title for r in results] == ["Lost"]


@respx.mock
async def test_lookup_by_imdb_id_uses_remoteid(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json=_LOGIN))
    respx.get(f"{_BASE}/search/remoteid/tt0411008").mock(
        return_value=httpx.Response(200, json={"data": [{"series": {"id": 73739, "name": "Lost", "year": "2004"}}]})
    )
    result = await TVDBClient("key", http_client).lookup_by_imdb_id("tt0411008")
    assert result.payload["tvdb_id"] == "73739" and result.payload["imdb_id"] == "tt0411008"


@respx.mock
async def test_login_failure_and_timeout(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(401))
    with pytest.raises(LookupError):
        await TVDBClient("bad", http_client).search_series("lost")
    respx.post(f"{_BASE}/login").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(LookupTimeout):
        await TVDBClient("key", http_client).search_series("lost")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest services/backend/tests/test_metadata_clients_tvdb.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'series_to_result'`.

- [ ] **Step 3: Extend the client**

Replace the class docstring's "Tier-1 scope: key validation only" sentence with "Key validation plus TV title search (PR 2b); episode listing lives in identity/episodes/providers/tvdb.py." Add `from typing import Any`, `from urllib.parse import quote` and `MetadataResult` to the imports, and add:

```python
def series_to_result(entry: Any) -> MetadataResult | None:
    """One TVDB search entry (or the `series` object of a remoteid result)
    → MetadataResult, or None without a name."""
    if not isinstance(entry, dict):
        return None
    name = entry.get("name")
    if not isinstance(name, str) or not name:
        return None
    raw_year = entry.get("year")
    year = int(str(raw_year)[:4]) if raw_year is not None and str(raw_year)[:4].isdigit() else None
    payload: dict[str, Any] = dict(entry)
    tvdb_id = entry.get("tvdb_id") or entry.get("id")
    if tvdb_id is not None and str(tvdb_id):
        payload["tvdb_id"] = str(tvdb_id)
    for remote in entry.get("remote_ids") or []:
        if isinstance(remote, dict) and str(remote.get("sourceName", "")).upper() == "IMDB" and remote.get("id"):
            payload["imdb_id"] = str(remote["id"])
            break
    poster = entry.get("image_url") or entry.get("image")
    if isinstance(poster, str) and poster.startswith("http"):
        payload["poster_url"] = poster
    return MetadataResult(title=name, year=year, kind="tv", payload=payload)
```

and on `TVDBClient` (keep `validate_key` as it is; refactor its login body into `_login` so both share it):

```python
    _token: str | None = None

    async def _login(self) -> str:
        try:
            r = await self._http.post(f"{_base_url()}/login", json={"apikey": self._api_key})
        except httpx.TimeoutException as e:
            raise LookupTimeout("tvdb login timeout") from e
        except httpx.HTTPError as e:
            raise LookupError(f"tvdb login transport error: {e}") from e
        if r.status_code == 401:
            logger.warning("tvdb auth_failed status=401")
            raise LookupError("tvdb auth failed")
        if r.status_code >= 500:
            raise LookupError(f"tvdb login 5xx status={r.status_code}")
        if r.status_code != 200:
            raise LookupError(f"tvdb login status={r.status_code}")
        try:
            token = r.json()["data"]["token"]
        except (ValueError, KeyError, TypeError) as e:
            raise LookupError("tvdb login malformed response") from e
        if not isinstance(token, str) or not token:
            raise LookupError("tvdb login returned no token")
        self._token = token
        return token

    async def _get_authed(self, path: str, params: dict[str, Any] | None = None) -> Any:
        token = self._token or await self._login()
        for attempt in (1, 2):
            try:
                r = await self._http.get(
                    f"{_base_url()}{path}", params=params, headers={"Authorization": f"Bearer {token}"}
                )
            except httpx.TimeoutException as e:
                raise LookupTimeout("tvdb timeout") from e
            except httpx.HTTPError as e:
                raise LookupError(f"tvdb transport error: {e}") from e
            if r.status_code == 401 and attempt == 1:
                token = await self._login()  # expired token: one re-login
                continue
            if r.status_code == 404:
                raise LookupError("tvdb miss")
            if r.status_code != 200:
                raise LookupError(f"tvdb status={r.status_code}")
            try:
                return r.json()
            except ValueError as e:
                raise LookupError("tvdb malformed response") from e
        raise LookupError("tvdb auth failed after re-login")

    async def search_candidates(self, title: str, limit: int = 10) -> list[MetadataResult]:
        body = await self._get_authed("/search", {"query": title, "type": "series"})
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            raise LookupError("tvdb malformed response")
        out: list[MetadataResult] = []
        for entry in data:
            result = series_to_result(entry)
            if result is not None:
                out.append(result)
            if len(out) >= limit:
                break
        return out

    async def search_series(self, title: str) -> MetadataResult:
        results = await self.search_candidates(title, limit=1)
        if not results:
            raise LookupError("tvdb search no results")
        return results[0]

    async def lookup_by_imdb_id(self, imdb_id: str) -> MetadataResult:
        body = await self._get_authed(f"/search/remoteid/{quote(imdb_id, safe='')}")
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            raise LookupError("tvdb malformed response")
        for entry in data:
            series = entry.get("series") if isinstance(entry, dict) else None
            result = series_to_result(series)
            if result is not None:
                result.payload.setdefault("imdb_id", imdb_id)
                return result
        raise LookupError("tvdb remoteid miss")
```

`validate_key` becomes `await self._login()` (return None). Keep the existing `test_config_key_check.py` / `test_config_tvdb_key.py` passing: they mock `POST /login` with status codes only; the new `_login` parses the token after a 200, so their 200 mocks need a `{"data": {"token": "t"}}` body — check and update those two test files if they return a bodiless 200 (say so in the report).

- [ ] **Step 4: Run, lint, commit**

Run: `uv run pytest services/backend/tests/test_metadata_clients_tvdb.py services/backend/tests/test_config_key_check.py services/backend/tests/test_config_tvdb_key.py -q -p no:cacheprovider && uv run pre-commit run ruff --files services/backend/arm_backend/metadata/tvdb.py services/backend/tests/test_metadata_clients_tvdb.py && uv run pre-commit run ruff-format --files services/backend/arm_backend/metadata/tvdb.py services/backend/tests/test_metadata_clients_tvdb.py && uv run mypy services/backend/arm_backend/metadata/tvdb.py`
Expected: all passed; clean.

```bash
git add services/backend/arm_backend/metadata/tvdb.py services/backend/tests
git commit -m "feat(metadata): TVDB v4 title search and IMDb lookup"
```

---

### Task 3: Adapters, id derivation, poster

**Files:**
- Modify: `services/backend/arm_backend/metadata/sources.py` (two adapters; `build_online_sources`)
- Modify: `services/backend/arm_backend/metadata/base.py` (`external_ids_of`, `extract_poster_url`)
- Modify: `services/backend/tests/test_metadata_sources.py`, `services/backend/tests/test_metadata_schema_fields.py` or wherever `external_ids_of` / `extract_poster_url` are tested (`grep -ln "external_ids_of\|extract_poster_url" services/backend/tests/*.py`)

**Interfaces:**
- Produces: `TvmazeSource` (`id="tvmaze"`, `media_types={"tv"}`, `requires_key=None`) and `TvdbSource` (`id="tvdb"`, `requires_key="tvdb_api_key"`), both with `search_title(cfg, kind, title, year)` (None for `kind != "tv"`), `search_candidates(cfg, kind, title, limit=10)` (`[]` for movie), `lookup_imdb(cfg, imdb_id)`. `build_online_sources` returns six sources. `external_ids_of` returns `tvmaze`; `extract_poster_url` honours `poster_url`.

- [ ] **Step 1: Write the failing tests**

In `test_metadata_sources.py`: extend `test_registry_has_the_four_sources_with_their_media_types` (rename to `…six_sources…`) with `tvmaze` and `tvdb` → `frozenset({"tv"})`, `requires_key` None / `"tvdb_api_key"`; add to `test_keyed_sources_report_missing_key`: `reg["tvdb"].configured(cfg) == "no tvdb key"` (with `tvdb_api_key=key`); add `test_keyless_sources_are_always_configured`: `reg["tvmaze"].configured(cfg) is None`. Add:

```python
async def test_tvmaze_adapter_is_tv_only_and_delegates(monkeypatch):
    calls: list[tuple] = []

    class FakeTVMaze:
        def __init__(self, http):
            pass

        async def search_show(self, title):
            calls.append(("show", title))
            return MetadataResult(title="Lost", year=2004, kind="tv")

        async def search_candidates(self, title, limit=10):
            calls.append(("cands", title, limit))
            return []

        async def lookup_by_imdb_id(self, imdb_id):
            calls.append(("imdb", imdb_id))
            return MetadataResult(title="Lost", year=2004, kind="tv")

    monkeypatch.setattr(sources_mod, "TVMazeClient", FakeTVMaze)
    async with httpx.AsyncClient() as http:
        tvmaze = build_online_sources(http)["tvmaze"]
        cfg = _config()
        assert await tvmaze.search_title(cfg, "movie", "lost", None) is None
        assert await tvmaze.search_candidates(cfg, "movie", "lost") == []
        assert (await tvmaze.search_title(cfg, "tv", "lost", 2004)).title == "Lost"
        assert await tvmaze.search_candidates(cfg, "tv", "lost", limit=3) == []
        assert (await tvmaze.lookup_imdb(cfg, "tt0411008")).title == "Lost"
    assert calls == [("show", "lost"), ("cands", "lost", 3), ("imdb", "tt0411008")]


async def test_tvdb_adapter_is_tv_only_and_passes_the_key(monkeypatch):
    calls: list[tuple] = []

    class FakeTVDB:
        def __init__(self, api_key, http):
            calls.append(("init", api_key))

        async def search_series(self, title):
            calls.append(("series", title))
            return MetadataResult(title="Lost", year=2004, kind="tv")

        async def search_candidates(self, title, limit=10):
            calls.append(("cands", title, limit))
            return []

        async def lookup_by_imdb_id(self, imdb_id):
            calls.append(("imdb", imdb_id))
            return MetadataResult(title="Lost", year=2004, kind="tv")

    monkeypatch.setattr(sources_mod, "TVDBClient", FakeTVDB)
    async with httpx.AsyncClient() as http:
        tvdb = build_online_sources(http)["tvdb"]
        cfg = _config(tvdb_api_key="tvdb-k")
        assert await tvdb.search_title(cfg, "movie", "lost", None) is None
        assert (await tvdb.search_title(cfg, "tv", "lost", 2004)).title == "Lost"
        assert await tvdb.search_candidates(cfg, "tv", "lost", limit=2) == []
        assert (await tvdb.lookup_imdb(cfg, "tt0411008")).title == "Lost"
    assert ("series", "lost") in calls and ("cands", "lost", 2) in calls and ("imdb", "tt0411008") in calls
    assert all(c[1] == "tvdb-k" for c in calls if c[0] == "init")
```

(`_config` in that file passes overrides through to `Config(**base)`, so `tvdb_api_key="tvdb-k"` works.)

For `external_ids_of` / `extract_poster_url`, add to the module that already tests them (or a new `test_metadata_base_ids.py` if none does):

```python
from arm_backend.metadata.base import MetadataResult, external_ids_of, extract_poster_url


def test_external_ids_of_reads_tvmaze_and_tvdb_provider_ids():
    tvmaze = MetadataResult(title="Lost", year=2004, kind="tv", provider="tvmaze", payload={"id": 4607, "imdb_id": "tt0411008", "tvdb_id": "73739"})
    ids = external_ids_of(tvmaze)
    assert (ids.tvmaze, ids.imdb, ids.tvdb, ids.tmdb) == ("4607", "tt0411008", "73739", None)
    tvdb = MetadataResult(title="Lost", year=2004, kind="tv", provider="tvdb", payload={"id": 73739})
    assert external_ids_of(tvdb).tvdb == "73739"
    explicit = MetadataResult(title="X", year=None, kind="tv", provider="omdb", payload={"tvmaze_id": "9", "tvdb_id": "8"})
    assert (external_ids_of(explicit).tvmaze, external_ids_of(explicit).tvdb) == ("9", "8")
    assert external_ids_of(MetadataResult(title="X", year=None, kind="tv", provider="tvmaze", payload={})).tvmaze is None


def test_extract_poster_url_accepts_a_generic_poster_url():
    assert extract_poster_url(MetadataResult(title="X", year=None, kind="tv", payload={"poster_url": "https://img/x.jpg"})) == "https://img/x.jpg"
    assert extract_poster_url(MetadataResult(title="X", year=None, kind="tv", payload={"poster_url": "not a url"})) is None
    # TMDb's poster_path still wins when both are present.
    both = MetadataResult(title="X", year=None, kind="tv", payload={"poster_path": "/a.jpg", "poster_url": "https://img/x.jpg"})
    assert extract_poster_url(both).endswith("/a.jpg")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest services/backend/tests/test_metadata_sources.py <ids test module> -q -p no:cacheprovider`
Expected: FAIL — `KeyError: 'tvmaze'`, missing `TVMazeClient` attribute, `ids.tvmaze is None`, poster None.

- [ ] **Step 3: Implement**

`metadata/base.py`, `external_ids_of`: add `tvmaze=_first_str(payload.get("tvmaze_id"), payload.get("id") if provider == "tvmaze" else None)` and change the tvdb line to `tvdb=_first_str(payload.get("tvdb_id"), payload.get("id") if provider == "tvdb" else None)`. `extract_poster_url`: after the OMDb block add

```python
    # TVmaze / TVDB adapters (and anything else) normalise a full URL here.
    poster_url = payload.get("poster_url")
    if isinstance(poster_url, str) and poster_url.startswith("http"):
        return poster_url
```

`metadata/sources.py`: import `TVMazeClient` from `arm_backend.metadata.tvmaze` and `TVDBClient` from `arm_backend.metadata.tvdb`; add after `OmdbSource`:

```python
class TvmazeSource:
    """TVmaze: keyless TV title search, candidates and IMDb lookup."""

    id = "tvmaze"
    media_types = frozenset({"tv"})
    requires_key: str | None = None

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    def configured(self, cfg: Config | None) -> str | None:
        return None

    async def search_title(self, cfg: Config | None, kind: Kind, title: str, year: int | None) -> MetadataResult | None:
        if kind != "tv":
            return None
        return await TVMazeClient(self._http).search_show(title)

    async def search_candidates(self, cfg: Config | None, kind: Kind, title: str, limit: int = 10) -> list[MetadataResult]:
        if kind != "tv":
            return []
        return await TVMazeClient(self._http).search_candidates(title, limit=limit)

    async def lookup_imdb(self, cfg: Config | None, imdb_id: str) -> MetadataResult | None:
        return await TVMazeClient(self._http).lookup_by_imdb_id(imdb_id)


class TvdbSource:
    """TVDB v4: keyed TV title search, candidates and IMDb lookup."""

    id = "tvdb"
    media_types = frozenset({"tv"})
    requires_key: str | None = "tvdb_api_key"

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    def _key(self, cfg: Config | None) -> str:
        return (getattr(cfg, "tvdb_api_key", None) or "").strip()

    def configured(self, cfg: Config | None) -> str | None:
        return "no tvdb key" if not self._key(cfg) else None

    def _client(self, cfg: Config | None) -> TVDBClient:
        return TVDBClient(self._key(cfg), self._http)

    async def search_title(self, cfg: Config | None, kind: Kind, title: str, year: int | None) -> MetadataResult | None:
        if kind != "tv":
            return None
        return await self._client(cfg).search_series(title)

    async def search_candidates(self, cfg: Config | None, kind: Kind, title: str, limit: int = 10) -> list[MetadataResult]:
        if kind != "tv":
            return []
        return await self._client(cfg).search_candidates(title, limit=limit)

    async def lookup_imdb(self, cfg: Config | None, imdb_id: str) -> MetadataResult | None:
        return await self._client(cfg).lookup_by_imdb_id(imdb_id)
```

and register both in `build_online_sources` after `OmdbSource(http)` (order in the dict does not matter; the lists decide). Update the module docstring's id comment (`"tmdb" | "omdb" | "tvmaze" | "tvdb" | "musicbrainz" | "arm_server"`).

- [ ] **Step 4: Run the suites, lint, commit**

Run: `uv run pytest services/backend/tests -q -p no:cacheprovider && uv run pre-commit run ruff --all-files && uv run pre-commit run ruff-format --all-files && uv run mypy services/backend/arm_backend/metadata/sources.py services/backend/arm_backend/metadata/base.py`
Expected: all passed. Casualties to expect and fix: `test_identity_registry_online.py::test_sources_for_tv_skips_ids_without_an_adapter` and `test_dispatcher.py::test_tv_order_follows_episode_sources` use fake registries, so they stand; any test building the real registry and asserting four ids (`test_registry_has_the_four_sources…`, renamed above; `test_known_source_ids_reads_media_types_from_the_registry` uses fakes). The router test `test_tv_search_falls_back_when_the_tv_provider_has_no_adapter` seeds `search_provider_tv="tvmaze"` with the real registry, where TVmaze now exists but the test mocks only TMDb: change its seed to `search_provider_tv="bogus"` (a row holding an unknown id) and keep its assertions — the registry test `test_search_source_falls_back_for_a_provider_with_no_adapter_yet` likewise seeds `tvmaze` against a fake registry without it, which still holds; rename its docstring subject to "an unknown id".

```bash
git add services/backend/arm_backend/metadata/sources.py services/backend/arm_backend/metadata/base.py services/backend/tests
git commit -m "feat(metadata): TVmaze and TVDB online-source adapters; generic poster and id fields"
```

---

### Task 4: `fill_external_ids`

**Files:**
- Modify: `services/backend/arm_backend/metadata/dispatcher.py` (`_with_tmdb_ids` → `fill_external_ids`; call sites in `identify` and `identify_from_imdb`)
- Modify: `services/backend/tests/test_dispatcher.py`

**Interfaces:**
- Produces: `MetadataDispatcher.fill_external_ids(hit, cfg) -> MetadataResult | None` (public, so the metadata router may reuse it later). `_with_tmdb_ids` removed; tests that call it by name are renamed.

- [ ] **Step 1: Write the failing tests**

Rename every `_with_tmdb_ids` reference in `test_dispatcher.py` to `fill_external_ids` (grep first; the respx enrichment tests keep their assertions). Add:

```python
async def test_fill_external_ids_adds_the_tmdb_id_to_a_tvmaze_hit():
    """S-10: a non-TMDb hit with an IMDb id gets its TMDb id from TMDb /find
    when TMDb is configured, so the episode stage can use every provider."""
    from arm_backend.metadata.base import MetadataResult

    calls: list[str] = []

    class Tmdb:
        id = "tmdb"
        media_types = frozenset({"movie", "tv"})
        requires_key = "tmdb_api_key"

        def configured(self, cfg):
            return None if cfg.tmdb_api_key else "no tmdb key"

        async def lookup_imdb(self, cfg, imdb_id):
            calls.append(imdb_id)
            return MetadataResult(title="Lost", year=2004, kind="tv", payload={"id": 4607, "tvdb_id": "73739"}, provider="tmdb")

    async with httpx.AsyncClient() as client:
        d = MetadataDispatcher(client, sources={"tmdb": Tmdb()})
        hit = MetadataResult(title="Lost", year=2004, kind="tv", payload={"id": 1, "imdb_id": "tt0411008"}, provider="tvmaze")
        out = await d.fill_external_ids(hit, _config())
        assert out is hit and out.payload["tmdb_id"] == "4607" and out.payload["tvdb_id"] == "73739"
        assert calls == ["tt0411008"]
        # Ids already present win; no second call for a hit that has tmdb_id.
        await d.fill_external_ids(hit, _config())
        assert calls == ["tt0411008"]
        # Unconfigured TMDb: nothing happens (review focus 5).
        other = MetadataResult(title="Lost", year=2004, kind="tv", payload={"imdb_id": "tt1"}, provider="tvmaze")
        assert (await d.fill_external_ids(other, _config(tmdb_api_key=None))).payload == {"imdb_id": "tt1"}
        assert calls == ["tt0411008"]


async def test_fill_external_ids_ignores_a_kind_mismatch_and_failures():
    from arm_backend.metadata.base import LookupError, MetadataResult

    class Tmdb:
        id = "tmdb"
        media_types = frozenset({"movie", "tv"})
        requires_key = "tmdb_api_key"
        mode = "mismatch"

        def configured(self, cfg):
            return None

        async def lookup_imdb(self, cfg, imdb_id):
            if self.mode == "mismatch":
                return MetadataResult(title="Lost (film)", year=1990, kind="movie", payload={"id": 99}, provider="tmdb")
            raise LookupError("down")

    tmdb = Tmdb()
    async with httpx.AsyncClient() as client:
        d = MetadataDispatcher(client, sources={"tmdb": tmdb})
        hit = MetadataResult(title="Lost", year=2004, kind="tv", payload={"imdb_id": "tt0411008"}, provider="tvdb")
        assert "tmdb_id" not in (await d.fill_external_ids(hit, _config())).payload
        tmdb.mode = "raise"
        assert "tmdb_id" not in (await d.fill_external_ids(hit, _config())).payload
        assert await d.fill_external_ids(None, _config()) is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `DATABASE_URL=postgresql://x:x@localhost/x ARM_SERVICE_TOKEN=tok-service uv run pytest services/backend/tests/test_dispatcher.py -q -p no:cacheprovider -k "fill_external_ids or with_tmdb_ids or enrich"`
Expected: FAIL with `AttributeError: 'MetadataDispatcher' object has no attribute 'fill_external_ids'`.

- [ ] **Step 3: Implement**

Replace `_with_tmdb_ids` with:

```python
    async def fill_external_ids(self, hit: MetadataResult | None, cfg: Config) -> MetadataResult | None:
        """Fill the ids a hit lacks so the stored identity lets every episode
        source find the show (spec S-10). A TMDb hit gets IMDb/TVDB ids from
        its `external_ids`; any other movie/TV hit with an IMDb id gets its
        TMDb id (and TVDB id) from TMDb's /find through the tmdb source, when
        that source is configured. Ids already in the payload win; a failure or
        timeout (bounded by PROVIDER_TIMEOUT_SECONDS) changes nothing."""
        if hit is None or hit.kind not in ("movie", "tv"):
            return hit
        if hit.provider == "tmdb":
            return await self._fill_from_tmdb_external_ids(hit, cfg)
        imdb = hit.payload.get("imdb_id")
        if hit.payload.get("tmdb_id") or not isinstance(imdb, str) or not imdb:
            return hit
        tmdb = self._sources.get("tmdb")
        if tmdb is None or tmdb.configured(cfg) is not None:
            return hit
        lookup = capability(tmdb, "lookup_imdb")
        if lookup is None:
            return hit
        found = await self._call("tmdb", lookup(cfg, imdb))
        if found is None or found.kind != hit.kind or found.payload.get("id") is None:
            return hit
        hit.payload["tmdb_id"] = str(found.payload["id"])
        tvdb = found.payload.get("tvdb_id")
        if tvdb and not hit.payload.get("tvdb_id"):
            hit.payload["tvdb_id"] = str(tvdb)
        return hit

    async def _fill_from_tmdb_external_ids(self, hit: MetadataResult, cfg: Config) -> MetadataResult:
        if not cfg.tmdb_api_key:
            return hit
        tmdb_id = hit.payload.get("id")
        if tmdb_id is None:
            return hit
        try:
            found = await asyncio.wait_for(
                TMDBClient(cfg.tmdb_api_key, self._http).get_external_id_map(tmdb_id, hit.kind),
                timeout=PROVIDER_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.info("metadata.tmdb_external_ids timeout id=%s", tmdb_id)
            return hit
        for key, value in found.items():
            hit.payload.setdefault(key, value)
        return hit
```

(`_call` already bounds the lookup by `PROVIDER_TIMEOUT_SECONDS` and swallows `LookupError`; the type-narrowing on `hit.kind` keeps mypy happy because `kind` is a `Literal`.) Update the two call sites (`identify` and `identify_from_imdb`) to `fill_external_ids`, and the `_with_tmdb_ids` mentions in comments.

- [ ] **Step 4: Run the suites, lint, commit**

Run: `uv run pytest services/backend/tests -q -p no:cacheprovider && uv run pre-commit run ruff --all-files && uv run pre-commit run ruff-format --all-files && uv run mypy services/backend/arm_backend/metadata/dispatcher.py`
Expected: all passed; clean. The prefer_tv test that patches `dispatcher_mod.TMDBClient` keeps working because the TMDb-hit path still constructs `TMDBClient` from the dispatcher module.

```bash
git add services/backend/arm_backend/metadata/dispatcher.py services/backend/tests/test_dispatcher.py
git commit -m "feat(metadata): fill_external_ids adds TMDb and TVDB ids to hits from any source"
```

---

### Task 5: TV search providers, wire contract, UI type

**Files:**
- Modify: `packages/arm_common/arm_common/config_metadata.py` (`search_provider_tv`), `packages/arm_common/tests/test_config_metadata.py`
- Modify: `services/backend/arm_backend/identity/sources/registry.py` (`ONLINE_SOURCE_VALUES["tv"]`), `services/backend/arm_backend/routers/metadata.py` (`SearchProvider`; type check)
- Modify: `services/backend/tests/test_metadata_search_router.py`, `services/backend/tests/test_identity_registry_online.py`, `services/backend/tests/test_config_identification_settings.py`
- Regenerate: `services/ui-neu/openapi.snapshot.json`, `services/ui-neu/frontend/src/lib/types/api.gen.ts`
- Modify: `services/ui-neu/frontend/src/lib/api/jobs.ts` (`searchMetadata` provider type), `src/lib/__tests__/jobs-api.test.ts` (one assertion with `provider=tvmaze`)

- [ ] **Step 1: Write the failing tests**

`test_config_metadata.py::test_identity_settings_meta`: `tv_sp.enum_values == ["tmdb", "omdb", "tvmaze", "tvdb"]`, labels `{"tmdb": "TMDb", "omdb": "OMDb", "tvmaze": "TVmaze", "tvdb": "TVDB"}`, `enum_requires == {"tmdb": "tmdb_api_key", "omdb": "omdb_api_key", "tvdb": "tvdb_api_key"}`.

`test_identity_registry_online.py::test_online_source_values_match_the_field_metadata` stays as is (it compares to the metadata, which changes with it).

`test_metadata_search_router.py`: change `test_search_provider_literal_matches_registry` to assert `set(get_args(metadata_router.SearchProvider)) == set(known_source_ids("movie", reg)) | set(known_source_ids("tv", reg))`. Add:

```python
@respx.mock
def test_search_tv_with_tvmaze_provider(signing_key: bytes) -> None:
    route = respx.get("https://api.tvmaze.com/search/shows").mock(
        return_value=httpx.Response(200, json=[{"score": 1, "show": {"id": 4607, "name": "Lost", "premiered": "2004-09-22", "externals": {"imdb": "tt0411008", "thetvdb": 73739}, "image": {"medium": "https://static.tvmaze.com/l.jpg"}}}])
    )
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "lost", "type": "tv", "provider": "tvmaze"}, headers=_auth(token))
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
        r = c.get("/api/metadata/search", params={"title": "x", "type": "movie", "provider": "tvmaze"}, headers=_auth(token))
    assert r.status_code == 400 and r.json()["detail"] == "tvmaze does not search movie"


@respx.mock
def test_search_default_tv_provider_tvmaze_without_tmdb_key(signing_key: bytes) -> None:
    respx.get("https://api.tvmaze.com/search/shows").mock(return_value=httpx.Response(200, json=[{"score": 1, "show": {"id": 1, "name": "Lost", "externals": {}, "image": None}}]))
    db = FakeSession()
    _seed(db, tmdb_api_key=None, search_provider_tv="tvmaze")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "lost", "type": "tv"}, headers=_auth(token))
    assert r.status_code == 200, r.text and r.json()["candidates"][0]["title"] == "Lost"
```

`test_config_identification_settings.py::test_patch_search_provider_needs_its_key`: add `search_provider_tv: "tvdb"` with no TVDB key → 400 `search_provider_tv: TVDB needs its API key`, then with `tvdb_api_key: "k"` in the same body → 200; and `search_provider_tv: "tvmaze"` → 200 with no key at all (the keyless path the PR 1 test lost).

UI `jobs-api.test.ts`: add a case `searchMetadata('Lost', 'tv', 'tvmaze')` → URL contains `provider=tvmaze` (it is a type change; the test exists to keep the union honest).

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest packages/arm_common/tests/test_config_metadata.py services/backend/tests/test_metadata_search_router.py services/backend/tests/test_config_identification_settings.py -q -p no:cacheprovider`
Expected: FAIL — enum values, 422 on `provider=tvmaze` (not in the literal), key-rule rows.

- [ ] **Step 3: Implement**

- `config_metadata.py`, `search_provider_tv`: `enum_values=["tmdb", "omdb", "tvmaze", "tvdb"]`, `enum_labels={"tmdb": "TMDb", "omdb": "OMDb", "tvmaze": "TVmaze", "tvdb": "TVDB"}`, `enum_requires={"tmdb": "tmdb_api_key", "omdb": "omdb_api_key", "tvdb": "tvdb_api_key"}`, help "The service behind the job page's search box for TV. TVmaze needs no key."
- `registry.py`: `ONLINE_SOURCE_VALUES["tv"] = ("tmdb", "omdb", "tvmaze", "tvdb")`.
- `routers/metadata.py`: `SearchProvider = Literal["tmdb", "omdb", "tvmaze", "tvdb"]`; in `search_metadata`, after resolving an explicit `provider` to a source and before the key check, add `if type not in source.media_types: raise HTTPException(400, f"{provider} does not search {type}")`.
- Regenerate: `bash devtools/regen-openapi-snapshot.sh && bash services/ui-neu/scripts/codegen.sh`.
- `api/jobs.ts`: `provider?: 'tmdb' | 'omdb' | 'tvmaze' | 'tvdb'`.

- [ ] **Step 4: Run everything, lint, commit**

Run: `uv run pytest services/backend/tests packages/arm_common/tests -q -p no:cacheprovider && (cd services/ui-neu/frontend && npm run check && npx vitest run && npm run lint) && uv run pre-commit run --all-files`
Expected: all green (`node_modules` must exist in the worktree: run `npm ci --prefix services/ui-neu/frontend` once if `npm run check` cannot find svelte-check).

```bash
git add packages/arm_common services/backend services/ui-neu/openapi.snapshot.json services/ui-neu/frontend/src
git commit -m "feat(config): TV search box may use TVmaze or TVDB"
```

---

### Task 6: Spec and docs

**Files:**
- Modify: `docs/superpowers/specs/2026-10-14-identification-sources-design.md` (§5.1 adapter sentence; §5.3 `_with_tmdb_ids` row; §6 PR 2b bullet; §10)
- Modify: `docs/developers/architecture/02-job-lifecycle.md` ("Online sources" paragraph: six sources; id fill)

- [ ] **Step 1: Edit**

- §5.1: "Adapters wrap the existing clients … and the TVmaze and TVDB HTTP already used by the episode providers" → "Adapters wrap the clients `TMDBClient`, `OMDBClient`, `MusicBrainzClient`, `ArmServerClient`, `TVMazeClient` and `TVDBClient` (the last two also serve title search for the TV list; episode listing keeps its own providers)."
- §5.3 `_with_tmdb_ids` row "After": "`fill_external_ids`: a TMDb hit gets IMDb/TVDB ids from `external_ids`; any other hit with an IMDb id gets its TMDb (and TVDB) id from TMDb `/find` through the tmdb source when configured (S-10)."
- §6 PR 2b bullet: "TVmaze and TVDB title-search clients and adapters (`search_title`, `search_candidates`, `lookup_imdb`, TV only); `fill_external_ids`; `search_provider_tv` offers `tmdb, omdb, tvmaze, tvdb`."
- §10: in the "Resolved in PR 1" bullet, strike "TVmaze and TVDB join the select in PR 2b with their adapters" and append "PR 2b added them."; in the "Resolved in PR 2" bullet, strike the sentence about the empty automatic TV walk and replace with "With PR 2b, TVmaze (keyless) is in the default TV list, so every install has an automatic TV title source."
- Lifecycle paragraph: list the six adapter ids and append "A hit from any source has its missing TMDb and TVDB ids filled from TMDb when a TMDb key is saved, so the episode stage can use every provider."

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-10-14-identification-sources-design.md docs/developers/architecture/02-job-lifecycle.md docs/superpowers/plans/2026-10-15-identification-sources-pr2b.md
git commit -m "docs: identification spec and lifecycle follow PR 2b"
```

---

## Self-review notes

- **Spec coverage.** §5.1 adapters: Tasks 1–3. S-10: Task 4. §5.3 rows: Tasks 3–4. §6 PR 2b: Task 5 for the select; §10 resolutions: Task 6. The `search_show -> ShowHit` capability the spec sketched is realised as `search_title` returning a `MetadataResult` for `kind="tv"`, which is what the dispatcher walk already consumes; the spec row in Task 6 says so.
- **Deviation recorded.** TVDB login is per client instance (per call) rather than cached process-wide; the episode provider keeps its own cached token. Acceptable for the volumes involved; a shared token cache is a later refinement.
- **Type consistency.** `TVMazeClient(http)`, `TVDBClient(api_key, http)` match the adapter constructors in Task 3; `search_show` / `search_series` / `search_candidates(title, limit=)` / `lookup_by_imdb_id` names are used identically in Tasks 1–3; `fill_external_ids(hit, cfg)` is the only enrichment entry point after Task 4.
- **Review Focus** 1–5 each have a named test.
