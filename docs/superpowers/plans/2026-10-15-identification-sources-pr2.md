# Identification Sources PR 2: Read the TV List, Exact-ID Walk, Label Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the last three identification decisions follow the operator's settings: the TV title-search order reads `episode_sources`, a TheDiscDB IMDb match resolves through the ranked sources (or from the release itself when none can), and an ignored volume label is neither searched nor used as the miss title while a better name exists. Closes #287.

**Architecture:** Three small changes behind the registry built in PR 0 and the columns from PR 1. `online_source_ids("tv")` returns `episode_sources_setting(cfg)`; `sources_for` already drops ids the registry does not know, so TVmaze and TVDB are skipped until their adapters land. `MetadataDispatcher.identify_from_imdb` takes the media kind and walks `sources_for(cfg, kind, registry)` with the `lookup_imdb` capability. The identify route passes the TheDiscDB kind, falls back to the release's own title and year when no source offers an IMDb lookup, and uses the hint title or release title before the raw label on a miss. The dispatcher adds the volume-label candidate only when the `label` hint is enabled.

**Tech Stack:** Python 3.14, FastAPI, pytest (fake sources, `respx`, `FakeSession`), ruff 0.15.11 via pre-commit, mypy. No schema or OpenAPI change.

**Spec:** `docs/superpowers/specs/2026-10-14-identification-sources-design.md` (D-1, D-4, D-6, §5.3 consumer table, §6 PR 2, §8 criteria 2–4, §10). Branch: `feat/identification-sources-pr2` from `feat/identification-sources-pr1` (PR #360).

## Global Constraints

- No schema, migration, metadata or OpenAPI change. No UI change.
- TV title-search order = `episode_sources_setting(cfg)` (default `tmdb, tvmaze, tvdb`), filtered by `sources_for` to registered, TV-capable, configured sources. Movie and music orders are unchanged from PR 1. The job page's TV search select (`search_provider_tv`, values `tmdb, omdb`) is unchanged: manual search may still pick OMDb; the automatic order follows the operator's TV list, which has no OMDb row (spec §10 resolution written in Task 4).
- `identify_from_imdb(imdb_id, cfg, *, kind: Kind = "movie")` walks `sources_for(cfg, kind, registry)` in rank order (not the search-box preference), using each source's `lookup_imdb`; the first hit wins and is stamped with that source's id; `_with_tmdb_ids` still runs on the result. Empty id or no capable source → `None`.
- New dispatcher helper `has_imdb_lookup(cfg, kind) -> bool`: True when at least one source in `sources_for(cfg, kind, registry)` offers `lookup_imdb`.
- TheDiscDB kind mapping: `DiscMatch.kind` starting with `movie` → `"movie"`, anything else → `"tv"`. Release identity: `metadata["Title"]` and `metadata["Year"]` when present, else derived from `title_slug` (`round-midnight-1986` → `Round Midnight`, `1986`).
- Identify route: when a TheDiscDB match carries an IMDb id and `has_imdb_lookup` is False, the job is identified from the release metadata with no online call: a `MetadataResult(title, year, kind, payload={"imdb_id": …, "thediscdb_release": release_slug}, provider="thediscdb")`. When sources exist but all miss, the fuzzy `identify` runs as today.
- Miss title order: hint title (from the enabled hint sources) → TheDiscDB release title → raw volume label.
- Volume label as a search candidate only when `"label"` is in `hint_sources_setting(cfg)`; the label-derived year is still used to narrow the hint candidate (spec D-4 gates the candidate, not the year) and the hint-year retry is unchanged.
- `MetadataResult.provider == "thediscdb"` for the no-online-call path; `metadata_with_identity` files it under `provider_raw["thediscdb"]` like any other provider.
- Error strings, log lines, timeouts unchanged. Tests zero-infra. Commits carry no attribution trailers.

## Review Focus

1. A TheDiscDB match whose IMDb id TMDb does not know (TMDb returns an empty `/find`) must fall through to the fuzzy identify, not to the release-metadata path (Task 3 router test: exact misses, `identify` is called).
2. `episode_sources = ["tvmaze"]` with no TVmaze adapter must produce an empty TV walk and no HTTP call, and a movie-shaped disc still walks the movie list (Task 1 dispatcher test).
3. A disc with every hint off (`disc_hint_sources = []`), no TheDiscDB match and a total miss must still get the raw label as its title (Task 3 router test).
4. A TheDiscDB match with `kind = "series"` must ask the TV sources, so an OMDb-only install resolves a series IMDb id through OMDb `type=series`-capable lookup (Task 2 dispatcher test passes `kind="tv"` through to the adapter; Task 3 router test asserts `kind="tv"` received).
5. The release-metadata result must not be enriched by `_with_tmdb_ids` into a TMDb call (provider is `thediscdb`, so the guard skips it; Task 3 asserts no dispatcher `identify_from_imdb` or `identify` call and the stored provider).

---

### Task 1: TV order from the episode list

**Files:**
- Modify: `services/backend/arm_backend/identity/sources/registry.py` (`online_source_ids`)
- Modify: `services/backend/tests/test_identity_registry_online.py`, `services/backend/tests/test_dispatcher.py`

**Interfaces:**
- Produces: `online_source_ids(cfg, "tv") == episode_sources_setting(cfg)`.

- [ ] **Step 1: Write the failing tests**

In `test_identity_registry_online.py`, replace the TV assertion inside `test_online_source_ids_reads_the_movie_and_music_lists` (the line asserting `"tv"` still returns the default) with:

```python
    assert online_source_ids(_cfg(episode_sources=["tvmaze", "tmdb"]), "tv") == ("tvmaze", "tmdb")
    assert online_source_ids(_cfg(episode_sources=[]), "tv") == ()
    assert online_source_ids(None, "tv") == ("tmdb", "tvmaze", "tvdb")
```

and update `test_default_order_matches_today` so `DEFAULT_ONLINE_SOURCES["tv"]` is no longer asserted (delete the `"tv"` key from the expected dict and from `DEFAULT_ONLINE_SOURCES` in Step 3) while `online_source_ids(None, "tv")` is asserted as above. Add:

```python
def test_sources_for_tv_skips_ids_without_an_adapter():
    reg = _registry(FakeSource("tmdb", {"movie", "tv"}, search_title=_noop), FakeSource("omdb", {"movie", "tv"}, search_title=_noop))
    assert [s.id for s in sources_for(_cfg(episode_sources=["tvmaze", "tvdb", "tmdb"]), "tv", reg)] == ["tmdb"]
    assert sources_for(_cfg(episode_sources=["tvmaze"]), "tv", reg) == ()
```

In `test_dispatcher.py` add, next to `test_movie_order_follows_movie_sources`:

```python
async def test_tv_order_follows_episode_sources():
    """The TV title walk reads the operator's episode list; ids with no adapter
    yet (tvmaze, tvdb) are skipped and OMDb is not in the list (spec §10)."""
    from arm_backend.metadata.base import MetadataResult

    calls: list[str] = []

    def _source(sid: str):
        class S:
            id = sid
            media_types = frozenset({"movie", "tv"})
            requires_key = None

            def configured(self, cfg):
                return None

            async def search_title(self, cfg, kind, title, year):
                calls.append(f"{sid}:{kind}")
                return None

        return S()

    reg = {"tmdb": _source("tmdb"), "omdb": _source("omdb")}
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="SHOW_DISC_1")
        cfg = _config(movie_sources=[], episode_sources=["tvmaze", "tmdb", "tvdb"])
        assert await dispatcher.identify(scan, cfg, prefer_tv=True) is None
    assert calls == ["tmdb:tv"]
    calls.clear()
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        cfg = _config(movie_sources=["omdb"], episode_sources=["tvmaze"])
        assert await dispatcher.identify(scan, cfg) is None
    assert calls == ["omdb:movie"]
    del MetadataResult
```

(Drop the unused `MetadataResult` import and the `del` if ruff complains; they are not needed.)

- [ ] **Step 2: Run them to verify they fail**

Run: `DATABASE_URL=postgresql://x:x@localhost/x ARM_SERVICE_TOKEN=tok-service uv run pytest services/backend/tests/test_identity_registry_online.py services/backend/tests/test_dispatcher.py -q -p no:cacheprovider -k "tv or default_order"`
Expected: FAIL on the TV assertions (`("tmdb", "omdb")` is returned).

- [ ] **Step 3: Implement**

In `registry.py`: remove the `"tv"` entry from `DEFAULT_ONLINE_SOURCES` and make `online_source_ids`:

```python
def online_source_ids(cfg: Config | None, media_type: str) -> tuple[str, ...]:
    """Source ids for `media_type` in the order they are tried: the operator's
    ranked list per type. The TV list is the episode list (spec D-7); ids whose
    adapter does not exist yet are dropped by `sources_for`."""
    if media_type == "movie":
        return movie_sources_setting(cfg)
    if media_type == "tv":
        return episode_sources_setting(cfg)
    if media_type == "music":
        return music_sources_setting(cfg)
    return ()
```

Update the module comment above `DEFAULT_ONLINE_SOURCES` to say it now holds the movie and music defaults only (or delete the dict if nothing else reads it: grep first; `test_default_order_matches_today` reads it, so keep it with the two keys).

- [ ] **Step 4: Run the suites, lint, commit**

Run: `uv run pytest services/backend/tests -q -p no:cacheprovider && uv run pre-commit run ruff --all-files && uv run pre-commit run ruff-format --all-files && uv run mypy services/backend/arm_backend/identity/sources/registry.py`
Expected: all passed; clean.

```bash
git add services/backend/arm_backend/identity/sources/registry.py services/backend/tests/test_identity_registry_online.py services/backend/tests/test_dispatcher.py
git commit -m "feat(identity): TV title-search order follows episode_sources"
```

---

### Task 2: Exact-ID walk and the label gate in the dispatcher

**Files:**
- Modify: `services/backend/arm_backend/metadata/dispatcher.py` (`identify_from_imdb`, new `has_imdb_lookup`, the candidate block of `_identify_video`)
- Modify: `services/backend/tests/test_dispatcher.py`

**Interfaces:**
- Produces: `MetadataDispatcher.identify_from_imdb(imdb_id: str, cfg: Config, *, kind: Kind = "movie") -> MetadataResult | None`; `MetadataDispatcher.has_imdb_lookup(cfg: Config, kind: Kind) -> bool`.
- Consumes: `hint_sources_setting` from the registry (already imported module: add the name to the existing `from arm_backend.identity.sources.registry import …` line).

- [ ] **Step 1: Write the failing tests**

Replace `test_identify_from_imdb_uses_tmdb_find` with:

```python
async def test_identify_from_imdb_walks_the_ranked_sources():
    """D-1: the exact-id lookup asks the enabled sources for the kind in rank
    order; an unconfigured source is skipped and the hit carries its source id."""
    from arm_backend.metadata.base import MetadataResult

    calls: list[str] = []

    def _source(sid: str, reason: str | None, hit: MetadataResult | None):
        class S:
            id = sid
            media_types = frozenset({"movie", "tv"})
            requires_key = None

            def configured(self, cfg):
                return reason

            async def lookup_imdb(self, cfg, imdb_id):
                calls.append(f"{sid}:{imdb_id}")
                return hit

        return S()

    reg = {
        "tmdb": _source("tmdb", "no tmdb key", MetadataResult(title="T", year=None, kind="movie")),
        "omdb": _source("omdb", None, MetadataResult(title="Round Midnight", year=1986, kind="movie")),
    }
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        hit = await dispatcher.identify_from_imdb("tt0090557", _config(movie_sources=["tmdb", "omdb"]))
        assert hit is not None and hit.title == "Round Midnight" and hit.provider == "omdb"
        assert hit.payload["imdb_id"] == "tt0090557"
        assert calls == ["omdb:tt0090557"]
        assert await dispatcher.identify_from_imdb("", _config()) is None
        assert await dispatcher.identify_from_imdb("tt1", _config(movie_sources=[])) is None
        assert dispatcher.has_imdb_lookup(_config(movie_sources=["tmdb", "omdb"]), "movie") is True
        assert dispatcher.has_imdb_lookup(_config(movie_sources=["tmdb"]), "movie") is False  # tmdb unkeyed
        assert dispatcher.has_imdb_lookup(_config(movie_sources=[]), "movie") is False


async def test_identify_from_imdb_uses_the_kind_list():
    from arm_backend.metadata.base import MetadataResult

    kinds: list[str] = []

    class Omdb:
        id = "omdb"
        media_types = frozenset({"movie", "tv"})
        requires_key = None

        def configured(self, cfg):
            return None

        async def lookup_imdb(self, cfg, imdb_id):
            kinds.append("called")
            return MetadataResult(title="Lost", year=2004, kind="tv")

    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources={"omdb": Omdb()})
        cfg = _config(movie_sources=[], episode_sources=["tmdb", "tvmaze"])
        # OMDb is not in the TV list: no TV source offers the lookup.
        assert await dispatcher.identify_from_imdb("tt0411008", cfg, kind="tv") is None
        assert dispatcher.has_imdb_lookup(cfg, "tv") is False
        assert kinds == []
        cfg = _config(movie_sources=["omdb"], episode_sources=[])
        hit = await dispatcher.identify_from_imdb("tt0411008", cfg, kind="movie")
        assert hit is not None and hit.kind == "tv" and kinds == ["called"]
```

Keep `test_identify_from_imdb_keeps_the_known_imdb_and_adds_tvdb` (respx, real adapters; it uses `_config()` with both keys and the default movie list, so TMDb answers first as before) and add the label-gate tests:

```python
async def test_label_candidate_skipped_when_the_label_hint_is_ignored():
    """D-4: with `label` removed from disc_hint_sources the volume label is not
    searched; only the hint title (and its year-free retry) is."""
    searched: list[str] = []

    class Tmdb:
        id = "tmdb"
        media_types = frozenset({"movie", "tv"})
        requires_key = None

        def configured(self, cfg):
            return None

        async def search_title(self, cfg, kind, title, year):
            searched.append(f"{kind}:{title}:{year}")
            return None

    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources={"tmdb": Tmdb()})
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="HEAT_1995")
        cfg = _config(disc_hint_sources=["bd_title"], movie_sources=["tmdb"], episode_sources=["tmdb"])
        assert await dispatcher.identify(scan, cfg) is None
        assert searched == []
        assert await dispatcher.identify(scan, cfg, title_hint="Heat") is None
    # The label's year still narrows the hint search (D-4 gates the candidate, not the year).
    assert searched == ["movie:Heat:1995", "tv:Heat:1995"]


async def test_label_candidate_searched_when_the_label_hint_is_enabled():
    searched: list[str] = []

    class Tmdb:
        id = "tmdb"
        media_types = frozenset({"movie", "tv"})
        requires_key = None

        def configured(self, cfg):
            return None

        async def search_title(self, cfg, kind, title, year):
            searched.append(f"{kind}:{title}")
            return None

    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources={"tmdb": Tmdb()})
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="HEAT_1995")
        cfg = _config(disc_hint_sources=["bd_title", "label"], movie_sources=["tmdb"], episode_sources=["tmdb"])
        assert await dispatcher.identify(scan, cfg) is None
    assert searched == ["movie:HEAT", "tv:HEAT"]
```

(`_config` in this file builds a `Config(**base)`; passing `disc_hint_sources`, `movie_sources`, `episode_sources` works because they are plain model fields.)

- [ ] **Step 2: Run them to verify they fail**

Run: `DATABASE_URL=postgresql://x:x@localhost/x ARM_SERVICE_TOKEN=tok-service uv run pytest services/backend/tests/test_dispatcher.py -q -p no:cacheprovider -k "imdb or label_candidate"`
Expected: FAIL — `identify_from_imdb` still goes to the `tmdb` source only and has no `kind` kwarg; `has_imdb_lookup` missing; the label is searched.

- [ ] **Step 3: Implement**

In `dispatcher.py`:

1. Extend the registry import to `from arm_backend.identity.sources.registry import fingerprint_sources, hint_sources_setting, sources_for`.
2. Replace `identify_from_imdb` with:

```python
    def has_imdb_lookup(self, cfg: Config, kind: Kind) -> bool:
        """True when an enabled source for `kind` can resolve an IMDb id (D-1)."""
        return any(capability(s, "lookup_imdb") is not None for s in sources_for(cfg, kind, self._sources))

    async def identify_from_imdb(self, imdb_id: str, cfg: Config, *, kind: Kind = "movie") -> MetadataResult | None:
        """Exact-ID identify for a TheDiscDB-matched disc (spec D-1): the
        enabled sources for `kind`, in rank order, first hit wins. None when
        the id is empty, no source offers the lookup, or every source misses
        (the caller falls back to the fuzzy identify in that last case)."""
        if not imdb_id:
            return None
        for source in sources_for(cfg, kind, self._sources):
            lookup = capability(source, "lookup_imdb")
            if lookup is None:
                continue
            hit = await self._call(source.id, lookup(cfg, imdb_id))
            if hit is not None:
                hit.payload.setdefault("imdb_id", imdb_id)
                return await self._with_tmdb_ids(hit, cfg)
        return None
```

3. In `_identify_video`, change the label block so the candidate is gated. The label title and year are still computed (the year narrows the hint candidate):

```python
        label_title: str | None = None
        label_year: int | None = None
        if scan.volume_label:
            label_title, label_year = _normalize_volume_label(scan.volume_label)
        # D-4: the volume label is a search candidate only while the `label`
        # disc hint is enabled; an operator who ignores disc text gets no
        # label search at all. Its year still narrows the hint candidate.
        label_enabled = "label" in hint_sources_setting(cfg)
```

and the existing `if label_title:` append becomes `if label_title and label_enabled:`. Keep the hint candidates and the hint-year retry exactly as they are.

- [ ] **Step 4: Run the suites, lint, commit**

Run: `uv run pytest services/backend/tests -q -p no:cacheprovider && uv run pre-commit run ruff --all-files && uv run pre-commit run ruff-format --all-files && uv run mypy services/backend/arm_backend/metadata/dispatcher.py`
Expected: all passed; clean. `test_ripper_router.py` still passes because its fakes accept positional `(imdb_id, cfg)`; Task 3 changes the route to pass `kind=` and updates them.

```bash
git add services/backend/arm_backend/metadata/dispatcher.py services/backend/tests/test_dispatcher.py
git commit -m "feat(metadata): exact IMDb identify walks the ranked sources; label candidate follows the label hint"
```

---

### Task 3: Identify route: kind, release fallback, miss title

**Files:**
- Modify: `services/backend/arm_backend/identity/sources/thediscdb.py` (two helpers)
- Modify: `services/backend/arm_backend/routers/ripper.py` (`_identify` closure and the miss branch)
- Modify: `services/backend/tests/test_ripper_router.py` (fakes gain `**kw`; four new tests)
- Modify: the thediscdb source test module (find it with `ls services/backend/tests | grep -i thediscdb`; add the helper tests there)

**Interfaces:**
- Produces in `thediscdb.py`: `release_kind(match: DiscMatch) -> Literal["movie", "tv"]`; `release_identity(match: DiscMatch) -> tuple[str | None, int | None]`.
- Consumes: `dispatcher.identify_from_imdb(imdb, cfg, kind=…)`, `dispatcher.has_imdb_lookup(cfg, kind)` (Task 2).

- [ ] **Step 1: Write the failing tests**

Helper tests (in the thediscdb source test module):

```python
def test_release_kind_maps_thediscdb_directories() -> None:
    from arm_backend.identity.sources.thediscdb import release_kind

    assert release_kind(_match(kind="movies")) == "movie"
    assert release_kind(_match(kind="movie")) == "movie"
    assert release_kind(_match(kind="series")) == "tv"
    assert release_kind(_match(kind="tv")) == "tv"


def test_release_identity_prefers_metadata_then_slug() -> None:
    from arm_backend.identity.sources.thediscdb import release_identity

    assert release_identity(_match(metadata={"Title": "Round Midnight", "Year": 1986})) == ("Round Midnight", 1986)
    assert release_identity(_match(metadata={"Title": "Round Midnight", "Year": "1986"})) == ("Round Midnight", 1986)
    assert release_identity(_match(metadata={}, title_slug="round-midnight-1986")) == ("Round Midnight", 1986)
    assert release_identity(_match(metadata={}, title_slug="lost")) == ("Lost", None)
    assert release_identity(_match(metadata={}, title_slug="")) == (None, None)
```

The module is `services/backend/tests/test_identity_thediscdb.py`; its existing `_match(titles, kind=)` builder has a different shape, so add a separate builder there and use it in these two tests (rename the calls above from `_match(` to `_release_match(`):

```python
def _release_match(**overrides: Any) -> DiscMatch:
    base: dict[str, Any] = dict(
        kind="movie", title_slug="round-midnight-1986", release_slug="r", disc={}, metadata={}, release={}
    )
    base.update(overrides)
    return DiscMatch(**base)
```

Router tests, in `test_ripper_router.py`. First make every fake `identify_from_imdb` accept the kwarg: change their signatures to `async def identify_from_imdb(self, imdb_id: str, _cfg: Any, **kw: Any)` and, in `_ImdbExactDispatcher`, record `self.kinds.append(kw.get("kind"))` (add `self.kinds: list[Any] = []` in `__init__`); add `def has_imdb_lookup(self, _cfg: Any, _kind: Any) -> bool: return True` to `_ImdbExactDispatcher` and to the total-miss fake, and `return False` is never needed there. Then:

```python
def test_identify_thediscdb_exact_walk_receives_the_release_kind() -> None:
    """D-1: the route passes the TheDiscDB kind so a series id asks the TV sources."""
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(block_on_miss=True, thediscdb_enabled=True)]
    dispatcher = _ImdbExactDispatcher(MetadataResult(title="Lost", year=2004, kind="tv", provider="omdb"))
    app = _make_app(db, dispatcher=dispatcher)
    app.state.thediscdb = _FakeStore(_thediscdb_match_series())
    with TestClient(app) as client:
        r = client.post("/api/ripper/identify", json={"drive_id": "drv_x", "scan_result": _scan_dict_with_hash()}, headers=_SERVICE_AUTH)
    assert r.status_code == 200, r.text
    assert dispatcher.identify_from_imdb_calls == ["tt0411008"]
    assert dispatcher.kinds == ["tv"]
    assert r.json()["media_type"] == "tv"


def test_identify_thediscdb_without_an_imdb_capable_source_uses_the_release() -> None:
    """D-1: no enabled source offers an IMDb lookup → no online call; the job is
    identified from the release's own title/year/kind with provider thediscdb."""
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(block_on_miss=True, thediscdb_enabled=True)]

    class _NoLookup:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def has_imdb_lookup(self, _cfg: Any, _kind: Any) -> bool:
            return False

        async def identify_from_imdb(self, *a: Any, **kw: Any) -> MetadataResult | None:
            self.calls.append("identify_from_imdb")
            return None

        async def identify(self, *a: Any, **kw: Any) -> MetadataResult | None:
            self.calls.append("identify")
            return None

    dispatcher = _NoLookup()
    app = _make_app(db, dispatcher=dispatcher)
    app.state.thediscdb = _FakeStore(_thediscdb_match())
    with TestClient(app) as client:
        r = client.post("/api/ripper/identify", json={"drive_id": "drv_x", "scan_result": _scan_dict_with_hash()}, headers=_SERVICE_AUTH)
    out = r.json()
    assert r.status_code == 200, r.text
    assert dispatcher.calls == []
    assert out["status"] == "identified"
    assert (out["title"], out["year"], out["media_type"]) == ("Round Midnight", 1986, "movie")
    assert out["metadata_json"]["identity"]["provider"] == "thediscdb"
    assert out["metadata_json"]["identity"]["external_ids"]["imdb"] == "tt0090557"
    assert "thediscdb" in out["metadata_json"]["provider_raw"]


def test_identify_thediscdb_exact_miss_falls_through_to_fuzzy_identify() -> None:
    """A source exists but does not know the id (review focus 1): fuzzy identify runs."""
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(block_on_miss=True, thediscdb_enabled=True)]

    class _ExactMiss(_Dispatcher):
        def has_imdb_lookup(self, _cfg: Any, _kind: Any) -> bool:
            return True

        async def identify_from_imdb(self, *a: Any, **kw: Any) -> MetadataResult | None:
            return None

    dispatcher = _ExactMiss(MetadataResult(title="Iron Man", year=2008, kind="movie", provider="tmdb"))
    app = _make_app(db, dispatcher=dispatcher)
    app.state.thediscdb = _FakeStore(_thediscdb_match())
    with TestClient(app) as client:
        r = client.post("/api/ripper/identify", json={"drive_id": "drv_x", "scan_result": _scan_dict_with_hash()}, headers=_SERVICE_AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Iron Man"
    assert dispatcher.received_kwargs  # identify() was called


def test_identify_miss_title_prefers_hint_then_release_then_label() -> None:
    """D-4 miss title: hint title → TheDiscDB release title → raw label."""
    # 1. Release title beats the raw label when every lookup misses.
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(block_on_miss=True, thediscdb_enabled=True, disc_hint_sources=[])]

    class _AllMiss:
        def has_imdb_lookup(self, _cfg: Any, _kind: Any) -> bool:
            return True

        async def identify_from_imdb(self, *a: Any, **kw: Any) -> MetadataResult | None:
            return None

        async def identify(self, *a: Any, **kw: Any) -> MetadataResult | None:
            return None

    app = _make_app(db, dispatcher=_AllMiss())
    app.state.thediscdb = _FakeStore(_thediscdb_match())
    with TestClient(app) as client:
        r = client.post("/api/ripper/identify", json={"drive_id": "drv_x", "scan_result": _scan_dict_with_hash()}, headers=_SERVICE_AUTH)
    assert r.status_code == 200 and r.json()["status"] == "awaiting_user_id"
    assert r.json()["title"] == "Round Midnight"
    # 2. With every hint off and no match, the raw label is the last resort (review focus 3).
    db2 = FakeSession()
    db2.rows["drives"] = [_drive()]
    db2.rows["config"] = [_config(block_on_miss=True, disc_hint_sources=[])]
    app2 = _make_app(db2, dispatcher=_Dispatcher(None))
    with TestClient(app2) as client:
        r2 = client.post("/api/ripper/identify", json={"drive_id": "drv_x", "scan_result": _scan_dict()}, headers=_SERVICE_AUTH)
    assert r2.json()["title"] == "MY_DISC"
```

Builders to add next to `_thediscdb_match()` (around line 1000): `_thediscdb_match_series()` returning `DiscMatch(kind="series", title_slug="lost-2004", release_slug="s1", disc={"Titles": []}, metadata={"Title": "Lost", "Year": 2004, "ExternalIds": {"Imdb": "tt0411008"}}, release={})`, and

```python
def _scan_dict_with_hash() -> dict[str, Any]:
    scan = _scan_dict()
    scan["fingerprints"] = [{"algo": "thediscdb", "value": "2D61282D8DA5EAC2CA87B451BCE9A055"}]
    return scan
```

(the same fingerprint the existing TheDiscDB tests set inline at lines 1045, 1079 and 1119). The `_config(...)` helper at line 120 has a fixed keyword list; add `disc_hint_sources: list[str] | None = None` to it and pass `**({"disc_hint_sources": disc_hint_sources} if disc_hint_sources is not None else {})` into the `Config(...)` call so existing callers are untouched. The release-title case and the dispatcher's label-gate tests cover D-4; no separate hint-title router case is needed.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest services/backend/tests/test_ripper_router.py services/backend/tests/<thediscdb test module> -q -p no:cacheprovider -k "thediscdb or miss_title or release_"`
Expected: FAIL — helpers missing; `kinds == []`; the no-lookup test sees `identify` called; the miss title is `MY_DISC`.

- [ ] **Step 3: Implement**

`identity/sources/thediscdb.py`, append:

```python
def release_kind(match: DiscMatch) -> Literal["movie", "tv"]:
    """TheDiscDB's top-level directory names the kind (`movies` / `series`)."""
    return "movie" if str(match.kind or "").lower().startswith("movie") else "tv"


_SLUG_YEAR_RE = re.compile(r"-(19\d{2}|20\d{2})$")


def release_identity(match: DiscMatch) -> tuple[str | None, int | None]:
    """The release's own title and year: the title metadata when present,
    else derived from the title slug (`round-midnight-1986`)."""
    title = match.metadata.get("Title")
    year = _int_or_none(match.metadata.get("Year"))
    if isinstance(title, str) and title.strip():
        return title.strip(), year
    slug = str(match.title_slug or "").strip()
    if not slug:
        return None, None
    m = _SLUG_YEAR_RE.search(slug)
    if m and year is None:
        year = int(m.group(1))
    if m:
        slug = slug[: m.start()]
    words = [w for w in slug.split("-") if w]
    return (" ".join(w.capitalize() for w in words) or None), year
```

(add `import re` and `Literal` to the imports; `_int_or_none` exists in the module.)

`routers/ripper.py`: import `release_identity, release_kind` from `arm_backend.identity.sources.thediscdb` alongside `external_imdb_id`, and `hint_title` is already imported. Replace the `_identify` closure body:

```python
            async def _identify() -> MetadataResult | None:
                if thediscdb_match is not None:
                    imdb = external_imdb_id(thediscdb_match)
                    if imdb:
                        kind = release_kind(thediscdb_match)
                        if not dispatcher.has_imdb_lookup(cfg, kind):
                            # D-1: no enabled source can resolve the id, so no
                            # online call; the release names the disc.
                            title, year = release_identity(thediscdb_match)
                            if title:
                                return MetadataResult(
                                    title=title,
                                    year=year,
                                    kind=kind,
                                    payload={"imdb_id": imdb, "thediscdb_release": thediscdb_match.release_slug},
                                    provider="thediscdb",
                                )
                        else:
                            exact = await dispatcher.identify_from_imdb(imdb, cfg, kind=kind)
                            if exact is not None:
                                return exact
                return await dispatcher.identify(
                    scan,
                    cfg,
                    title_hint=hint_title(job, hints),
                    title_hint_is_tv=hint_is_tv(job, hints),
                    prefer_tv=looks_episodic(scan.titles),
                )
```

Miss branch: compute once before the `if cfg.block_on_miss:` line:

```python
            release_title = release_identity(thediscdb_match)[0] if thediscdb_match is not None else None
            miss_title = hint_title(job, hints) or release_title or scan.volume_label
```

and replace both `job.title = scan.volume_label` assignments with `job.title = miss_title`.

The test fakes that lack `has_imdb_lookup` (plain `_Dispatcher`) never reach that branch because they run without a TheDiscDB match; the fakes used with a match gain the method in Step 1.

- [ ] **Step 4: Run the suites, lint, commit**

Run: `uv run pytest services/backend/tests -q -p no:cacheprovider && uv run pre-commit run ruff --all-files && uv run pre-commit run ruff-format --all-files && uv run mypy services/backend/arm_backend/routers/ripper.py services/backend/arm_backend/identity/sources/thediscdb.py`
Expected: all passed; clean.

```bash
git add services/backend/arm_backend/identity/sources/thediscdb.py services/backend/arm_backend/routers/ripper.py services/backend/tests
git commit -m "feat(identify): TheDiscDB exact match walks the ranked sources or names the disc itself; miss title prefers hint and release"
```

---

### Task 4: Spec and docs

**Files:**
- Modify: `docs/superpowers/specs/2026-10-14-identification-sources-design.md` (§5.3 rows for `dispatcher.identify_from_imdb` and the label candidate; §6 PR 2 bullet; §10)
- Modify: `docs/developers/architecture/02-job-lifecycle.md` (the "Online sources" paragraph)

- [ ] **Step 1: Spec**

- §5.3, `dispatcher.identify_from_imdb` row "After": "walks `sources_for(cfg, kind, registry)` with `lookup_imdb`; `kind` from the TheDiscDB release; no capable source → the route identifies from the release metadata with provider `thediscdb` (D-1)". Label row "After": "only when `label` is in `disc_hint_sources`; the label year still narrows the hint; miss title = hint title → release title → raw label (D-4)".
- §6 PR 2 bullet: "`online_source_ids` reads the TV list; exact-id walk (D-1); label gate (D-4). CRC64 gate, CD walk and the re-resolve hook landed in PR 1. Closes #287."
- §10: replace the "PR 0 keeps OMDb in the TV title-search order…" bullet with: "Resolved in PR 2: the automatic TV title order is `episode_sources` (no OMDb row); OMDb series search remains available from the job page's TV search select. TVmaze/TVDB title search lands in PR 2b; until then a TV list naming only them yields no automatic TV title search." Strike the "PR 2b must land before PR 2" sentence from the PR 1 resolution bullet (the stack merges together).

- [ ] **Step 2: Architecture doc**

In the "Online sources" paragraph, change "The order is a built-in default until the Identification settings … make it operator-configurable." to "The order comes from the Identification settings: `movie_sources`, `episode_sources` (TV) and `music_sources`; a TheDiscDB IMDb match resolves through the same ranked sources, and the volume label is searched only while the `label` disc hint is enabled."

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-10-14-identification-sources-design.md docs/developers/architecture/02-job-lifecycle.md docs/superpowers/plans/2026-10-15-identification-sources-pr2.md
git commit -m "docs: identification spec and lifecycle follow PR 2"
```

---

## Self-review notes

- **Spec coverage.** D-1: Tasks 2 and 3. D-4: Tasks 2 and 3. D-6 unchanged. §6 PR 2 items already landed in PR 1 are named as such. §8 criteria: 2 (empty movie list → AWAITING_USER_ID) is covered by Task 2's walk returning None plus the existing miss tests; 3 by Task 2 (`walks_the_ranked_sources`) and Task 3 (release fallback); 4 by Task 2's label gate and Task 3's miss-title test.
- **Deviation recorded.** The label-derived year still narrows the hint candidate when the label is ignored (spec D-4 gates the candidate). If the owner wants the year ignored too, it is one condition in Task 2.
- **Type consistency.** `kind: Kind` (`Literal["movie","tv"]`) flows from `release_kind` through `identify_from_imdb` and `has_imdb_lookup`; `MediaType(result.kind)` in the route accepts "movie"/"tv".
- **Review Focus** 1–5 each have a named test.
