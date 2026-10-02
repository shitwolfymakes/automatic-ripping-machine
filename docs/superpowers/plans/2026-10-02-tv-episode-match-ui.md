# TV Episode Matching in ui-neu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an operator flip a job between movie and TV and review, re-run and correct TV episode placement in a Match Episodes tab, backed by a complete set of show ids in the job's identity.

**Architecture:** Backend: every identity writer stores `tmdb`, `imdb`, `tvdb` and a new `tmdb_kind` in `metadata_json.identity.external_ids`; the episode stage ignores a movie-kind TMDb id; `JobView` gains computed `looks_episodic` / `has_series`; PATCH accepts `media_type`. UI: a thin `identity` API module, a pure row/state model (`episodeModel.ts`), and an `EpisodeMatchPanel` component built to the Claude Design states, wired into the job page; TitleSearch gains a Movie/TV toggle and sends ids on apply; the job header gains a Movie | TV switch; the dead v2 matcher is deleted.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, SQLModel, pytest + respx (backend); SvelteKit / Svelte 5 runes, TypeScript, vitest + @testing-library/svelte (ui-neu).

**Spec:** `docs/superpowers/specs/2026-10-02-tv-episode-match-ui-design.md` (sections cited as "spec 3.4" etc.). Design: claude.ai/design project `c9e32e06-7be6-44c0-9fae-85ca48a37861`, files `MatchEpisodesPanel.dc.html` and `TV Episode Matching.dc.html` (frames 1a-1n).

## Global Constraints

- Branch `feat/tv-episode-match-ui`, worktree `/home/upb/src/arm-wt-tvmatch`, stacked on `feat/identity-settings` (#100).
- Run Python tests from the worktree root with `uv run pytest` (no file-path invocation, no `tests/__init__.py`; test module basenames must be unique across all services).
- Backend keeps 100% statement coverage; inline pragmas only as a bare `# pragma: no cover`.
- Enums are VARCHAR / Literal validated in the app; never Postgres `CREATE TYPE`. No migration is needed (all new data lives in JSON `metadata_json`).
- After any schema / router change: `bash devtools/regen-openapi-snapshot.sh` then `bash services/ui-neu/scripts/codegen.sh`, and commit both artifacts.
- UI: reuse shared components and the block classes (`btn`, `chip`, `badge`, `alert`, `table`, `field`, `panel`); no one-off status glyphs. Light and dark themes; phone width with a 16px gutter and no horizontal scroll.
- Every suite's **exit code** is checked, not only its summary line: `uv run pytest; echo $?`, `npx vitest run; echo $?`, `npm run check; echo $?`, `npm run lint; echo $?`.
- Commit messages: conventional style, **no Claude attribution lines** (repo owner rule).
- `TrackRole` is `main | episode | extra | trailer | other`. There is no "play all" role.
- Episode sources are `"tmdb" | "tvmaze" | "tvdb"` (`EpisodeSourceSetting`).

## Review Focus

1. A job whose stored TMDb id is a movie (`tmdb_kind: "movie"`) and media type TV must show **Pick the series first** and must never have episodes matched against that id (Task 6 tests the stage; Task 12 tests the panel state).
2. Jobs stored before this change (no `tmdb_kind`) must behave exactly as today: their `tmdb` is still used as a show id (Task 6 test `test_unknown_kind_tmdb_is_still_used`).
3. A failed preview or apply must leave the current placement untouched and say which source failed (Task 13 test `keeps the current placement when preview fails`).
4. A hand-set episode picked while the stage is running must not be possible: pickers and Re-run are hidden in the matching state (Task 12 test `hides pickers and re-run while matching`).
5. Guests see everything but no controls; controls are removed, not disabled (Task 12 test `guest sees rows but no controls`).

---

## File Structure

Backend (`/home/upb/src/arm-wt-tvmatch`):

- Modify `packages/arm_common/arm_common/schemas/job_metadata.py` — `ExternalIds.tmdb_kind`.
- Create `packages/arm_common/arm_common/disc_shape.py` — pure `looks_episodic` (moved into arm_common so `JobView` can use it).
- Modify `packages/arm_common/arm_common/schemas/jobs.py` — `JobView` computed fields; `JobUpdateRequest.media_type`.
- Modify `packages/arm_common/arm_common/schemas/metadata.py` — `MetadataCandidate.external_ids`.
- Modify `services/backend/arm_backend/metadata/base.py` — `external_ids_of(result)`; `metadata_with_identity` uses it.
- Modify `services/backend/arm_backend/metadata/tmdb.py` — `get_external_id_map`; candidates carry `tvdb_id`.
- Modify `services/backend/arm_backend/metadata/dispatcher.py` — enrich the chosen TMDb hit.
- Modify `services/backend/arm_backend/routers/metadata.py` — candidates carry ids.
- Modify `services/backend/arm_backend/routers/jobs.py` — resolve copies `tmdb_kind`; PATCH sets `media_type`.
- Modify `services/backend/arm_backend/identity/ids.py` — movie-kind TMDb id is not a show id.

UI (`services/ui-neu/frontend/src`):

- Create `lib/api/identity.ts` — the four identity endpoints.
- Modify `lib/api/jobs.ts` — `resolveJob` passes `external_ids`; `setJobMediaType`; delete v2 stubs.
- Create `lib/components/episodes/episodeModel.ts` — pure state / row derivation.
- Create `lib/components/episodes/EpisodeMatchPanel.svelte` — the tab.
- Create `lib/components/episodes/MediaTypeSwitch.svelte` — header Movie | TV switch.
- Modify `lib/components/TitleSearch.svelte` — Movie / TV toggle, ids on apply, `onseries`.
- Modify `routes/jobs/[id]/+page.svelte` — tab, switch, refresh.
- Delete `lib/components/EpisodeMatch.svelte`, `EpisodeMatch.test.ts`, `TvdbMatch.svelte`, `TvdbMatch.test.ts`.

---

### Task 1: `tmdb_kind` and one place that derives a result's ids

**Files:**
- Modify: `packages/arm_common/arm_common/schemas/job_metadata.py:34-42`
- Modify: `services/backend/arm_backend/metadata/base.py:45-83`
- Test: `services/backend/tests/test_external_ids_of.py` (new)

**Interfaces:**
- Produces: `ExternalIds.tmdb_kind: Literal["movie", "tv"] | None`; `external_ids_of(result: MetadataResult) -> ExternalIds` in `arm_backend.metadata.base`.

- [ ] **Step 1: Write the failing tests**

```python
# services/backend/tests/test_external_ids_of.py
"""Every id a provider hit carries lands in the identity, with the TMDb id's
kind, so episode sources can find the show (spec 3.4)."""

from __future__ import annotations

from datetime import datetime, timezone

from arm_backend.metadata.base import MetadataResult, external_ids_of, metadata_with_identity


def test_tmdb_tv_hit_records_all_ids_and_kind() -> None:
    hit = MetadataResult(
        title="Kolchak: The Night Stalker", year=1974, kind="tv",
        payload={"id": 5084, "imdb_id": "tt0071003", "tvdb_id": 77170}, provider="tmdb",
    )
    ids = external_ids_of(hit)
    assert (ids.tmdb, ids.imdb, ids.tvdb, ids.tmdb_kind) == ("5084", "tt0071003", "77170", "tv")


def test_tmdb_movie_hit_records_movie_kind() -> None:
    hit = MetadataResult(title="Arrival", year=2016, kind="movie", payload={"id": 329865}, provider="tmdb")
    assert external_ids_of(hit).tmdb_kind == "movie"


def test_no_tmdb_id_means_no_kind() -> None:
    hit = MetadataResult(title="Lost", year=2004, kind="tv", payload={"imdbID": "tt0411008"}, provider="omdb")
    ids = external_ids_of(hit)
    assert (ids.imdb, ids.tmdb, ids.tmdb_kind) == ("tt0411008", None, None)


def test_metadata_with_identity_stores_the_kind() -> None:
    hit = MetadataResult(title="X", year=2000, kind="tv", payload={"id": 1}, provider="tmdb")
    md = metadata_with_identity({}, hit, identified_at=datetime.now(timezone.utc))
    assert md["identity"]["external_ids"] == {"tmdb": "1", "tmdb_kind": "tv"}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q -k test_external_ids_of; echo $?`
Expected: collection error `cannot import name 'external_ids_of'`, exit code non-zero.

- [ ] **Step 3: Implement**

In `job_metadata.py`, add to `ExternalIds` after `musicbrainz_release` (add `Literal` to the `typing` import):

```python
    # Whether `tmdb` names a movie or a TV show: TMDb numbers the two
    # separately, so a movie's id must never be used as a show id (episode
    # stage). None for ids stored before this field existed.
    tmdb_kind: Literal["movie", "tv"] | None = None
```

In `metadata/base.py`, add above `metadata_with_identity`:

```python
def external_ids_of(result: MetadataResult) -> ExternalIds:
    """Every id a provider hit carries, plus the kind of its TMDb id.

    The single derivation used by identify (`metadata_with_identity`) and
    the title-search candidates, so both store the same ids."""
    payload = result.payload or {}
    provider = result.provider or "unknown"
    tmdb = _first_str(payload.get("tmdb_id"), payload.get("id") if provider == "tmdb" else None)
    return ExternalIds(
        imdb=_first_str(payload.get("imdb_id"), payload.get("imdbID")),
        tmdb=tmdb,
        tvdb=_first_str(payload.get("tvdb_id")),
        musicbrainz_release=_first_str(payload.get("id") if provider == "musicbrainz" else None),
        tmdb_kind=result.kind if tmdb and result.kind in ("movie", "tv") else None,
    )
```

and in `metadata_with_identity` replace lines 61-66 (the `external = ExternalIds(...)` block) with:

```python
    external = external_ids_of(result)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q -k "test_external_ids_of or identify" ; echo $?`
Expected: all pass, exit 0.

- [ ] **Step 5: Commit**

```bash
git add packages/arm_common/arm_common/schemas/job_metadata.py services/backend/arm_backend/metadata/base.py services/backend/tests/test_external_ids_of.py
git commit -m "feat(identity): ExternalIds.tmdb_kind; one derivation of a hit's ids"
```

---

### Task 2: TMDb returns IMDb and TVDB ids together

**Files:**
- Modify: `services/backend/arm_backend/metadata/tmdb.py:99-151`
- Test: `services/backend/tests/test_metadata_clients.py` (append)

**Interfaces:**
- Produces: `TMDBClient.get_external_id_map(tmdb_id: int | str, kind: Literal["movie","tv"]) -> dict[str, str]` (keys `imdb_id`, `tvdb_id`, present only when known; never raises). `get_external_ids` keeps its signature and returns `map.get("imdb_id")`. `_search_candidates` sets both `payload["imdb_id"]` and `payload["tvdb_id"]`.

- [ ] **Step 1: Write the failing tests** (append to `test_metadata_clients.py`, which already has the `http_client` fixture and imports `respx`, `httpx`, `TMDBClient`)

```python
@respx.mock
async def test_tmdb_external_id_map_has_imdb_and_tvdb(http_client) -> None:
    respx.get("https://api.themoviedb.org/3/tv/5084/external_ids").mock(
        return_value=httpx.Response(200, json={"imdb_id": "tt0071003", "tvdb_id": 77170})
    )
    ids = await TMDBClient("k", http_client).get_external_id_map(5084, "tv")
    assert ids == {"imdb_id": "tt0071003", "tvdb_id": "77170"}


@respx.mock
async def test_tmdb_external_id_map_empty_on_failure(http_client) -> None:
    respx.get("https://api.themoviedb.org/3/tv/1/external_ids").mock(return_value=httpx.Response(500))
    assert await TMDBClient("k", http_client).get_external_id_map(1, "tv") == {}


@respx.mock
async def test_tmdb_tv_candidates_carry_tvdb_id(http_client) -> None:
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=httpx.Response(200, json={"results": [{"id": 5084, "name": "Kolchak: The Night Stalker", "first_air_date": "1974-09-13"}]})
    )
    respx.get("https://api.themoviedb.org/3/tv/5084/external_ids").mock(
        return_value=httpx.Response(200, json={"imdb_id": "tt0071003", "tvdb_id": 77170})
    )
    [hit] = await TMDBClient("k", http_client).search_tv_candidates("kolchak")
    assert (hit.payload["imdb_id"], hit.payload["tvdb_id"]) == ("tt0071003", "77170")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q -k "external_id_map or carry_tvdb"; echo $?`
Expected: FAIL `AttributeError: 'TMDBClient' object has no attribute 'get_external_id_map'`.

- [ ] **Step 3: Implement** — replace `get_external_ids` (131-151) with:

```python
    async def get_external_id_map(self, tmdb_id: int | str, kind: Literal["movie", "tv"]) -> dict[str, str]:
        """A result's IMDb and TVDB ids via TMDb `external_ids`, as
        `{"imdb_id": ..., "tvdb_id": ...}` with only the known ones present.
        Empty on any failure; NEVER raises (it runs per candidate in the search
        fan-out and per identify hit, and one failure must fail neither)."""
        try:
            r = await self._http.get(f"{_base_url()}/{kind}/{tmdb_id}/external_ids", headers=self._headers)
        except httpx.HTTPError:
            return {}
        if r.status_code != 200:
            return {}
        try:
            body = r.json()
        except ValueError:
            return {}
        if not isinstance(body, dict):
            return {}
        out: dict[str, str] = {}
        imdb = body.get("imdb_id")
        if isinstance(imdb, str) and imdb:
            out["imdb_id"] = imdb
        tvdb = body.get("tvdb_id")
        if isinstance(tvdb, int) or (isinstance(tvdb, str) and tvdb):
            out["tvdb_id"] = str(tvdb)
        return out

    async def get_external_ids(self, tmdb_id: int | str, kind: Literal["movie", "tv"]) -> str | None:
        """The result's IMDb id only (kept for callers that need just that)."""
        return (await self.get_external_id_map(tmdb_id, kind)).get("imdb_id")
```

and in `_search_candidates` replace lines 118-128 with:

```python
        enrichable = [r for r in out if r.payload.get("id") is not None]
        maps = await asyncio.gather(
            *(self.get_external_id_map(r.payload["id"], kind) for r in enrichable),
            return_exceptions=True,
        )
        resolved = {id(r): (m if isinstance(m, dict) else {}) for r, m in zip(enrichable, maps)}
        for r in out:
            found = resolved.get(id(r), {})
            r.payload["imdb_id"] = found.get("imdb_id")
            r.payload["tvdb_id"] = found.get("tvdb_id")
        return out
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q -k "tmdb"; echo $?`
Expected: all pass, exit 0. The existing `get_external_ids` tests (lines ~714, 1081-1095) still pass because the wrapper keeps its contract.

- [ ] **Step 5: Commit**

```bash
git add services/backend/arm_backend/metadata/tmdb.py services/backend/tests/test_metadata_clients.py
git commit -m "feat(metadata): TMDb external ids return IMDb and TVDB; candidates carry both"
```

---

### Task 3: Identify enriches the chosen TMDb hit

**Files:**
- Modify: `services/backend/arm_backend/metadata/dispatcher.py:83-97, 194-201`
- Test: `services/backend/tests/test_dispatcher.py` (append)

**Interfaces:**
- Consumes: `TMDBClient.get_external_id_map` (Task 2).
- Produces: a TMDb hit returned by `MetadataDispatcher.identify` / `identify_from_imdb` has `payload["imdb_id"]` / `payload["tvdb_id"]` filled when TMDb knows them (an id already in the payload is kept).

- [ ] **Step 1: Write the failing tests** (append; file already imports `httpx`, `respx`, `MetadataDispatcher`, `DiscType`, `ScanResult`, `_config`)

```python
@respx.mock
async def test_identify_enriches_the_tmdb_tv_hit_with_imdb_and_tvdb():
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=httpx.Response(200, json={"results": [{"id": 5084, "name": "Kolchak: The Night Stalker", "first_air_date": "1974-09-13"}]})
    )
    respx.get("https://api.themoviedb.org/3/tv/5084/external_ids").mock(
        return_value=httpx.Response(200, json={"imdb_id": "tt0071003", "tvdb_id": 77170})
    )
    async with httpx.AsyncClient() as client:
        scan = ScanResult(disc_type=DiscType.BLURAY, volume_label="KOLCHAK")
        hit = await MetadataDispatcher(client).identify(scan, _config(omdb_api_key=None), title_hint="kolchak", title_hint_is_tv=True)
    assert hit is not None and hit.provider == "tmdb"
    assert (hit.payload["imdb_id"], hit.payload["tvdb_id"]) == ("tt0071003", "77170")


@respx.mock
async def test_identify_keeps_the_hit_when_enrichment_fails():
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(200, json={"results": [{"id": 603, "title": "The Matrix", "release_date": "1999-03-31"}]})
    )
    respx.get("https://api.themoviedb.org/3/movie/603/external_ids").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as client:
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="THE_MATRIX_1999")
        hit = await MetadataDispatcher(client).identify(scan, _config())
    assert hit is not None and hit.title == "The Matrix" and "tvdb_id" not in hit.payload


@respx.mock
async def test_identify_from_imdb_keeps_the_known_imdb_and_adds_tvdb():
    respx.get("https://api.themoviedb.org/3/find/tt0071003").mock(
        return_value=httpx.Response(200, json={"movie_results": [], "tv_results": [{"id": 5084, "name": "Kolchak: The Night Stalker", "first_air_date": "1974-09-13"}]})
    )
    respx.get("https://api.themoviedb.org/3/tv/5084/external_ids").mock(
        return_value=httpx.Response(200, json={"imdb_id": "tt0071003", "tvdb_id": 77170})
    )
    async with httpx.AsyncClient() as client:
        hit = await MetadataDispatcher(client).identify_from_imdb("tt0071003", _config())
    assert hit is not None and hit.kind == "tv"
    assert (hit.payload["imdb_id"], hit.payload["tvdb_id"]) == ("tt0071003", "77170")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q -k "enrich or identify_from_imdb_keeps"; echo $?`
Expected: FAIL `KeyError: 'imdb_id'` / `'tvdb_id'`.

- [ ] **Step 3: Implement** — add to `MetadataDispatcher`:

```python
    async def _with_tmdb_ids(self, hit: MetadataResult | None, cfg: Config) -> MetadataResult | None:
        """Fill a TMDb hit's IMDb / TVDB ids (one `external_ids` call) so the
        stored identity lets every episode source find the show (spec 3.4).
        Ids already in the payload win; a failed call changes nothing."""
        if hit is None or hit.provider != "tmdb" or hit.kind not in ("movie", "tv") or not cfg.tmdb_api_key:
            return hit
        tmdb_id = hit.payload.get("id")
        if tmdb_id is None:
            return hit
        found = await TMDBClient(cfg.tmdb_api_key, self._http).get_external_id_map(tmdb_id, hit.kind)
        for key, value in found.items():
            hit.payload.setdefault(key, value)
        return hit
```

In `identify`, replace line 97 with:

```python
        hit = await self._identify_video(scan, cfg, title_hint=title_hint, title_hint_is_tv=title_hint_is_tv)
        return await self._with_tmdb_ids(hit, cfg)
```

In `identify_from_imdb`, replace line 201 with:

```python
        hit = await self._call("tmdb_find_imdb", tmdb.find_by_imdb_id(imdb_id))
        if hit is not None:
            hit.payload.setdefault("imdb_id", imdb_id)
        return await self._with_tmdb_ids(hit, cfg)
```

- [ ] **Step 4: Run the whole dispatcher module and the ripper identify tests**

Run: `uv run pytest -q -k "dispatcher or identify"; echo $?`
Expected: exit 0. If an existing `@respx.mock` test now fails with respx `AllMockedAssertionError` for `.../external_ids`, that test's search payload has an `"id"`: add `respx.get(<that external_ids url>).mock(return_value=httpx.Response(200, json={}))` to it (the enrichment then finds nothing and the old assertions hold). Do not change the assertions.

- [ ] **Step 5: Commit**

```bash
git add services/backend/arm_backend/metadata/dispatcher.py services/backend/tests/test_dispatcher.py
git commit -m "feat(identify): the chosen TMDb hit carries its IMDb and TVDB ids"
```

---

### Task 4: Title-search candidates carry their ids

**Files:**
- Modify: `packages/arm_common/arm_common/schemas/metadata.py:8-18`
- Modify: `services/backend/arm_backend/routers/metadata.py:47-95`
- Test: `services/backend/tests/test_metadata_search_router.py` (append; reuse its app/auth helpers)

**Interfaces:**
- Consumes: `external_ids_of` (Task 1), candidate `payload["tvdb_id"]` (Task 2).
- Produces: `MetadataCandidate.external_ids: ExternalIds | None` (with `tmdb_kind`).

- [ ] **Step 1: Write the failing test** — copy the module's existing TMDb TV search test (the one that mocks `search/tv` and calls `GET /api/metadata/search?title=...&type=tv`) into a new test named `test_tv_search_candidates_carry_all_ids`, mock `.../tv/5084/external_ids` → `{"imdb_id": "tt0071003", "tvdb_id": 77170}` with search result `{"id": 5084, "name": "Kolchak: The Night Stalker", "first_air_date": "1974-09-13"}`, and assert:

```python
    [c] = r.json()["candidates"]
    assert c["external_ids"] == {"tmdb": "5084", "imdb": "tt0071003", "tvdb": "77170", "tmdb_kind": "tv"}
```

and a second test `test_omdb_candidates_carry_imdb_without_tmdb_kind` copied from the module's OMDb search test, asserting `c["external_ids"] == {"imdb": <its imdbID>}`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q -k carry; echo $?`
Expected: FAIL `KeyError: 'external_ids'`.

- [ ] **Step 3: Implement**

`schemas/metadata.py`: import `from arm_common.schemas.job_metadata import ExternalIds` and add to `MetadataCandidate`:

```python
    # Every id this result carries (tmdb with its kind, imdb, tvdb), so
    # applying it stores the identity that was picked (spec 3.4).
    external_ids: ExternalIds | None = None
```

`routers/metadata.py`: import `external_ids_of` from `arm_backend.metadata.base`; in `_to_candidate` add the argument:

```python
        external_ids=external_ids_of(r),
```

and give the response `exclude_none` ids by stamping the provider before building candidates — replace the final `return` of `search_metadata` with:

```python
    for r in results:
        r.provider = r.provider or resolved
    return MetadataSearchResponse(candidates=[_to_candidate(r) for r in results])
```

Set `response_model_exclude_none=True` on the `@router.get("/search", ...)` decorator only if the assertion fails on `null` members; otherwise leave the decorator as is and compare with `{k: v for k, v in c["external_ids"].items() if v is not None}` in the tests.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q -k "metadata_search"; echo $?`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add packages/arm_common/arm_common/schemas/metadata.py services/backend/arm_backend/routers/metadata.py services/backend/tests/test_metadata_search_router.py
git commit -m "feat(metadata): search candidates carry every id and the TMDb kind"
```

---

### Task 5: Resolve stores `tmdb_kind`; PATCH can change the media type

**Files:**
- Modify: `services/backend/arm_backend/routers/jobs.py:995-1030` (resolve), `:855-931` (update_job)
- Modify: `packages/arm_common/arm_common/schemas/jobs.py:228-238` (`JobUpdateRequest`)
- Test: `services/backend/tests/test_jobs_router.py` (append; uses `_make_app`, `_auth`, `_ids_job`, `_job`, `_StageRunner`, `FakeSession`)

**Interfaces:**
- Produces: `POST /api/jobs/{id}/resolve` copies `external_ids.tmdb_kind` when sent and clears it with the other stale ids when the show changes; `PATCH /api/jobs/{id}` accepts `media_type` (writer only, existing auth) and reschedules the episode stage (the existing `_identity_snapshot` check covers `media_type`).

- [ ] **Step 1: Write the failing tests**

```python
def test_resolve_stores_the_picked_series_ids_and_kind(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    job = _job(meta={"identity": {"provider": "tmdb", "external_ids": {"tmdb": "1749913", "tmdb_kind": "movie"}}})
    db.rows["jobs"] = [job]
    app.state.episode_stage = _StageRunner()
    body = {
        "title": "Kolchak: The Night Stalker", "year": 1974, "media_type": "tv",
        "external_ids": {"tmdb": "5084", "imdb": "tt0071003", "tvdb": "77170", "tmdb_kind": "tv"},
    }
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{job.id}/resolve", json=body, headers=_auth(token))
    assert r.status_code == 200, r.text
    ids = {k: v for k, v in r.json()["job"]["metadata_json"]["identity"]["external_ids"].items() if v is not None}
    assert ids == {"tmdb": "5084", "imdb": "tt0071003", "tvdb": "77170", "tmdb_kind": "tv"}


def test_resolve_with_a_new_tmdb_and_no_kind_drops_the_old_kind(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    job = _job(meta={"identity": {"provider": "tmdb", "external_ids": {"tmdb": "1749913", "tmdb_kind": "movie"}}})
    db.rows["jobs"] = [job]
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{job.id}/resolve", json={"title": "X", "external_ids": {"tmdb": "5084"}}, headers=_auth(token))
    ids = r.json()["job"]["metadata_json"]["identity"]["external_ids"]
    assert ids.get("tmdb") == "5084" and ids.get("tmdb_kind") is None


def test_patch_switches_media_type_and_reschedules_matching(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    job = _job(meta={"identity": {"provider": "tmdb", "external_ids": {"tmdb": "1749913", "tmdb_kind": "movie"}}})
    job.media_type = MediaType.MOVIE
    db.rows["jobs"] = [job]
    runner = _StageRunner()
    app.state.episode_stage = runner
    with TestClient(app) as client:
        r = client.patch(f"/api/jobs/{job.id}", json={"media_type": "tv"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["media_type"] == "tv"
    assert r.json()["metadata_json"]["identity"]["external_ids"]["tmdb"] == "1749913"  # ids kept
    assert runner.scheduled == [job.id]
```

(Import `MediaType` from `arm_common.enums` if the module doesn't already.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q -k "picked_series or drops_the_old_kind or switches_media_type"; echo $?`
Expected: 3 failures (`tmdb_kind` not copied; `422` for `media_type`).

- [ ] **Step 3: Implement**

`JobUpdateRequest` (schemas/jobs.py): add

```python
    # The header Movie | TV switch: the type alone, ids untouched. The episode
    # stage re-runs on the change (routers/jobs.py identity snapshot).
    media_type: MediaType | None = None
```

`update_job` (routers/jobs.py): `media_type` is not a claim field, so it falls into the "other keys are written with setattr" path already used for `poster_url_manual`. Verify by reading lines 870-880; if the loop only handles listed names, add `"media_type"` to it. No provenance call (spec 3.2; `media_type` has no claim provenance).

Resolve (routers/jobs.py), in the `show_changed` clear loop change `for name in ("tvmaze", *_SHOW_ID_FIELDS):` to `for name in ("tvmaze", "tmdb_kind", *_SHOW_ID_FIELDS):`, and after the `tvdb` copy add:

```python
        if "tmdb_kind" in ids_set:
            existing_ids.tmdb_kind = req.external_ids.tmdb_kind
        elif "tmdb" in ids_set and req.external_ids.tmdb != getattr(existing_ids, "tmdb", None):
            existing_ids.tmdb_kind = None  # a new TMDb id of unknown kind
```

Place the `elif` before `existing_ids.tmdb` is overwritten (i.e. move the `tmdb` copy below it) so the comparison sees the old value.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q -k "jobs_router or resolve"; echo $?`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add packages/arm_common/arm_common/schemas/jobs.py services/backend/arm_backend/routers/jobs.py services/backend/tests/test_jobs_router.py
git commit -m "feat(jobs): resolve stores tmdb_kind; PATCH switches the media type"
```

---

### Task 6: A movie's TMDb id is never used as a show id

**Files:**
- Modify: `services/backend/arm_backend/identity/ids.py:43-124`
- Test: `services/backend/tests/test_identity_ids.py` (append; reuse its job/provider fakes)

**Interfaces:**
- Produces: `resolve_show_ids` returns ids in which a `tmdb` of kind `movie` is absent unless a provider resolved a TV one (then `tmdb_kind="tv"`); `merge_new_ids` replaces a stored movie-kind `tmdb` with a found TV one.

- [ ] **Step 1: Write the failing tests** (use the module's existing fake provider class; if it has none, add this one)

```python
class _Provider:
    def __init__(self, id_field: str, answer: str | None) -> None:
        self.source_id = f"episodes_{id_field}"
        self.id_field = id_field
        self.answer = answer
        self.seen: list[ExternalIds] = []

    async def resolve_show_id(self, ids: ExternalIds) -> str | None:
        self.seen.append(ids)
        return self.answer


def _job_with(ids: dict) -> Job:
    return Job(id="job_1", drive_id="drv_x", disc_type=DiscType.BLURAY, status=JobStatus.RIPPED,
               title="Kolchak", year=None, resumed_from_crash=False,
               metadata_json={"identity": {"provider": "tmdb", "external_ids": ids}})


async def test_movie_kind_tmdb_is_not_a_show_id() -> None:
    tmdb = _Provider("tmdb", None)  # /find by imdb/tvdb found nothing
    ids = await resolve_show_ids(_job_with({"tmdb": "1749913", "tmdb_kind": "movie"}), [tmdb])
    assert ids.tmdb is None
    assert tmdb.seen and tmdb.seen[0].tmdb is None  # asked, without the movie id


async def test_movie_kind_tmdb_replaced_by_the_resolved_show() -> None:
    job = _job_with({"tmdb": "1749913", "tmdb_kind": "movie", "imdb": "tt0071003"})
    ids = await resolve_show_ids(job, [_Provider("tmdb", "5084")])
    assert (ids.tmdb, ids.tmdb_kind) == ("5084", "tv")
    stored = job.metadata_json["identity"]["external_ids"]
    assert (stored["tmdb"], stored["tmdb_kind"]) == ("5084", "tv")


async def test_unknown_kind_tmdb_is_still_used() -> None:
    tmdb = _Provider("tmdb", "should-not-be-asked")
    ids = await resolve_show_ids(_job_with({"tmdb": "1399"}), [tmdb])
    assert ids.tmdb == "1399" and tmdb.seen == []


def test_merge_new_ids_replaces_a_movie_tmdb_with_a_show() -> None:
    job = _job_with({"tmdb": "1749913", "tmdb_kind": "movie"})
    assert merge_new_ids(job, ExternalIds(tmdb="5084", tmdb_kind="tv")) is True
    stored = job.metadata_json["identity"]["external_ids"]
    assert (stored["tmdb"], stored["tmdb_kind"]) == ("5084", "tv")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q -k "movie_kind or unknown_kind or replaces_a_movie"; echo $?`
Expected: 3 failures (`test_unknown_kind_tmdb_is_still_used` already passes).

- [ ] **Step 3: Implement** — in `resolve_show_ids` replace lines 61-89 with:

```python
    stored = current_ids(job)
    # A movie's TMDb id is not a show id (TMDb numbers movies and shows
    # separately): episode sources look the show up by IMDb / TVDB instead.
    ids = stored.model_copy(update={"tmdb": None}) if stored.tmdb_kind == "movie" else stored
    found = False
    for provider in providers:
        if getattr(ids, provider.id_field, None):
            continue
        try:
            show_id = await provider.resolve_show_id(ids)
        except (SourceError, SourceMiss) as e:
            if raise_errors and isinstance(e, SourceError):
                raise
            logger.warning("resolve_show_id failed source=%s job_id=%s: %s", provider.source_id, job.id, e)
            continue
        if show_id is None:
            continue
        update: dict[str, str] = {provider.id_field: show_id}
        if provider.id_field == "tmdb":
            update["tmdb_kind"] = "tv"
        ids = ids.model_copy(update=update)
        stored = stored.model_copy(update=update)
        found = True

    if found and persist:
        identity = (job.metadata_json or {}).get("identity")
        if isinstance(identity, dict):
            job.metadata_json = {
                **(job.metadata_json or {}),
                "identity": {**identity, "external_ids": stored.model_dump(mode="json", exclude_none=True)},
            }
    return ids
```

In `merge_new_ids`, replace the `new_values = {...}` comprehension with:

```python
    replace_movie = existing.tmdb_kind == "movie" and found.tmdb_kind == "tv" and found.tmdb is not None
    new_values = {
        field: value
        for field, value in found.model_dump(exclude_none=True).items()
        if getattr(existing, field, None) is None or (replace_movie and field in ("tmdb", "tmdb_kind"))
    }
```

- [ ] **Step 4: Run the identity and episode-stage suites**

Run: `uv run pytest -q -k "identity or episode"; echo $?`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add services/backend/arm_backend/identity/ids.py services/backend/tests/test_identity_ids.py
git commit -m "fix(identity): a movie's TMDb id is never used as a show id"
```

---

### Task 7: `JobView.looks_episodic` and `JobView.has_series`

**Files:**
- Create: `packages/arm_common/arm_common/disc_shape.py`
- Modify: `packages/arm_common/arm_common/schemas/jobs.py:148-183` (`JobView`)
- Test: `packages/arm_common/tests/test_common_disc_shape.py` (new), `services/backend/tests/test_job_metadata_schema.py` (append)

**Interfaces:**
- Produces: `arm_common.disc_shape.looks_episodic(titles: Sequence[ScanTitle]) -> bool`; `JobView.looks_episodic: bool` and `JobView.has_series: bool` (pydantic `@computed_field`, serialized in every JobView response).

- [ ] **Step 1: Bring the shape rule over and write the failing tests**

Create `packages/arm_common/arm_common/disc_shape.py` with the exact body of `services/backend/arm_backend/identity/disc_shape.py` from integration commit `065d96d4` (`git show 065d96d4:services/backend/arm_backend/identity/disc_shape.py`), changing nothing but its docstring's first line to say it lives in arm_common so `JobView` can use it. Create `packages/arm_common/tests/test_common_disc_shape.py` from `git show 065d96d4:services/backend/tests/test_disc_shape.py`, replacing the import with `from arm_common.disc_shape import looks_episodic` and dropping the two `os.environ.setdefault` lines.

Append to `services/backend/tests/test_job_metadata_schema.py` (it has `make_job`):

```python
_KOLCHAK_TITLES = [{"index": i, "duration_seconds": d} for i, d in enumerate((3093, 3033, 3092, 3070, 3078, 542))]


def _scan(titles: list[dict]) -> dict:
    return {"disc_type": "bluray", "titles": titles}


def test_jobview_looks_episodic_from_the_stored_scan() -> None:
    assert JobView.model_validate(make_job(metadata_json={"scan_result": _scan(_KOLCHAK_TITLES)})).looks_episodic is True
    feature = [{"index": 0, "duration_seconds": 6960}, {"index": 1, "duration_seconds": 900}]
    assert JobView.model_validate(make_job(metadata_json={"scan_result": _scan(feature)})).looks_episodic is False
    assert JobView.model_validate(make_job(metadata_json={})).looks_episodic is False


def _ids(**ids: str) -> dict:
    return {"identity": {"provider": "tmdb", "external_ids": ids}}


def test_jobview_has_series_by_ids() -> None:
    assert JobView.model_validate(make_job(metadata_json=_ids(tmdb="5084", tmdb_kind="tv"))).has_series is True
    assert JobView.model_validate(make_job(metadata_json=_ids(tvdb="77170"))).has_series is True
    assert JobView.model_validate(make_job(metadata_json=_ids(tvmaze="1234"))).has_series is True
    assert JobView.model_validate(make_job(metadata_json=_ids(tmdb="1749913", tmdb_kind="movie"))).has_series is False
    assert JobView.model_validate(make_job(metadata_json=_ids(imdb="tt0071003"))).has_series is False
    assert JobView.model_validate(make_job(metadata_json={})).has_series is False


def test_jobview_has_series_when_a_source_resolved_a_show() -> None:
    md = {"identity_claims": {"sources": {"episodes_tvmaze": {"status": "ok", "inputs": {"show_id": "1234"}}}}}
    assert JobView.model_validate(make_job(metadata_json=md)).has_series is True
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest -q -k "common_disc_shape or looks_episodic or has_series"; echo $?`
Expected: disc_shape tests pass (copied), JobView tests fail `AttributeError: 'JobView' object has no attribute 'looks_episodic'`.

- [ ] **Step 3: Implement** — in `schemas/jobs.py` add imports `from pydantic import computed_field`, `from arm_common.disc_shape import looks_episodic as _looks_episodic`, `from arm_common.schemas.identity import IdentityClaims`, and to `JobView`:

```python
    @computed_field  # type: ignore[prop-decorator]
    @property
    def looks_episodic(self) -> bool:
        """The stored scan looks like a TV disc (several same-length episode
        titles, no feature): the title search defaults to TV (spec 3.3)."""
        scan = self.metadata_json.scan_result
        return bool(scan and _looks_episodic(scan.titles))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_series(self) -> bool:
        """A TV show is known: a TMDb id of kind tv, a TVDB or TVmaze id, or a
        show id some episode source resolved (spec 3.4). False means the
        Match Episodes tab asks for the series first."""
        identity = self.metadata_json.identity
        ids = identity.external_ids if identity else None
        if ids and ((ids.tmdb and ids.tmdb_kind == "tv") or ids.tvdb or ids.tvmaze):
            return True
        claims = self.metadata_json.identity_claims
        if isinstance(claims, IdentityClaims):
            return any(src.inputs.get("show_id") for src in claims.sources.values())
        return False
```

If importing `IdentityClaims` here creates a circular import (it is in `arm_common.schemas.identity`, already imported by `job_metadata.py`), import it inside the property instead.

- [ ] **Step 4: Run all suites (computed fields appear in every JobView response)**

Run: `uv run pytest -q; echo $?`
Expected: exit 0. Any test asserting a JobView JSON body with `==` on the whole dict needs the two keys; update such assertions by adding `"looks_episodic": False, "has_series": False` (do not loosen them).

- [ ] **Step 5: Regenerate API artifacts and commit**

```bash
bash devtools/regen-openapi-snapshot.sh
bash services/ui-neu/scripts/codegen.sh
git add packages/arm_common services/backend/tests/test_job_metadata_schema.py services/ui-neu/openapi.snapshot.json services/ui-neu/frontend/src/lib/types/api.gen.ts
git commit -m "feat(jobs): JobView.looks_episodic and has_series"
```

(The regenerated artifacts also carry Tasks 1, 4 and 5's schema changes.)

---

### Task 8: UI API layer

**Files:**
- Create: `services/ui-neu/frontend/src/lib/api/identity.ts`
- Modify: `services/ui-neu/frontend/src/lib/api/jobs.ts` (`resolveJob`, new `setJobMediaType`, delete lines 290-310 stubs)
- Test: `services/ui-neu/frontend/src/lib/__tests__/identity-api.test.ts` (new); `src/lib/__tests__/jobs-api-extra.test.ts` (remove the `MISSING in v3` block 238-246 and the two imports at 21-22)

**Interfaces:**
- Produces (TypeScript):
  - `fetchIdentity(jobId: string): Promise<IdentityView>`
  - `matchIdentity(jobId: string, req: MatchRequest): Promise<MatchPreview>`
  - `unpinIdentity(jobId: string): Promise<IdentityView>`
  - `fetchEpisodes(jobId: string, source: EpisodeSource, season: number): Promise<EpisodeListView>`
  - `type EpisodeSource = 'tmdb' | 'tvmaze' | 'tvdb'`
  - `resolveJob(jobId, body)` body gains `external_ids?: ExternalIds | null` (sent only when defined)
  - `setJobMediaType(jobId: string, mediaType: 'movie' | 'tv'): Promise<JobView>`

- [ ] **Step 1: Write the failing test**

```ts
// src/lib/__tests__/identity-api.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

const get = vi.fn();
const post = vi.fn();
const del = vi.fn();
const apiFetch = vi.fn();
vi.mock('$lib/api/client', () => ({
	get: (...a: unknown[]) => get(...a),
	post: (...a: unknown[]) => post(...a),
	del: (...a: unknown[]) => del(...a),
	apiFetch: (...a: unknown[]) => apiFetch(...a)
}));

import { fetchIdentity, matchIdentity, unpinIdentity, fetchEpisodes } from '$lib/api/identity';
import { resolveJob, setJobMediaType } from '$lib/api/jobs';

beforeEach(() => vi.clearAllMocks());

describe('identity api', () => {
	it('reads the identity', async () => {
		await fetchIdentity('job_1');
		expect(get).toHaveBeenCalledWith('/api/jobs/job_1/identity');
	});
	it('previews and applies a match', async () => {
		await matchIdentity('job_1', { source: 'tvmaze', season: 1, apply: false });
		expect(post).toHaveBeenCalledWith('/api/jobs/job_1/identity/match', { source: 'tvmaze', season: 1, apply: false });
	});
	it('unpins', async () => {
		await unpinIdentity('job_1');
		expect(del).toHaveBeenCalledWith('/api/jobs/job_1/identity/pin');
	});
	it('lists a season', async () => {
		await fetchEpisodes('job_1', 'tmdb', 1);
		expect(get).toHaveBeenCalledWith('/api/jobs/job_1/identity/episodes?source=tmdb&season=1');
	});
});

describe('jobs api ids and type', () => {
	it('resolve sends the picked ids', async () => {
		const ids = { tmdb: '5084', imdb: 'tt0071003', tvdb: '77170', tmdb_kind: 'tv' as const };
		await resolveJob('job_1', { title: 'Kolchak', year: 1974, media_type: 'tv', external_ids: ids });
		expect(post).toHaveBeenCalledWith('/api/jobs/job_1/resolve', expect.objectContaining({ external_ids: ids }));
	});
	it('resolve omits ids when none were picked', async () => {
		await resolveJob('job_1', { title: 'X' });
		expect(post.mock.calls[0][1]).not.toHaveProperty('external_ids');
	});
	it('switches the media type alone', async () => {
		await setJobMediaType('job_1', 'tv');
		expect(apiFetch).toHaveBeenCalledWith('/api/jobs/job_1', { method: 'PATCH', body: JSON.stringify({ media_type: 'tv' }) });
	});
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd services/ui-neu/frontend && npx vitest run src/lib/__tests__/identity-api.test.ts; echo $?`
Expected: FAIL `Failed to resolve import "$lib/api/identity"`, exit non-zero.

- [ ] **Step 3: Implement**

```ts
// src/lib/api/identity.ts
// v3 episode matching (design spec 2026-10-02 section 4): the identity view,
// match preview / apply, unpin, and a season's episode list for the picker.
import type { EpisodeListView, IdentityView, MatchPreview, MatchRequest } from '$lib/types/api.gen';
import { del, get, post } from './client';

export type EpisodeSource = 'tmdb' | 'tvmaze' | 'tvdb';

export function fetchIdentity(jobId: string): Promise<IdentityView> {
	return get<IdentityView>(`/api/jobs/${jobId}/identity`);
}

export function matchIdentity(jobId: string, req: MatchRequest): Promise<MatchPreview> {
	return post<MatchPreview>(`/api/jobs/${jobId}/identity/match`, req);
}

export function unpinIdentity(jobId: string): Promise<IdentityView> {
	return del<IdentityView>(`/api/jobs/${jobId}/identity/pin`);
}

export function fetchEpisodes(jobId: string, source: EpisodeSource, season: number): Promise<EpisodeListView> {
	return get<EpisodeListView>(`/api/jobs/${jobId}/identity/episodes?source=${source}&season=${season}`);
}
```

In `jobs.ts` `resolveJob`: add `external_ids?: ExternalIds | null;` to the body type (import `ExternalIds` from `api.gen`) and before `return`:

```ts
	if (body.external_ids !== undefined) {
		payload.external_ids = body.external_ids;
	}
```

Add after `updateJobTitle`:

```ts
// Header Movie | TV switch: the type alone; ids and title stay (spec 3.2).
export function setJobMediaType(jobId: string, mediaType: 'movie' | 'tv'): Promise<JobView> {
	return patchJob(jobId, { media_type: mediaType });
}
```

Delete the `tvdbMatch` / `fetchTvdbEpisodes` stubs (290-310) and, if `notAvailable` is no longer imported anywhere in `jobs.ts`, its import. Remove the `MISSING in v3` block and imports from `jobs-api-extra.test.ts`.

- [ ] **Step 4: Run to verify pass**

Run: `npx vitest run src/lib/__tests__; echo $?`
Expected: exit 0. (`EpisodeMatch.svelte` / `TvdbMatch.svelte` still import the stubs: Task 14 deletes them; until then run only the listed tests.)

- [ ] **Step 5: Commit**

```bash
git add src/lib/api/identity.ts src/lib/api/jobs.ts src/lib/__tests__/identity-api.test.ts src/lib/__tests__/jobs-api-extra.test.ts
git commit -m "feat(ui-neu): identity API module; resolve sends ids; media type switch call"
```

---

### Task 9: Episode panel model (pure, no Svelte)

**Files:**
- Create: `services/ui-neu/frontend/src/lib/components/episodes/episodeModel.ts`
- Test: `services/ui-neu/frontend/src/lib/components/episodes/__tests__/episodeModel.test.ts`

**Interfaces:**
- Consumes: `IdentityView`, `TrackView`, `JobView`, `MatchPreview` from `api.gen`.
- Produces:

```ts
export type PanelState = 'noseries' | 'matching' | 'unavailable' | 'nomatch' | 'suggestion' | 'pinned' | 'applied';
export type Origin = { kind: 'auto' | 'suggestion' | 'you' | 'none'; source: string | null };
export interface EpisodeRow {
	trackId: string; ref: string; length: string;
	code: string;        // 'S01E03', 'S01E03-E04', 'Extra', 'Trailer', 'Other', 'Not placed'
	name: string;        // episode name or ''
	origin: Origin;
	confidence: number | null;
	proposed: { code: string; name: string; confidence: number | null } | null;
	changed: boolean;
	handSet: boolean;
}
export const SOURCE_LABEL: Record<string, string>; // episodes_tmdb -> 'TMDb', episodes_tvmaze -> 'TVmaze', episodes_tvdb -> 'TVDB'
export function panelState(job: JobView, identity: IdentityView | null, matching: boolean): PanelState;
export function activeSource(identity: IdentityView): string | null;   // source id in effect, e.g. 'episodes_tmdb'
export function buildRows(tracks: TrackView[], identity: IdentityView, preview: MatchPreview | null): EpisodeRow[];
export function placedCount(rows: EpisodeRow[]): number;
export function formatLength(seconds: number | null | undefined): string; // 3093 -> '51:33', 542 -> '9:02'
```

Rules (from spec 4.2 / 4.4 and the design):
- `panelState`: `!job.has_series` → `noseries`; `matching` → `matching`; no source with `status` in `ok/miss/skipped/error` → `unavailable`; `identity.pin.episode` set → `pinned`; the active source's summary has `suggestion: true` → `suggestion`; every source `miss`/`skipped` (none `ok`) → `nomatch`; else `applied`.
- `activeSource`: `pin.episode` mapped to its source id (`'tmdb'` → `'episodes_tmdb'`), else the first `ok` source in `identity.sources` order.
- Row `origin`: `identity_provenance.episode_number === 'manual'` (or `role === 'manual'`) → `you`; else provenance names a source id → `suggestion` when that source's summary is a suggestion, else `auto`; else `none`.
- Row placement: `role` `extra|trailer|other` → that word capitalized; `episode_number` set → `S{season:02}E{ep:02}` (+ `-E{end:02}` when `episode_number_end`); for a suggestion row with no stored episode, use `proposals[activeSource]` (`episode`, `episode_end`, `episode_name`, `confidence`); otherwise `Not placed`.
- `confidence`: the active source's proposal `confidence` for that track, else null.
- `proposed`/`changed`: from `preview.outcomes[0].matches` by `source_ref`; `changed` when the proposed code differs from the current code.

- [ ] **Step 1: Write the failing tests**

```ts
import { describe, it, expect } from 'vitest';
import { panelState, buildRows, placedCount, formatLength, activeSource } from '../episodeModel';
import type { IdentityView, JobView, TrackView, MatchPreview } from '$lib/types/api.gen';

const job = (o: Partial<JobView> = {}) => ({ has_series: true, looks_episodic: true, media_type: 'tv', ...o }) as JobView;
const LENGTHS = [3093, 3033, 3092, 3070, 3078, 542];
const NAMES = ['The Ripper', 'The Zombie', 'They Have Been, They Are, They Will Be...', 'The Vampire', 'The Werewolf'];
const tracks = LENGTHS.map((d, i) => ({ id: `trk_${i}`, source_ref: `t0${i}`, duration_seconds: d }) as TrackView);

function identity(o: Partial<IdentityView> = {}, suggestion = false): IdentityView {
	return {
		sources: { episodes_tmdb: { status: 'ok', suggestion } },
		pin: {},
		tracks: LENGTHS.map((_, i) => ({
			track_id: `trk_${i}`, source_ref: `t0${i}`,
			role: i === 5 ? 'extra' : 'episode',
			season: i === 5 || suggestion ? null : 1,
			episode_number: i === 5 || suggestion ? null : i + 1,
			episode_name: i === 5 || suggestion ? null : NAMES[i],
			identity_provenance: i === 5 ? {} : { episode_number: 'episodes_tmdb' },
			proposals: i === 5 ? {} : { episodes_tmdb: { season: 1, episode: i + 1, episode_name: NAMES[i], confidence: suggestion ? 0.6 : 0.9 } }
		})),
		...o
	};
}

describe('panelState', () => {
	it('asks for the series when none is known (e.g. a movie id)', () => {
		expect(panelState(job({ has_series: false }), identity(), false)).toBe('noseries');
	});
	it('matching wins over stored rows', () => expect(panelState(job(), identity(), true)).toBe('matching'));
	it('applied / suggestion / pinned', () => {
		expect(panelState(job(), identity(), false)).toBe('applied');
		expect(panelState(job(), identity({}, true), false)).toBe('suggestion');
		expect(panelState(job(), identity({ pin: { episode: 'tmdb' } }), false)).toBe('pinned');
	});
	it('no match when every source missed', () => {
		const id = identity({ sources: { episodes_tmdb: { status: 'miss' }, episodes_tvdb: { status: 'skipped' } } });
		expect(panelState(job(), id, false)).toBe('nomatch');
	});
	it('unavailable with no sources at all', () => expect(panelState(job(), identity({ sources: {} }), false)).toBe('unavailable'));
});

describe('buildRows', () => {
	it('applied rows read Kolchak disc 1', () => {
		const rows = buildRows(tracks, identity(), null);
		expect(rows.map((r) => r.code)).toEqual(['S01E01', 'S01E02', 'S01E03', 'S01E04', 'S01E05', 'Extra']);
		expect(rows[3]).toMatchObject({ ref: 't03', length: '51:10', name: 'The Vampire', origin: { kind: 'auto', source: 'episodes_tmdb' }, confidence: 0.9 });
		expect(rows[5].origin.kind).toBe('none');
		expect(placedCount(rows)).toBe(6);
	});
	it('suggestion rows come from the proposals and say so', () => {
		const rows = buildRows(tracks, identity({}, true), null);
		expect(rows[0]).toMatchObject({ code: 'S01E01', origin: { kind: 'suggestion' }, confidence: 0.6 });
	});
	it('a hand-set row is "you"', () => {
		const id = identity();
		id.tracks![5].identity_provenance = { role: 'manual' };
		expect(buildRows(tracks, id, null)[5]).toMatchObject({ handSet: true, origin: { kind: 'you' } });
	});
	it('a preview marks changed rows', () => {
		const preview: MatchPreview = { outcomes: [{ source_id: 'episodes_tvmaze', matches: [
			{ source_ref: 't00', season: 1, episode: 2, episode_name: 'The Zombie', confidence: 0.81 },
			{ source_ref: 't01', season: 1, episode: 1, episode_name: 'The Ripper', confidence: 0.79 },
			{ source_ref: 't02', season: 1, episode: 3, episode_name: NAMES[2], confidence: 0.9 }
		] }] };
		const rows = buildRows(tracks, identity(), preview);
		expect(rows.filter((r) => r.changed).map((r) => r.ref)).toEqual(['t00', 't01']);
		expect(rows[0].proposed).toEqual({ code: 'S01E02', name: 'The Zombie', confidence: 0.81 });
	});
	it('a span renders E03-E04', () => {
		const id = identity();
		id.tracks![2].episode_number_end = 4;
		expect(buildRows(tracks, id, null)[2].code).toBe('S01E03-E04');
	});
});

it('formatLength', () => {
	expect(formatLength(3093)).toBe('51:33');
	expect(formatLength(542)).toBe('9:02');
	expect(formatLength(null)).toBe('—');
});
it('activeSource maps a pin to its source id', () => {
	expect(activeSource(identity({ pin: { episode: 'tvmaze' } }))).toBe('episodes_tvmaze');
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run src/lib/components/episodes; echo $?`
Expected: FAIL `Failed to resolve import "../episodeModel"`.

- [ ] **Step 3: Implement** `episodeModel.ts`

```ts
import type { IdentityView, JobView, MatchPreview, TrackIdentityView, TrackView } from '$lib/types/api.gen';

export type PanelState = 'noseries' | 'matching' | 'unavailable' | 'nomatch' | 'suggestion' | 'pinned' | 'applied';
export type Origin = { kind: 'auto' | 'suggestion' | 'you' | 'none'; source: string | null };
export interface EpisodeRow {
	trackId: string;
	ref: string;
	length: string;
	code: string;
	name: string;
	origin: Origin;
	confidence: number | null;
	proposed: { code: string; name: string; confidence: number | null } | null;
	changed: boolean;
	handSet: boolean;
}

export const SOURCE_LABEL: Record<string, string> = {
	episodes_tmdb: 'TMDb',
	episodes_tvmaze: 'TVmaze',
	episodes_tvdb: 'TVDB'
};
const RAN = new Set(['ok', 'miss', 'skipped', 'error']);
const NON_EPISODE: Record<string, string> = { extra: 'Extra', trailer: 'Trailer', other: 'Other' };

const pad = (n: number) => String(n).padStart(2, '0');

function episodeCode(season: number | null | undefined, ep: number | null | undefined, end?: number | null): string | null {
	if (ep == null) return null;
	const span = end != null && end !== ep ? `-E${pad(end)}` : '';
	return `S${pad(season ?? 1)}E${pad(ep)}${span}`;
}

export function formatLength(seconds: number | null | undefined): string {
	if (seconds == null) return '—';
	const m = Math.floor(seconds / 60);
	return `${m}:${pad(seconds % 60)}`;
}

export function activeSource(identity: IdentityView): string | null {
	const pinned = identity.pin?.episode;
	if (pinned) return `episodes_${pinned}`;
	const sources = identity.sources ?? {};
	return Object.keys(sources).find((id) => sources[id]?.status === 'ok') ?? null;
}

export function panelState(job: JobView, identity: IdentityView | null, matching: boolean): PanelState {
	if (!job.has_series) return 'noseries';
	if (matching) return 'matching';
	const sources = identity?.sources ?? {};
	const ran = Object.values(sources).filter((s) => RAN.has(s?.status ?? 'ok'));
	if (!identity || ran.length === 0) return 'unavailable';
	if (identity.pin?.episode) return 'pinned';
	const active = activeSource(identity);
	if (active && sources[active]?.suggestion) return 'suggestion';
	if (!ran.some((s) => (s?.status ?? 'ok') === 'ok')) return 'nomatch';
	return 'applied';
}

function origin(t: TrackIdentityView, identity: IdentityView): Origin {
	const prov = t.identity_provenance ?? {};
	const src = prov.episode_number ?? prov.role ?? null;
	if (src === 'manual') return { kind: 'you', source: null };
	if (src && src.startsWith('episodes_')) {
		return { kind: identity.sources?.[src]?.suggestion ? 'suggestion' : 'auto', source: src };
	}
	return { kind: 'none', source: null };
}

export function buildRows(tracks: TrackView[], identity: IdentityView, preview: MatchPreview | null): EpisodeRow[] {
	const byTrack = new Map((identity.tracks ?? []).map((t) => [t.track_id, t]));
	const active = activeSource(identity);
	const matches = new Map((preview?.outcomes?.[0]?.matches ?? []).map((m) => [m.source_ref, m]));
	return tracks.map((track) => {
		const t = byTrack.get(track.id);
		const o: Origin = t ? origin(t, identity) : { kind: 'none', source: null };
		const proposal = t && active ? t.proposals?.[active] : undefined;
		let code: string | null = null;
		let name = '';
		if (t?.role && NON_EPISODE[t.role]) code = NON_EPISODE[t.role];
		if (!code && t) {
			code = episodeCode(t.season, t.episode_number, t.episode_number_end);
			name = t.episode_name ?? '';
		}
		if (!code && proposal && o.kind !== 'you' && identity.sources?.[active ?? '']?.suggestion) {
			code = episodeCode(proposal.season, proposal.episode, proposal.episode_end);
			name = proposal.episode_name ?? '';
			o.kind = 'suggestion';
			o.source = active;
		}
		const m = matches.get(track.source_ref);
		const proposed = m
			? { code: episodeCode(m.season, m.episode, m.episode_end) ?? 'Not placed', name: m.episode_name ?? '', confidence: m.confidence ?? null }
			: null;
		const current = code ?? 'Not placed';
		return {
			trackId: track.id,
			ref: track.source_ref,
			length: formatLength(track.duration_seconds),
			code: current,
			name,
			origin: o,
			confidence: proposal?.confidence ?? null,
			proposed,
			changed: proposed !== null && proposed.code !== current,
			handSet: o.kind === 'you'
		};
	});
}

export function placedCount(rows: EpisodeRow[]): number {
	return rows.filter((r) => r.code !== 'Not placed').length;
}
```

- [ ] **Step 4: Run to verify pass**

Run: `npx vitest run src/lib/components/episodes; echo $?`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add src/lib/components/episodes
git commit -m "feat(ui-neu): episode panel model (states, rows, preview diff)"
```

---

### Task 10: EpisodeMatchPanel — read-only states

**Files:**
- Create: `services/ui-neu/frontend/src/lib/components/episodes/EpisodeMatchPanel.svelte`
- Test: `services/ui-neu/frontend/src/lib/components/episodes/__tests__/EpisodeMatchPanel.test.ts`

**Interfaces:**
- Consumes: `fetchIdentity` (Task 8), `fetchNamingPreview` (existing), Task 9 model.
- Produces: `<EpisodeMatchPanel job={JobView} tracks={TrackView[]} matching={boolean} onsearchseries={() => void} />` with `export function reload(): Promise<void>` (the page calls it on `job.identity_updated`).

Markup follows `MatchEpisodesPanel.dc.html` using ui-neu classes, not the design's inline rgb values:
- Status line: `role="status"`, eyebrow "Episodes", source chip `chip chip-sm chip-info` (`SOURCE_LABEL`), state chip (`chip-success` "Applied automatically" / `chip-warning` "Suggestion, not applied" / `chip-info` "Pinned by you" / `chip` "No match"), "N of M tracks placed", "Other sources ▾" button (`aria-expanded`), "Re-run…" button (Task 11).
- Other sources strip: one item per non-active source, `"<Label> <status> · <detail>"`.
- Banners: suggestion (`alert alert-warning`, title "<Source>'s best match is too uncertain to apply on its own"), pinned (`alert alert-info` "<Source> is pinned."), nomatch (`alert alert-info` "No source could place these tracks"), noseries (dashed panel "Pick the series first", text "This job is TV, but it has no series identity, so there are no episode lists to match against.", admin button "Search for the series" → `onsearchseries`), unavailable (`alert alert-warning` "No episode source is set up", link `/settings#metadata`).
- Matching: indeterminate bar (`progress` block) + "Matching episodes…" text; rows show "Waiting for matcher".
- Rows: `<table class="table">` with columns Track · Length · Placement (code bold + name; second line the file name from `fetchNamingPreview` item matching the track id, monospace, `title` attribute holds the full text) · Origin (chip: "Auto · TMDb" `chip-info`, "Suggestion · TMDb" `chip-warning`, "Set by you" `chip` with `data-origin="you"`, "—") · Conf. (two decimals). Below 640px the table is replaced by stacked cards (render both, toggle with the existing `sm:` utility pattern used in `IsoSourceChip`).
- Guest (`!$isAdmin`): same content, footer "View only. Sign in as an admin to change episodes.", no Re-run / Accept / Unpin / pickers / Revert elements at all.

- [ ] **Step 1: Write the failing tests**

```ts
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent } from '$lib/test-utils';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return { role: { subscribe: _role.subscribe }, isAdmin: derived(_role, (r) => r === 'admin'), __setRole: (r: string | null) => _role.set(r) };
});
const fetchIdentity = vi.fn();
vi.mock('$lib/api/identity', () => ({
	fetchIdentity: (...a: unknown[]) => fetchIdentity(...a),
	matchIdentity: vi.fn(), unpinIdentity: vi.fn(), fetchEpisodes: vi.fn(() => Promise.resolve({ source_id: 'episodes_tmdb', show_id: '5084', season: 1, episodes: [] }))
}));
vi.mock('$lib/api/jobs', () => ({ fetchNamingPreview: vi.fn(() => Promise.resolve({ items: [] })), updateTrack: vi.fn() }));

import EpisodeMatchPanel from '../EpisodeMatchPanel.svelte';
import type { IdentityView, JobView, TrackView } from '$lib/types/api.gen';

const LENGTHS = [3093, 3033, 3092, 3070, 3078, 542];
const tracks = LENGTHS.map((d, i) => ({ id: `trk_${i}`, source_ref: `t0${i}`, duration_seconds: d }) as TrackView);
const job = (o: Partial<JobView> = {}) => ({ id: 'job_1', has_series: true, media_type: 'tv', ...o }) as JobView;
const applied: IdentityView = {
	sources: { episodes_tmdb: { status: 'ok' }, episodes_tvmaze: { status: 'ok', detail: 'matched 5 of 6' } },
	pin: {},
	tracks: LENGTHS.map((_, i) => ({ track_id: `trk_${i}`, source_ref: `t0${i}`, role: i === 5 ? 'extra' : 'episode', season: 1,
		episode_number: i === 5 ? null : i + 1, episode_name: i === 5 ? null : `Ep ${i + 1}`,
		identity_provenance: i === 5 ? {} : { episode_number: 'episodes_tmdb' },
		proposals: { episodes_tmdb: { episode: i + 1, confidence: 0.9 } } }))
};

beforeEach(() => fetchIdentity.mockResolvedValue(applied));
afterEach(async () => {
	cleanup();
	((await import('$lib/stores/auth')) as unknown as { __setRole: (r: string) => void }).__setRole('admin');
});

describe('EpisodeMatchPanel', () => {
	it('applied: status line, rows and origin', async () => {
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		expect(await screen.findByText('Applied automatically')).toBeInTheDocument();
		expect(screen.getByText('6 of 6 tracks placed')).toBeInTheDocument();
		expect(screen.getAllByText('S01E04')[0]).toBeInTheDocument();
		expect(screen.getAllByText('Auto · TMDb').length).toBeGreaterThan(0);
	});
	it('other sources open inline', async () => {
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		await fireEvent.click(await screen.findByRole('button', { name: /Other sources/ }));
		expect(screen.getByText(/matched 5 of 6/)).toBeInTheDocument();
	});
	it('pick the series first when the job has no series', async () => {
		const onsearchseries = vi.fn();
		renderComponent(EpisodeMatchPanel, { props: { job: job({ has_series: false }), tracks, matching: false, onsearchseries } });
		await fireEvent.click(await screen.findByRole('button', { name: 'Search for the series' }));
		expect(onsearchseries).toHaveBeenCalled();
		expect(fetchIdentity).not.toHaveBeenCalled();
	});
	it('hides pickers and re-run while matching', async () => {
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: true } });
		expect(await screen.findByText(/Matching episodes/)).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: /Re-run/ })).toBeNull();
		expect(screen.queryByLabelText(/Set placement for/)).toBeNull();
	});
	it('guest sees rows but no controls', async () => {
		((await import('$lib/stores/auth')) as unknown as { __setRole: (r: string) => void }).__setRole('guest');
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		expect(await screen.findByText('6 of 6 tracks placed')).toBeInTheDocument();
		expect(screen.getByText(/View only/)).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: /Re-run/ })).toBeNull();
		expect(screen.queryByLabelText(/Set placement for/)).toBeNull();
	});
	it('unavailable when no episode source ran', async () => {
		fetchIdentity.mockResolvedValue({ sources: {}, pin: {}, tracks: [] });
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		expect(await screen.findByText('No episode source is set up')).toBeInTheDocument();
	});
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run src/lib/components/episodes; echo $?`
Expected: FAIL `Failed to resolve import "../EpisodeMatchPanel.svelte"`.

- [ ] **Step 3: Implement the component** (script outline; markup per the bullet list above)

```svelte
<script lang="ts">
	import type { IdentityView, JobView, NamingPreviewItem, TrackView } from '$lib/types/api.gen';
	import { fetchIdentity } from '$lib/api/identity';
	import { fetchNamingPreview } from '$lib/api/jobs';
	import { isAdmin } from '$lib/stores/auth';
	import { panelState, buildRows, placedCount, activeSource, SOURCE_LABEL } from './episodeModel';

	interface Props { job: JobView; tracks: TrackView[]; matching?: boolean; onsearchseries?: () => void }
	let { job, tracks, matching = false, onsearchseries }: Props = $props();

	let identity = $state<IdentityView | null>(null);
	let fileNames = $state(new Map<string, string>());
	let othersOpen = $state(false);
	let loadError = $state<string | null>(null);

	export async function reload(): Promise<void> {
		if (!job.has_series) return;
		try {
			identity = await fetchIdentity(job.id);
			loadError = null;
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Could not load episodes';
		}
		try {
			const preview = await fetchNamingPreview(job.id);
			fileNames = new Map((preview.items ?? []).map((i: NamingPreviewItem) => [i.track_id, i.filename ?? '']));
		} catch {
			/* file names are a nicety */
		}
	}

	$effect(() => { void job.id; void job.has_series; reload(); });

	const state = $derived(panelState(job, identity, matching));
	const rows = $derived(identity && state !== 'noseries' ? buildRows(tracks, identity, null) : []);
	const source = $derived(identity ? activeSource(identity) : null);
	const others = $derived(Object.entries(identity?.sources ?? {}).filter(([id]) => id !== source));
</script>
```

Check `NamingPreviewItem`'s field names in `api.gen.ts` (`track_id` and the rendered name field) and use them exactly.

- [ ] **Step 4: Run to verify pass**

Run: `npx vitest run src/lib/components/episodes; echo $?` then `npm run check; echo $?`
Expected: both exit 0.

- [ ] **Step 5: Commit**

```bash
git add src/lib/components/episodes
git commit -m "feat(ui-neu): Match Episodes panel, read-only states"
```

---

### Task 11: Accept, re-run with preview, apply & pin, unpin

**Files:**
- Modify: `services/ui-neu/frontend/src/lib/components/episodes/EpisodeMatchPanel.svelte`
- Test: `.../episodes/__tests__/EpisodeMatchPanel.test.ts` (append)

**Interfaces:**
- Consumes: `matchIdentity`, `unpinIdentity`, `EpisodeSource` (Task 8); `buildRows(tracks, identity, preview)` (Task 9).
- Produces: panel UI per design 1b-1e, 1j.

Behaviour:
- **Accept suggestion** (suggestion state, admin): `matchIdentity(job.id, { source: <active source without 'episodes_' prefix>, apply: true })`; button shows "Accepting…" until it resolves, then `reload()`.
- **Re-run…** toggles a panel with Source (`<select>` tmdb/tvmaze/tvdb; a source whose summary `status` is `skipped` with detail containing "not configured" is `disabled`), Season (number ≥0, default `job.season ?? 1`), Disc (number ≥1, default `job.disc_number ?? 1`), Tolerance (s) (1-1800, empty = default), **Preview** button.
- **Preview**: `matchIdentity(job.id, { source, season, disc_number, tolerance (omit when empty), apply: false })` → `preview` state; rows rebuilt with the preview; desktop shows the "Proposed · <Source>" column with `CHANGED` tags; phone (cards) shows the old placement struck through over the new one. A bar shows "<n> tracks change if you apply <Source>. Nothing is saved yet." with **Discard** (clears `preview`) and **Apply & pin <Source>** (`apply: true`, then clear preview, `reload()`). Pickers are hidden while a preview is shown. Changing any re-run field clears `preview`.
- **Error**: a rejected preview/apply shows `role="alert"` inside the re-run panel: "<Source> didn't answer (<message>). Nothing changed; the placement below is still <active source label>'s." with **Try again** repeating the last request. `identity` is not touched.
- **Unpin…** (pinned state): first click swaps the button for "Unpin and let ARM pick the source again?" + **Unpin** (calls `unpinIdentity`, then `identity = result`) + **Cancel**.

- [ ] **Step 1: Write the failing tests**

```ts
import { matchIdentity, unpinIdentity } from '$lib/api/identity';

it('previews then applies & pins', async () => {
	vi.mocked(matchIdentity).mockResolvedValueOnce({ outcomes: [{ source_id: 'episodes_tvmaze', matches: [
		{ source_ref: 't00', season: 1, episode: 2, episode_name: 'Ep 2', confidence: 0.81 }] }] })
		.mockResolvedValueOnce({ outcomes: [] });
	renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
	await fireEvent.click(await screen.findByRole('button', { name: /Re-run/ }));
	await fireEvent.change(screen.getByLabelText('Source'), { target: { value: 'tvmaze' } });
	await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
	expect(matchIdentity).toHaveBeenCalledWith('job_1', expect.objectContaining({ source: 'tvmaze', season: 1, apply: false }));
	expect(await screen.findByText(/1 track changes if you apply TVmaze/)).toBeInTheDocument();
	await fireEvent.click(screen.getByRole('button', { name: 'Apply & pin TVmaze' }));
	expect(matchIdentity).toHaveBeenLastCalledWith('job_1', expect.objectContaining({ source: 'tvmaze', apply: true }));
});

it('keeps the current placement when preview fails', async () => {
	vi.mocked(matchIdentity).mockRejectedValueOnce(new Error('HTTP 502'));
	renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
	await fireEvent.click(await screen.findByRole('button', { name: /Re-run/ }));
	await fireEvent.change(screen.getByLabelText('Source'), { target: { value: 'tvmaze' } });
	await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
	const alert = await screen.findByRole('alert');
	expect(alert).toHaveTextContent("TVmaze didn't answer");
	expect(alert).toHaveTextContent("still TMDb's");
	expect(screen.getAllByText('S01E01').length).toBeGreaterThan(0);
});

it('accepts a suggestion by pinning its source', async () => {
	fetchIdentity.mockResolvedValue({ ...applied, sources: { episodes_tmdb: { status: 'ok', suggestion: true } } });
	vi.mocked(matchIdentity).mockResolvedValue({ outcomes: [] });
	renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
	await fireEvent.click(await screen.findByRole('button', { name: 'Accept suggestion' }));
	expect(matchIdentity).toHaveBeenCalledWith('job_1', { source: 'tmdb', apply: true });
});

it('unpin asks inline first', async () => {
	fetchIdentity.mockResolvedValue({ ...applied, pin: { episode: 'tmdb' } });
	vi.mocked(unpinIdentity).mockResolvedValue({ ...applied, pin: {} });
	renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
	await fireEvent.click(await screen.findByRole('button', { name: 'Unpin…' }));
	expect(unpinIdentity).not.toHaveBeenCalled();
	await fireEvent.click(screen.getByRole('button', { name: 'Unpin' }));
	expect(unpinIdentity).toHaveBeenCalledWith('job_1');
});
```

- [ ] **Step 2: Run to verify failure** — `npx vitest run src/lib/components/episodes; echo $?` → the four new tests fail (no Re-run button / Accept / Unpin…).

- [ ] **Step 3: Implement** — add to the script:

```ts
	import { matchIdentity, unpinIdentity, type EpisodeSource } from '$lib/api/identity';
	import type { MatchPreview, MatchRequest } from '$lib/types/api.gen';

	let rerunOpen = $state(false);
	let rerun = $state<{ source: EpisodeSource; season: number; disc: number; tolerance: string }>({
		source: 'tmdb', season: job.season ?? 1, disc: job.disc_number ?? 1, tolerance: ''
	});
	let preview = $state<MatchPreview | null>(null);
	let busy = $state(false);
	let actionError = $state<string | null>(null);
	let lastRequest: MatchRequest | null = null;
	let unpinAsk = $state(false);

	const shortId = (id: string | null) => (id ?? '').replace(/^episodes_/, '') as EpisodeSource;

	function request(apply: boolean): MatchRequest {
		const req: MatchRequest = { source: rerun.source, season: rerun.season, disc_number: rerun.disc, apply };
		if (rerun.tolerance.trim()) req.tolerance = Number(rerun.tolerance);
		return req;
	}

	async function run(req: MatchRequest) {
		busy = true;
		actionError = null;
		lastRequest = req;
		try {
			const out = await matchIdentity(job.id, req);
			if (req.apply) { preview = null; rerunOpen = false; await reload(); } else { preview = out; }
		} catch (e) {
			const label = SOURCE_LABEL[`episodes_${req.source}`] ?? req.source;
			const still = SOURCE_LABEL[source ?? ''] ?? 'the current source';
			actionError = `${label} didn't answer (${e instanceof Error ? e.message : 'error'}). Nothing changed; the placement below is still ${still}'s.`;
		} finally {
			busy = false;
		}
	}

	async function accept() {
		await run({ source: shortId(source), apply: true });
	}

	async function unpin() {
		identity = await unpinIdentity(job.id);
		unpinAsk = false;
	}

	$effect(() => { void rerun.source; void rerun.season; void rerun.disc; void rerun.tolerance; preview = null; });
```

Note: `accept()` sends exactly `{ source, apply: true }` (test asserts equality). Rebuild `rows` with `buildRows(tracks, identity, preview)`. Add the markup per the Behaviour list; label the selects/inputs with `<label>` text "Source", "Season", "Disc", "Tolerance (s)".

- [ ] **Step 4: Run to verify pass** — `npx vitest run src/lib/components/episodes; echo $?` and `npm run check; echo $?` → exit 0.

- [ ] **Step 5: Commit** — `git commit -am "feat(ui-neu): accept, re-run with preview, apply & pin, unpin"`

---

### Task 12: Set by hand and revert

**Files:**
- Modify: `.../episodes/EpisodeMatchPanel.svelte`
- Test: `.../episodes/__tests__/EpisodeMatchPanel.test.ts` (append)

**Interfaces:**
- Consumes: `fetchEpisodes` (Task 8), `updateTrack(jobId, trackId, data: Omit<TrackEditRequest,'track_id'>)` (existing, `$lib/api/jobs`).

Behaviour (design 1a, 1c):
- Admin rows (not matching, no preview) get a "Set by hand" `<select aria-label="Set placement for t0N">` whose options are `Change…` (empty), the season's episodes from `fetchEpisodes(job.id, <active source short id>, <season>)` labelled `E03 The Vampire · 51m` (specials: `S00E01 The Night Stalker · 74m · special`, value `s<season>e<number>`), then Extra / Trailer / Other. Load the list once per (source, season).
- Picking an episode calls `updateTrack(job.id, trackId, { role: 'episode', season, episode_number, episode_name })`; picking Extra/Trailer/Other calls `updateTrack(job.id, trackId, { role })`; then `reload()`. Saved on change; no Save button.
- A `handSet` row shows **Revert** → `updateTrack(job.id, trackId, { revert_fields: ['role', 'season', 'episode_number', 'episode_number_end', 'episode_name'] })`, then `reload()`. No confirmation.

- [ ] **Step 1: Write the failing tests**

```ts
import { fetchEpisodes } from '$lib/api/identity';
import { updateTrack } from '$lib/api/jobs';

it('sets a track to Extra by hand', async () => {
	vi.mocked(fetchEpisodes).mockResolvedValue({ source_id: 'episodes_tmdb', show_id: '5084', season: 1,
		episodes: [{ number: 4, name: 'The Vampire', runtime_s: 3060 }] });
	renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
	const select = await screen.findByLabelText('Set placement for t04');
	await waitFor(() => expect(screen.getAllByText(/E04 The Vampire · 51m/).length).toBeGreaterThan(0));
	await fireEvent.change(select, { target: { value: 'extra' } });
	expect(updateTrack).toHaveBeenCalledWith('job_1', 'trk_4', { role: 'extra' });
});

it('picks an episode by hand', async () => {
	vi.mocked(fetchEpisodes).mockResolvedValue({ source_id: 'episodes_tmdb', show_id: '5084', season: 1,
		episodes: [{ number: 4, name: 'The Vampire', runtime_s: 3060 }] });
	renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
	const select = await screen.findByLabelText('Set placement for t03');
	await waitFor(() => expect(screen.getAllByText(/E04 The Vampire/).length).toBeGreaterThan(0));
	await fireEvent.change(select, { target: { value: 's1e4' } });
	expect(updateTrack).toHaveBeenCalledWith('job_1', 'trk_3', { role: 'episode', season: 1, episode_number: 4, episode_name: 'The Vampire' });
});

it('reverts a hand-set row', async () => {
	const handSet = structuredClone(applied);
	handSet.tracks![5].identity_provenance = { role: 'manual' };
	fetchIdentity.mockResolvedValue(handSet);
	renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
	await fireEvent.click(await screen.findByRole('button', { name: 'Revert' }));
	expect(updateTrack).toHaveBeenCalledWith('job_1', 'trk_5', { revert_fields: ['role', 'season', 'episode_number', 'episode_number_end', 'episode_name'] });
});
```

- [ ] **Step 2: Run to verify failure** — the three tests fail (no select / Revert).

- [ ] **Step 3: Implement** — add to the script:

```ts
	import { fetchEpisodes } from '$lib/api/identity';
	import { updateTrack } from '$lib/api/jobs';
	import type { EpisodeSummary } from '$lib/types/api.gen';

	let episodes = $state<EpisodeSummary[]>([]);
	let episodesKey = '';
	const REVERT = ['role', 'season', 'episode_number', 'episode_number_end', 'episode_name'] as const;

	$effect(() => {
		const src = shortId(source);
		const season = job.season ?? 1;
		const key = `${src}:${season}`;
		if (!source || key === episodesKey || !$isAdmin) return;
		episodesKey = key;
		fetchEpisodes(job.id, src, season).then((r) => (episodes = r.episodes ?? []), () => (episodes = []));
	});

	const optionLabel = (e: EpisodeSummary, season: number) =>
		`${e.special ? `S00E${pad(e.number)}` : `E${pad(e.number)}`} ${e.name ?? ''} · ${Math.round((e.runtime_s ?? 0) / 60)}m${e.special ? ' · special' : ''}`;

	async function setByHand(trackId: string, value: string) {
		if (!value) return;
		const season = job.season ?? 1;
		if (value === 'extra' || value === 'trailer' || value === 'other') {
			await updateTrack(job.id, trackId, { role: value });
		} else {
			const n = Number(value.split('e')[1]);
			const ep = episodes.find((e) => e.number === n);
			await updateTrack(job.id, trackId, { role: 'episode', season, episode_number: n, episode_name: ep?.name ?? null });
		}
		await reload();
	}

	async function revert(trackId: string) {
		await updateTrack(job.id, trackId, { revert_fields: [...REVERT] });
		await reload();
	}

	const pad = (n: number) => String(n).padStart(2, '0');
```

Option values: `s${season}e${number}` (specials `s0e${number}`). Render the select in the desktop "Set by hand" column and full-width (min-height 44px) in phone cards.

- [ ] **Step 4: Run to verify pass** — `npx vitest run src/lib/components/episodes; echo $?`, `npm run check; echo $?` → 0.

- [ ] **Step 5: Commit** — `git commit -am "feat(ui-neu): set a track's episode by hand; revert"`

---

### Task 13: TitleSearch — Movie / TV toggle, ids on apply

**Files:**
- Modify: `services/ui-neu/frontend/src/lib/components/TitleSearch.svelte`
- Test: `services/ui-neu/frontend/src/lib/components/TitleSearch.test.ts` (append; update the existing apply assertion)

**Interfaces:**
- Consumes: `searchMetadata(query, type)`, `resolveJob(..., { external_ids })` (Task 8), `MetadataCandidate.external_ids` (Task 4), `JobView.looks_episodic` (Task 7).
- Produces: props `{ job; onapply?; onseries?: () => void; initialType?: 'movie' | 'tv' }` (`onepisodes` removed). `onseries` fires after a TV result is applied.

Behaviour: a `role="radiogroup" aria-label="Search type"` pair of buttons Movie / TV (reuse the `tabs tabs-pills` classes) before the search button; default `initialType ?? (job.media_type === 'tv' || (job.media_type == null && job.looks_episodic) ? 'tv' : 'movie')`; search calls `searchMetadata(query, searchType)`; changing the type clears results. Apply sends `external_ids: selected.external_ids ?? undefined` and `media_type` from the edit form; after success, if the applied type is TV call `onseries?.()`, else `onapply?.()`. Remove the "Match Episodes" button and `showEpisodes`.

- [ ] **Step 1: Write the failing tests**

```ts
it('defaults to TV for an episodic disc and searches TV', async () => {
	mockSearchMetadata.mockResolvedValue({ candidates: [] });
	renderComponent(TitleSearch, { props: { job: createJob({ title: 'kolchak', media_type: null, looks_episodic: true }) } });
	expect(screen.getByRole('radio', { name: 'TV' })).toHaveAttribute('aria-checked', 'true');
	await fireEvent.click(screen.getByText('Search'));
	expect(mockSearchMetadata).toHaveBeenCalledWith('kolchak', 'tv');
});

it('applying a series sends its ids and opens episode matching', async () => {
	const ids = { tmdb: '5084', imdb: 'tt0071003', tvdb: '77170', tmdb_kind: 'tv' };
	mockSearchMetadata.mockResolvedValue({ candidates: [createCandidate({ title: 'Kolchak: The Night Stalker', year: 1974, kind: 'tv', external_ids: ids })] });
	const onseries = vi.fn();
	renderComponent(TitleSearch, { props: { job: createJob({ id: 'job_9', status: 'ripped', title: 'kolchak', media_type: 'tv' }), onseries } });
	await fireEvent.click(screen.getByText('Search'));
	await fireEvent.click(await screen.findByText('Kolchak: The Night Stalker'));
	await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
	await waitFor(() => expect(mockResolve).toHaveBeenCalledWith('job_9', { title: 'Kolchak: The Night Stalker', year: 1974, media_type: 'tv', external_ids: ids }));
	expect(onseries).toHaveBeenCalled();
});
```

Update the existing `'resolvable job: Apply resolves title/year + applies the poster'` expectation to `{ title: 'The Matrix', year: 1999, media_type: 'movie', external_ids: undefined }`, and make `createJob` / `createCandidate` accept the new fields (add `looks_episodic: false, has_series: false` defaults to `createJob` in `__fixtures__/job.ts`).

- [ ] **Step 2: Run to verify failure** — `npx vitest run src/lib/components/TitleSearch.test.ts; echo $?` → new tests fail.

- [ ] **Step 3: Implement** — add `searchType` state and the radiogroup; pass `searchType` to `searchMetadata`; in `applyResult` build the `resolveJob` body with `external_ids: selected?.external_ids ?? undefined`; replace the post-apply `onapply?.()` with `if (editType === 'series') onseries?.(); else onapply?.();`; delete `onepisodes` and the "Match Episodes" button.

- [ ] **Step 4: Run to verify pass** — `npx vitest run src/lib/components/TitleSearch.test.ts; echo $?`, `npm run check; echo $?` → 0.

- [ ] **Step 5: Commit** — `git commit -am "feat(ui-neu): title search Movie/TV toggle; applying a result stores its ids"`

---

### Task 14: Wire the job page; header switch; remove the v2 matcher

**Files:**
- Create: `services/ui-neu/frontend/src/lib/components/episodes/MediaTypeSwitch.svelte`
- Modify: `services/ui-neu/frontend/src/routes/jobs/[id]/+page.svelte`
- Delete: `src/lib/components/EpisodeMatch.svelte`, `EpisodeMatch.test.ts`, `TvdbMatch.svelte`, `TvdbMatch.test.ts`
- Test: `services/ui-neu/frontend/src/routes/jobs/[id]/page.test.ts` (append; add `setJobMediaType` to its `$lib/api/jobs` mock and a `$lib/api/identity` mock)

**Interfaces:**
- Consumes: `setJobMediaType` (Task 8), `EpisodeMatchPanel` (Tasks 10-12), `TitleSearch` `onseries` / `initialType` (Task 13), `ConfirmDialog` (existing: `{ open, title, message, confirmLabel, variant, onconfirm, oncancel }`).
- Produces: `<MediaTypeSwitch job={JobView} handSetCount={number} onchanged={() => void} />`.

Behaviour:
- Tab bar (video discs): the existing "Poster & metadata search" button stays; add **Match Episodes** (`activePanel === 'episodes'`) only when `job.media_type === 'tv'`. `activePanel` type becomes `'title' | 'music' | 'episodes' | null`.
- Episodes panel: `<EpisodeMatchPanel bind:this={episodePanel} {job} {tracks} matching={matching} onsearchseries={() => { titleInitialType = 'tv'; activePanel = 'title'; }} />`.
- `matching`: set `true` right after a type flip or a series apply; cleared when a `job.identity_updated`-carrying refresh arrives (the existing `onRipperEvent` listener: call `loadJob()` and `episodePanel?.reload()`, then `matching = false`).
- TitleSearch: `onseries={() => { activePanel = 'episodes'; matching = true; loadJob(); }}`, `initialType={titleInitialType}`.
- Header: `MediaTypeSwitch` next to the status badge for video discs, admin only; guests see plain text "TV" / "Movie". Switching to Movie when `handSetCount > 0` (tracks whose `identity_provenance.episode_number` or `.role` is `manual`) opens `ConfirmDialog` with title "Switch to Movie?" and message "<n> tracks have episodes you set by hand. Switch to Movie anyway?". On change: `setJobMediaType`, then `onchanged()` (page: `matching = newType === 'tv'; activePanel = newType === 'tv' ? 'episodes' : null; loadJob()`).

- [ ] **Step 1: Write the failing tests** (page.test.ts)

```ts
it('shows Match Episodes only for TV jobs', async () => {
	mockFetchJob.mockResolvedValue(createJobDetail({ job: createJob({ id: 'job_42', media_type: 'tv', disc_type: 'bluray', has_series: true }) }));
	renderComponent(Page);
	expect(await screen.findByRole('button', { name: 'Match Episodes' })).toBeInTheDocument();
});

it('the header switch flips a movie to TV and opens episode matching', async () => {
	mockFetchJob.mockResolvedValue(createJobDetail({ job: createJob({ id: 'job_42', media_type: 'movie', disc_type: 'bluray' }) }));
	vi.mocked(setJobMediaType).mockResolvedValue(createJob({ id: 'job_42', media_type: 'tv' }));
	renderComponent(Page);
	await fireEvent.click(await screen.findByRole('radio', { name: 'TV' }));
	expect(setJobMediaType).toHaveBeenCalledWith('job_42', 'tv');
});

it('asks before switching a job with hand-set episodes to Movie', async () => {
	const tracks = [createTrack({ id: 'trk_1', identity_provenance: { episode_number: 'manual' } })];
	mockFetchJob.mockResolvedValue(createJobDetail({ job: createJob({ id: 'job_42', media_type: 'tv', disc_type: 'bluray', has_series: true }), tracks }));
	renderComponent(Page);
	await fireEvent.click(await screen.findByRole('radio', { name: 'Movie' }));
	expect(setJobMediaType).not.toHaveBeenCalled();
	expect(screen.getByText(/1 track has episodes you set by hand/)).toBeInTheDocument();
});
```

(Use singular "1 track has" / plural "<n> tracks have" in the message.)

- [ ] **Step 2: Run to verify failure** — `npx vitest run 'src/routes/jobs/[id]'; echo $?` → new tests fail.

- [ ] **Step 3: Implement** `MediaTypeSwitch.svelte`:

```svelte
<script lang="ts">
	import type { JobView } from '$lib/types/api.gen';
	import { setJobMediaType } from '$lib/api/jobs';
	import ConfirmDialog from '$lib/components/ConfirmDialog.svelte';

	interface Props { job: JobView; handSetCount: number; onchanged: (type: 'movie' | 'tv') => void }
	let { job, handSetCount, onchanged }: Props = $props();
	let confirmOpen = $state(false);
	let saving = $state(false);
	const current = $derived(job.media_type === 'tv' ? 'tv' : 'movie');

	async function apply(type: 'movie' | 'tv') {
		saving = true;
		try {
			await setJobMediaType(job.id, type);
			onchanged(type);
		} finally {
			saving = false;
			confirmOpen = false;
		}
	}

	function choose(type: 'movie' | 'tv') {
		if (type === current || saving) return;
		if (type === 'movie' && handSetCount > 0) confirmOpen = true;
		else apply(type);
	}
	const plural = $derived(handSetCount === 1 ? '1 track has' : `${handSetCount} tracks have`);
</script>

<div class="media-type-switch" role="radiogroup" aria-label="Media type">
	<span class="media-type-switch-label">Type</span>
	{#each [['movie', 'Movie'], ['tv', 'TV']] as [value, label] (value)}
		<button type="button" role="radio" class="tabs-tab" aria-checked={current === value} data-selected={current === value}
			disabled={saving} onclick={() => choose(value as 'movie' | 'tv')}>{label}</button>
	{/each}
</div>
<ConfirmDialog open={confirmOpen} title="Switch to Movie?" message={`${plural} episodes you set by hand. Switch to Movie anyway?`}
	confirmLabel="Switch to Movie" variant="primary" onconfirm={() => apply('movie')} oncancel={() => (confirmOpen = false)} />

<style>
	.media-type-switch { display: flex; align-items: center; gap: 0.5rem; }
	.media-type-switch-label { font-size: 0.6875rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--color-text-muted); }
</style>
```

Page changes per the Behaviour list; `handSetCount = tracks.filter((t) => ['episode_number', 'role'].some((k) => t.identity_provenance?.[k] === 'manual')).length`. Delete the four v2 files.

- [ ] **Step 4: Run every UI check**

```bash
npx vitest run; echo $?
npm run check; echo $?
npm run lint; echo $?
npx prettier --check .; echo $?
```

Expected: all four exit 0.

- [ ] **Step 5: Commit**

```bash
git add -A src
git commit -m "feat(ui-neu): Match Episodes tab and Movie/TV switch on the job page; drop the v2 matcher"
```

---

### Task 15: Full verification, docs, PR, integration mirror, live check

**Files:**
- Modify: `docs/developers/architecture/02-job-lifecycle.md` ("Episode matching": the ui-neu panel and `tmdb_kind`), `docs/user/` page that documents the job page (add "Match Episodes" and the type switch; find it with `grep -rln "Poster & metadata search" docs/user`).

- [ ] **Step 1: Run every suite with exit codes**

```bash
uv run pytest; echo pytest=$?
uv run pre-commit run --all-files; echo precommit=$?
cd services/ui-neu/frontend && npx vitest run; echo vitest=$?; npm run check; echo check=$?; npm run lint; echo lint=$?
cd /home/upb/src/arm-wt-tvmatch/site && npm test; echo docs=$?
```

Expected: every exit code 0. Backend statement coverage stays at 100% (`uv run --with coverage coverage run -m pytest services/backend && uv run --with coverage coverage report --fail-under=100`).

- [ ] **Step 2: Update the two docs, commit**

```bash
git add docs
git commit -m "docs: Match Episodes tab, Movie/TV switch, tmdb_kind"
```

- [ ] **Step 3: Push and open the PR stacked on #100**

```bash
env -u GITHUB_TOKEN git push -u origin feat/tv-episode-match-ui
env -u GITHUB_TOKEN gh pr create -R shitwolfymakes/automatic-ripping-machine --base feat/identity-settings --head feat/tv-episode-match-ui \
  --title "feat: TV episode matching in ui-neu (Match Episodes tab, Movie/TV switch, complete show ids)" --body-file <summary file>
```

The PR body summarises the spec, links the design project, lists verification; no Claude attribution.

- [ ] **Step 4: Mirror to `integration/all-prs-3`**

Cherry-pick the branch's commits (`git cherry-pick -x <first>^..<last>`) onto `integration/all-prs-3` in `/home/upb/src/automatic-ripping-machine`. Expected conflicts: `metadata/dispatcher.py` (integration has `prefer_tv` from `065d96d4`): keep both, and call `_with_tmdb_ids` on the result of `_identify_video` there too; `identity/disc_shape.py` exists on integration: make it `from arm_common.disc_shape import looks_episodic  # noqa: F401` re-exporting the arm_common copy, and delete the backend copy's duplicate tests only if `packages/arm_common/tests/test_common_disc_shape.py` covers the same cases. Regenerate API artifacts there, run every suite with exit codes, push.

- [ ] **Step 5: Live check on hifi (after the operator's go-ahead to deploy)**

Deploy integration (`setup-dev.sh up`) only after confirming nothing is ripping, filing or transcoding. Then on the Kolchak job: header switch to TV → **Pick the series first**; TV search → apply "Kolchak: The Night Stalker (1974)"; confirm stored ids (`tmdb=5084`, `tmdb_kind=tv`, IMDb, TVDB) in the DB; watch the automatic match land; preview TVmaze vs TMDb; set t05 to Extra by hand, revert; check file names.
