# Identification Sources PR 0: Registry and Dispatcher Walk — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every hard-coded "which provider do I call" decision in the Backend's title lookup with one online-source registry, keeping today's observable behaviour so the later PRs of #258 only have to read the new Config columns.

**Architecture:** A new module `arm_backend/metadata/sources.py` defines the `OnlineSource` protocol and one adapter per existing HTTP client (TMDb, OMDb, MusicBrainz, ARM community server). `identity/sources/registry.py` gains the accessors that decide order and enablement (`sources_for`, `search_source`, `fingerprint_sources`, `known_source_ids`), reading a built-in default order in this PR. `MetadataDispatcher` and `routers/metadata.py` become walks over those accessors; `_PROVIDER_BY_LABEL_PREFIX` and the per-route client branching go away.

**Tech Stack:** Python 3.14, FastAPI, httpx, pytest with `respx` and `monkeypatch`; `uv run pytest` from the repo root; ruff line length 120; mypy.

**Spec:** `docs/superpowers/specs/2026-10-14-identification-sources-design.md` (§5.1–5.3, §6 PR 0, §7).

## Global Constraints

- No behaviour change except the one §6 names below: the dispatcher's title search becomes kind-major (all sources for the first kind, then all for the second). Every other outcome, HTTP call, error message and log line stays as it is.
- Default online order is `("tmdb", "omdb")` for movie and TV, `("musicbrainz",)` for music, `("arm_server",)` for fingerprints. No Config column is read for these lists in this PR.
- Source ids are exactly `tmdb`, `omdb`, `musicbrainz`, `arm_server`. `MetadataResult.provider` is always the source id.
- Capability methods take `cfg` first; adapters construct a client per call from `cfg` so a key saved after boot is used on the next call (today's behaviour).
- `PROVIDER_TIMEOUT_SECONDS` and `DISPATCH_TIMEOUT_SECONDS` stay in `arm_backend/metadata/dispatcher.py` (tests patch them there).
- The `OMDB_API_KEY` environment override is removed in this PR (owner decision during review, spec D-3): no `omdb_api_key_override` anywhere, no `Settings.OMDB_API_KEY`.
- `routers/config.py` is not touched; its `metadata_provider` literal is deleted with the field in PR 1.
- Error strings returned to the UI are unchanged: `no {id} key configured`, `{id} unavailable: {exc}`, `lookup unavailable: {exc}`, `musicbrainz unavailable: {exc}`.
- No OpenAPI change in this PR, so no snapshot regeneration. `SearchProvider` stays a `Literal` and a test pins it to the registry.
- Tests stay zero-infra. Commits do not carry Claude attribution lines (repo memory rule).

## Call-site sweep (2026-10-14)

Every place in `services/` and `packages/` that constructs a metadata client, reads a provider key, or spells a provider id, and which PR owns it:

| Site | What it does | Owner |
|---|---|---|
| `metadata/dispatcher.py` | all four clients, provider walk | PR 0 Task 3 |
| `routers/metadata.py` | TMDb/OMDb/MusicBrainz/ArmServer per route, `SearchProvider` literal | PR 0 Task 4 |
| `main.py:202` | `OMDB_API_KEY` override into the dispatcher | PR 0 (removed after the final review) |
| `routers/config.py:272-330` | `_KEY_ATTR` map and `_check_tmdb/_check_omdb/_check_tvdb` raw HTTP probes behind `POST /api/config/keys/{name}/check` | PR 0 Task 4 pins `_KEY_ATTR` to the registry's `requires_key`; probes stay as they are |
| `routers/config.py:98,153-156` | `metadata_provider` in ConfigView and PATCH validation | PR 1 (field deleted) |
| `arm_common/schemas/auth.py:80,116` | `metadata_provider` on ConfigView / ConfigUpdate | PR 1 |
| `identity/stage_runner.py:93-101,189` | episode providers wired from `tmdb_api_key` / `tvdb_api_key` | PR 2b, per spec §5.3 |
| `identity/ids.py:79,119`, `identity/episode_stage.py:543` | id-field logic keyed on `"tmdb"` | identity layer, not a call site; PR 2b `fill_external_ids` touches it |
| `routers/images.py` | cover-art proxy host allowlist | not a provider decision; unchanged |
| `services/ripper/arm_ripper/rip/abcde_rip.py:55` | `CDDBMETHOD="musicbrainz"`: abcde does its own MusicBrainz CDDB lookup for tagging during a CD rip | outside the Backend; recorded in spec §10 |
| UI: `api/jobs.ts:199`, `api/config.ts`, `stores/config.ts`, `setup/steps/FinishStep.svelte:65`, `utils/settings-sections.ts:46,83-91`, `episodes/EpisodeMatchPanel.svelte:47` | provider literals, `metadata_provider` readers, key-check names | PR 1/2 UI work; no API change in PR 0 |

No other constructor, key read or provider host string exists outside `arm_backend/metadata/`.

## Review Focus

1. A hint title and a volume label that both miss on TMDb but hit on OMDb for different kinds: the first hit in kind-major order wins (Task 3 pins the order).
2. A source whose key is present but blank or whitespace: `configured()` must report "no key", not call the provider (Task 1 test).
3. A `MetadataResult` built by a client with `provider` already set: `_call` overwrites it with the source id so provenance cannot be spoofed by a payload (Task 3 test).
4. A registry missing a source id the default order names (a future adapter removed or renamed): `sources_for` skips it instead of raising `KeyError` (Task 2 test).
5. The metadata search route asked for `provider=omdb` while only TMDb is keyed: 400 `no omdb key configured`, no HTTP call (Task 4 test).

---

### Task 1: `OnlineSource` protocol and the four adapters

**Files:**
- Create: `services/backend/arm_backend/metadata/sources.py`
- Test: `services/backend/tests/test_metadata_sources.py`

**Interfaces:**
- Consumes: `TMDBClient`, `OMDBClient`, `MusicBrainzClient`, `ArmServerClient`, `MetadataResult` (existing).
- Produces:
  - `class OnlineSource(Protocol)` with `id: str`, `media_types: frozenset[str]`, `requires_key: str | None`, `configured(cfg) -> str | None`.
  - Optional capability methods, all `async`, all taking `cfg: Config` first:
    `search_title(cfg, kind, title, year) -> MetadataResult | None`,
    `search_candidates(cfg, kind, title, limit=10) -> list[MetadataResult]`,
    `lookup_imdb(cfg, imdb_id) -> MetadataResult | None`,
    `lookup_disc_id(cfg, disc_id) -> MetadataResult | None`,
    `lookup_fingerprint(cfg, algo, value) -> MetadataResult | None`,
    `search_releases(cfg, query, *, artist, track_count, release_type, format, country, status) -> list[MetadataResult]`.
  - `def capability(source, name) -> Callable | None`.
  - `def build_online_sources(http, *, omdb_api_key_override=None) -> dict[str, OnlineSource]`.
  - `MUSICBRAINZ_USER_AGENT` moves here (dispatcher and router import it from here).

- [ ] **Step 1: Write the failing tests**

```python
"""Online-source adapters: one per HTTP client, keyed per call from Config."""

import httpx
import pytest

from arm_backend.metadata import sources as sources_mod
from arm_backend.metadata.base import MetadataResult
from arm_backend.metadata.sources import build_online_sources, capability
from arm_common import Config


def _config(**overrides) -> Config:
    base = dict(id=1, tmdb_api_key="tmdb-k", omdb_api_key="omdb-k", musicbrainz_user_agent="arm-test/0.0 (t@x)")
    base.update(overrides)
    return Config(**base)


async def test_registry_has_the_four_sources_with_their_media_types():
    async with httpx.AsyncClient() as http:
        reg = build_online_sources(http)
    assert set(reg) == {"tmdb", "omdb", "musicbrainz", "arm_server"}
    assert reg["tmdb"].media_types == frozenset({"movie", "tv"})
    assert reg["omdb"].media_types == frozenset({"movie", "tv"})
    assert reg["musicbrainz"].media_types == frozenset({"music"})
    assert reg["arm_server"].media_types == frozenset()
    for sid, source in reg.items():
        assert source.id == sid


@pytest.mark.parametrize("key", [None, "", "   "])
async def test_keyed_sources_report_missing_key(key):
    async with httpx.AsyncClient() as http:
        reg = build_online_sources(http)
    cfg = _config(tmdb_api_key=key, omdb_api_key=key)
    assert reg["tmdb"].configured(cfg) == "no tmdb key"
    assert reg["omdb"].configured(cfg) == "no omdb key"
    assert reg["tmdb"].requires_key == "tmdb_api_key"
    assert reg["omdb"].requires_key == "omdb_api_key"


async def test_keyless_sources_are_always_configured():
    async with httpx.AsyncClient() as http:
        reg = build_online_sources(http)
    cfg = _config(tmdb_api_key=None, omdb_api_key=None)
    assert reg["musicbrainz"].configured(cfg) is None
    assert reg["arm_server"].configured(cfg) is None
    assert reg["musicbrainz"].requires_key is None


async def test_omdb_env_override_counts_as_configured():
    async with httpx.AsyncClient() as http:
        reg = build_online_sources(http, omdb_api_key_override="env-k")
    assert reg["omdb"].configured(_config(omdb_api_key=None)) is None


def test_capability_returns_none_for_missing_methods():
    class Bare:
        id = "x"
        media_types = frozenset()
        requires_key = None

        def configured(self, cfg):
            return None

    assert capability(Bare(), "search_title") is None
    assert capability(Bare(), "configured") is not None


async def test_tmdb_adapter_delegates_by_kind(monkeypatch):
    calls: list[tuple] = []

    class FakeTMDB:
        def __init__(self, api_key, http):
            calls.append(("init", api_key))

        async def search_movie(self, title, year):
            calls.append(("movie", title, year))
            return MetadataResult(title="M", year=year, kind="movie")

        async def search_tv(self, title):
            calls.append(("tv", title))
            return MetadataResult(title="T", year=None, kind="tv")

        async def search_movie_candidates(self, title, year=None, limit=10):
            calls.append(("movie_cands", title, limit))
            return []

        async def search_tv_candidates(self, title, limit=10):
            calls.append(("tv_cands", title, limit))
            return []

        async def find_by_imdb_id(self, imdb_id):
            calls.append(("find", imdb_id))
            return MetadataResult(title="F", year=None, kind="movie")

    monkeypatch.setattr(sources_mod, "TMDBClient", FakeTMDB)
    async with httpx.AsyncClient() as http:
        tmdb = build_online_sources(http)["tmdb"]
        cfg = _config()
        assert (await tmdb.search_title(cfg, "movie", "alien", 1979)).title == "M"
        assert (await tmdb.search_title(cfg, "tv", "lost", 2004)).title == "T"
        assert await tmdb.search_candidates(cfg, "movie", "alien", limit=3) == []
        assert await tmdb.search_candidates(cfg, "tv", "lost", limit=4) == []
        assert (await tmdb.lookup_imdb(cfg, "tt1")).title == "F"
    assert ("movie", "alien", 1979) in calls
    assert ("tv", "lost") in calls
    assert ("movie_cands", "alien", 3) in calls
    assert ("tv_cands", "lost", 4) in calls
    assert ("find", "tt1") in calls
    assert all(c[1] == "tmdb-k" for c in calls if c[0] == "init")


async def test_omdb_adapter_prefers_env_override_and_passes_kind(monkeypatch):
    calls: list[tuple] = []

    class FakeOMDB:
        def __init__(self, api_key, http):
            calls.append(("init", api_key))

        async def lookup_by_title(self, title, year=None, kind="movie"):
            calls.append(("title", title, year, kind))
            return None

        async def search_candidates(self, title, kind="movie", limit=10):
            calls.append(("cands", title, kind, limit))
            return []

        async def lookup_by_imdb_id(self, imdb_id):
            calls.append(("imdb", imdb_id))
            return MetadataResult(title="I", year=None, kind="movie")

    monkeypatch.setattr(sources_mod, "OMDBClient", FakeOMDB)
    async with httpx.AsyncClient() as http:
        omdb = build_online_sources(http, omdb_api_key_override="env-k")["omdb"]
        cfg = _config(omdb_api_key="saved-k")
        assert await omdb.search_title(cfg, "tv", "lost", 2004) is None
        assert await omdb.search_candidates(cfg, "movie", "alien", limit=5) == []
        assert (await omdb.lookup_imdb(cfg, "tt2")).title == "I"
    assert ("title", "lost", 2004, "tv") in calls
    assert ("cands", "alien", "movie", 5) in calls
    assert ("imdb", "tt2") in calls
    assert all(c[1] == "env-k" for c in calls if c[0] == "init")


async def test_musicbrainz_adapter_delegates(monkeypatch):
    calls: list[tuple] = []

    class FakeMB:
        def __init__(self, user_agent, http):
            calls.append(("init", user_agent))

        async def lookup_disc_id(self, disc_id):
            calls.append(("disc", disc_id))
            return MetadataResult(title="A", year=None, kind="music")

        async def search_releases(self, query, limit=10, **filters):
            calls.append(("search", query, filters))
            return []

    monkeypatch.setattr(sources_mod, "MusicBrainzClient", FakeMB)
    async with httpx.AsyncClient() as http:
        mb = build_online_sources(http)["musicbrainz"]
        assert (await mb.lookup_disc_id(_config(), "d1")).title == "A"
        assert await mb.search_releases(_config(), "abbey road", artist="beatles") == []
    assert ("disc", "d1") in calls
    assert calls[-1][1] == "abbey road" and calls[-1][2]["artist"] == "beatles"
    assert calls[0][1] == sources_mod.MUSICBRAINZ_USER_AGENT


async def test_arm_server_adapter_only_answers_crc64(monkeypatch):
    calls: list[str] = []

    class FakeArm:
        def __init__(self, http):
            pass

        async def lookup_by_crc64(self, crc64):
            calls.append(crc64)
            return MetadataResult(title="C", year=None, kind="movie")

    monkeypatch.setattr(sources_mod, "ArmServerClient", FakeArm)
    async with httpx.AsyncClient() as http:
        arm = build_online_sources(http)["arm_server"]
        assert await arm.lookup_fingerprint(_config(), "sha256", "zzz") is None
        assert (await arm.lookup_fingerprint(_config(), "crc64", "abc")).title == "C"
    assert calls == ["abc"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest services/backend/tests/test_metadata_sources.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'arm_backend.metadata.sources'`

- [ ] **Step 3: Write the module**

```python
"""Online metadata sources (spec §5.1): one adapter per HTTP client.

An adapter knows which client method implements which capability and which
Config key it needs. It constructs the client per call from `cfg`, so a key
saved after boot is used on the next lookup. Order and enablement are not
decided here: `identity.sources.registry.sources_for` does that."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, Protocol

import httpx

from arm_backend.metadata.arm_server import ArmServerClient
from arm_backend.metadata.base import MetadataResult
from arm_backend.metadata.musicbrainz import MusicBrainzClient
from arm_backend.metadata.omdb import OMDBClient
from arm_backend.metadata.tmdb import TMDBClient
from arm_common import Config

Kind = Literal["movie", "tv"]

# MusicBrainz 403s any User-Agent that doesn't follow their etiquette guide's
# `AppName/version ( contact )` shape. Not operator-configurable (Config.
# musicbrainz_user_agent is dormant — see config_metadata.py).
MUSICBRAINZ_USER_AGENT = "ARM/3.0.0 ( https://github.com/automatic-ripping-machine/automatic-ripping-machine )"


class OnlineSource(Protocol):
    id: str
    media_types: frozenset[str]
    requires_key: str | None

    def configured(self, cfg: Config | None) -> str | None:
        """None when usable; otherwise the skip reason (e.g. "no tmdb key")."""
        ...

    # Capabilities are optional methods; `capability()` finds them. Each takes
    # `cfg` first. Names and signatures:
    #   search_title(cfg, kind, title, year) -> MetadataResult | None
    #   search_candidates(cfg, kind, title, limit=10) -> list[MetadataResult]
    #   lookup_imdb(cfg, imdb_id) -> MetadataResult | None
    #   lookup_disc_id(cfg, disc_id) -> MetadataResult | None
    #   lookup_fingerprint(cfg, algo, value) -> MetadataResult | None
    #   search_releases(cfg, query, *, artist, track_count, release_type,
    #                   format, country, status) -> list[MetadataResult]


def capability(source: object, name: str) -> Callable[..., Any] | None:
    """The capability method `name` of `source`, or None when it lacks it."""
    method = getattr(source, name, None)
    return method if callable(method) else None


def _blank(value: str | None) -> bool:
    return not (value or "").strip()


class TmdbSource:
    id = "tmdb"
    media_types = frozenset({"movie", "tv"})
    requires_key = "tmdb_api_key"

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    def configured(self, cfg: Config | None) -> str | None:
        return "no tmdb key" if _blank(getattr(cfg, "tmdb_api_key", None)) else None

    def _client(self, cfg: Config) -> TMDBClient:
        return TMDBClient(cfg.tmdb_api_key or "", self._http)

    async def search_title(self, cfg: Config, kind: Kind, title: str, year: int | None) -> MetadataResult | None:
        client = self._client(cfg)
        return await (client.search_tv(title) if kind == "tv" else client.search_movie(title, year))

    async def search_candidates(self, cfg: Config, kind: Kind, title: str, limit: int = 10) -> list[MetadataResult]:
        client = self._client(cfg)
        if kind == "tv":
            return await client.search_tv_candidates(title, limit=limit)
        return await client.search_movie_candidates(title, limit=limit)

    async def lookup_imdb(self, cfg: Config, imdb_id: str) -> MetadataResult | None:
        return await self._client(cfg).find_by_imdb_id(imdb_id)


class OmdbSource:
    id = "omdb"
    media_types = frozenset({"movie", "tv"})
    requires_key = "omdb_api_key"

    def __init__(self, http: httpx.AsyncClient, *, api_key_override: str | None = None) -> None:
        self._http = http
        # Backend env `OMDB_API_KEY` wins over the saved key (removed in PR 1, spec D-3).
        self._override = api_key_override

    def _key(self, cfg: Config | None) -> str:
        return (self._override or getattr(cfg, "omdb_api_key", None) or "").strip()

    def configured(self, cfg: Config | None) -> str | None:
        return "no omdb key" if not self._key(cfg) else None

    def _client(self, cfg: Config) -> OMDBClient:
        return OMDBClient(self._key(cfg), self._http)

    async def search_title(self, cfg: Config, kind: Kind, title: str, year: int | None) -> MetadataResult | None:
        return await self._client(cfg).lookup_by_title(title, year, kind=kind)

    async def search_candidates(self, cfg: Config, kind: Kind, title: str, limit: int = 10) -> list[MetadataResult]:
        return await self._client(cfg).search_candidates(title, kind=kind, limit=limit)

    async def lookup_imdb(self, cfg: Config, imdb_id: str) -> MetadataResult | None:
        return await self._client(cfg).lookup_by_imdb_id(imdb_id)


class MusicBrainzSource:
    id = "musicbrainz"
    media_types = frozenset({"music"})
    requires_key = None

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    def configured(self, cfg: Config | None) -> str | None:
        return None

    def _client(self) -> MusicBrainzClient:
        return MusicBrainzClient(MUSICBRAINZ_USER_AGENT, self._http)

    async def lookup_disc_id(self, cfg: Config, disc_id: str) -> MetadataResult | None:
        return await self._client().lookup_disc_id(disc_id)

    async def search_releases(
        self,
        cfg: Config,
        query: str,
        *,
        artist: str | None = None,
        track_count: int | None = None,
        release_type: str | None = None,
        format: str | None = None,
        country: str | None = None,
        status: str | None = None,
    ) -> list[MetadataResult]:
        return await self._client().search_releases(
            query,
            artist=artist,
            track_count=track_count,
            release_type=release_type,
            format=format,
            country=country,
            status=status,
        )


class ArmServerSource:
    """The ARM community database: DVD CRC64 → title. A fingerprint source
    only (spec Step 2), never a title-search source."""

    id = "arm_server"
    media_types: frozenset[str] = frozenset()
    requires_key = None

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    def configured(self, cfg: Config | None) -> str | None:
        return None

    async def lookup_fingerprint(self, cfg: Config, algo: str, value: str) -> MetadataResult | None:
        if algo != "crc64" or not value:
            return None
        return await ArmServerClient(self._http).lookup_by_crc64(value)


def build_online_sources(
    http: httpx.AsyncClient, *, omdb_api_key_override: str | None = None
) -> dict[str, OnlineSource]:
    """Every online source, keyed by id, sharing the app's httpx client."""
    sources: list[OnlineSource] = [
        TmdbSource(http),
        OmdbSource(http, api_key_override=omdb_api_key_override),
        MusicBrainzSource(http),
        ArmServerSource(http),
    ]
    return {s.id: s for s in sources}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest services/backend/tests/test_metadata_sources.py -q`
Expected: 10 passed

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check services/backend/arm_backend/metadata/sources.py services/backend/tests/test_metadata_sources.py && uv run mypy services/backend/arm_backend/metadata/sources.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add services/backend/arm_backend/metadata/sources.py services/backend/tests/test_metadata_sources.py
git commit -m "feat(metadata): online-source adapters behind one protocol"
```

---

### Task 2: Registry accessors that decide order and enablement

**Files:**
- Modify: `services/backend/arm_backend/identity/sources/registry.py` (append after `episode_auto_apply`)
- Test: `services/backend/tests/test_identity_registry_online.py`

**Interfaces:**
- Consumes: `OnlineSource` from Task 1 as a type-only import under `TYPE_CHECKING`. The registry must import nothing from `arm_backend.metadata` at runtime: that package's `__init__` imports the dispatcher, which imports this registry, so a runtime import here is a circular import.
- Produces:
  - `DEFAULT_ONLINE_SOURCES: dict[str, tuple[str, ...]]` = `{"movie": ("tmdb","omdb"), "tv": ("tmdb","omdb"), "music": ("musicbrainz",)}`.
  - `DEFAULT_FINGERPRINT_SOURCES: tuple[str, ...]` = `("arm_server",)`.
  - `online_source_ids(cfg, media_type) -> tuple[str, ...]` (the operator's order; defaults in this PR).
  - `sources_for(cfg, media_type, registry) -> tuple[OnlineSource, ...]`.
  - `search_source(cfg, media_type, registry) -> OnlineSource | None`.
  - `fingerprint_sources(cfg, registry) -> tuple[OnlineSource, ...]`.
  - `known_source_ids(media_type, registry) -> tuple[str, ...]`.

- [ ] **Step 1: Write the failing tests**

```python
"""Online-source order and enablement live in one place (spec §5.2)."""

from arm_backend.identity.sources import registry as reg_mod
from arm_backend.identity.sources.registry import (
    DEFAULT_ONLINE_SOURCES,
    fingerprint_sources,
    known_source_ids,
    online_source_ids,
    search_source,
    sources_for,
)
from arm_common import Config


class FakeSource:
    def __init__(self, id: str, media_types: set[str], reason: str | None = None, **caps):
        self.id = id
        self.media_types = frozenset(media_types)
        self.requires_key = None
        self._reason = reason
        for name, fn in caps.items():
            setattr(self, name, fn)

    def configured(self, cfg):
        return self._reason


async def _noop(*a, **k):
    return None


def _registry(*sources: FakeSource) -> dict[str, FakeSource]:
    return {s.id: s for s in sources}


def _cfg(**kw) -> Config:
    return Config(id=1, **kw)


def test_default_order_matches_today():
    assert DEFAULT_ONLINE_SOURCES == {"movie": ("tmdb", "omdb"), "tv": ("tmdb", "omdb"), "music": ("musicbrainz",)}
    assert online_source_ids(_cfg(), "movie") == ("tmdb", "omdb")
    assert online_source_ids(None, "music") == ("musicbrainz",)
    assert online_source_ids(_cfg(), "data") == ()


def test_sources_for_keeps_order_and_drops_unconfigured():
    reg = _registry(
        FakeSource("tmdb", {"movie", "tv"}, reason="no tmdb key", search_title=_noop),
        FakeSource("omdb", {"movie", "tv"}, search_title=_noop),
    )
    assert [s.id for s in sources_for(_cfg(), "movie", reg)] == ["omdb"]
    reg["tmdb"]._reason = None
    assert [s.id for s in sources_for(_cfg(), "movie", reg)] == ["tmdb", "omdb"]


def test_sources_for_skips_ids_missing_from_registry():
    reg = _registry(FakeSource("omdb", {"movie", "tv"}, search_title=_noop))
    assert [s.id for s in sources_for(_cfg(), "movie", reg)] == ["omdb"]


def test_sources_for_requires_media_type_membership(monkeypatch):
    monkeypatch.setitem(reg_mod.DEFAULT_ONLINE_SOURCES, "music", ("musicbrainz", "tmdb"))
    reg = _registry(
        FakeSource("musicbrainz", {"music"}, lookup_disc_id=_noop),
        FakeSource("tmdb", {"movie", "tv"}, search_title=_noop),
    )
    assert [s.id for s in sources_for(_cfg(), "music", reg)] == ["musicbrainz"]


def test_search_source_is_first_configured_of_the_list():
    reg = _registry(
        FakeSource("tmdb", {"movie", "tv"}, reason="no tmdb key"),
        FakeSource("omdb", {"movie", "tv"}),
    )
    assert search_source(_cfg(), "movie", reg).id == "omdb"
    reg["omdb"]._reason = "no omdb key"
    assert search_source(_cfg(), "movie", reg) is None


def test_fingerprint_sources_default_to_arm_server():
    reg = _registry(FakeSource("arm_server", set(), lookup_fingerprint=_noop))
    assert [s.id for s in fingerprint_sources(_cfg(), reg)] == ["arm_server"]
    assert fingerprint_sources(_cfg(), {}) == ()


def test_known_source_ids_reads_media_types_from_the_registry():
    reg = _registry(
        FakeSource("tmdb", {"movie", "tv"}),
        FakeSource("omdb", {"movie", "tv"}),
        FakeSource("musicbrainz", {"music"}),
        FakeSource("arm_server", set()),
    )
    assert known_source_ids("movie", reg) == ("tmdb", "omdb")
    assert known_source_ids("music", reg) == ("musicbrainz",)
    assert known_source_ids("data", reg) == ()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest services/backend/tests/test_identity_registry_online.py -q`
Expected: FAIL with `ImportError: cannot import name 'DEFAULT_ONLINE_SOURCES'`

- [ ] **Step 3: Append the accessors to `registry.py`**

Add to the imports at the top of the file:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arm_backend.metadata.sources import OnlineSource
```

Append at the end of the file:

```python
# ---------------------------------------------------------------------------
# Online sources (spec §5.2). PR 2 makes `online_source_ids` read the operator's
# `movie_sources` / `episode_sources` / `music_sources` columns; until then the
# order is the one the dispatcher hard-coded before PR 0.
# ---------------------------------------------------------------------------

DEFAULT_ONLINE_SOURCES: dict[str, tuple[str, ...]] = {
    "movie": ("tmdb", "omdb"),
    "tv": ("tmdb", "omdb"),
    "music": ("musicbrainz",),
}
# Step 2 fingerprint sources (PR 1 adds the `crc64service_enabled` switch).
DEFAULT_FINGERPRINT_SOURCES: tuple[str, ...] = ("arm_server",)


def online_source_ids(cfg: Config | None, media_type: str) -> tuple[str, ...]:
    """Source ids for `media_type` in the order they are tried."""
    return DEFAULT_ONLINE_SOURCES.get(media_type, ())


def sources_for(cfg: Config | None, media_type: str, registry: Mapping[str, "OnlineSource"]) -> tuple["OnlineSource", ...]:
    """The sources to try for `media_type`, in order: listed, present in the
    registry, serving that media type, and configured. The only function that
    decides online order or enablement."""
    out: list[OnlineSource] = []
    for sid in online_source_ids(cfg, media_type):
        source = registry.get(sid)
        if source is None or media_type not in source.media_types:
            continue
        if source.configured(cfg) is not None:
            continue
        out.append(source)
    return tuple(out)


def search_source(cfg: Config | None, media_type: str, registry: Mapping[str, "OnlineSource"]) -> "OnlineSource | None":
    """The source behind the job page's search box for `media_type` (PR 1 adds
    the `search_provider_*` columns; until then the first usable listed source)."""
    ranked = sources_for(cfg, media_type, registry)
    return ranked[0] if ranked else None


def fingerprint_sources(cfg: Config | None, registry: Mapping[str, "OnlineSource"]) -> tuple["OnlineSource", ...]:
    """Step 2 sources that answer a disc fingerprint, in order."""
    out: list[OnlineSource] = []
    for sid in DEFAULT_FINGERPRINT_SOURCES:
        source = registry.get(sid)
        if source is not None and source.configured(cfg) is None:
            out.append(source)
    return tuple(out)


def known_source_ids(media_type: str, registry: Mapping[str, "OnlineSource"]) -> tuple[str, ...]:
    """Every registered source id that serves `media_type` (validation lists)."""
    return tuple(sid for sid, source in registry.items() if media_type in source.media_types)
```

The protocol's `configured` takes `Config | None` (Task 1), so the accessors accept `Config | None` like their neighbours without type ignores.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest services/backend/tests/test_identity_registry_online.py services/backend/tests/test_identity_sources_base.py -q`
Expected: all passed (the existing identity-sources suite must still pass)

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check services/backend/arm_backend/identity/sources/registry.py && uv run mypy services/backend/arm_backend/identity/sources/registry.py`
Expected: no errors. If mypy flags the `Config | None` argument, change the accessors' `cfg` parameter to `Config` and drop the ignores (every caller in Tasks 3 and 4 passes a Config).

- [ ] **Step 6: Commit**

```bash
git add services/backend/arm_backend/identity/sources/registry.py services/backend/tests/test_identity_registry_online.py
git commit -m "feat(identity): online-source order and enablement accessors"
```

---

### Task 3: The dispatcher becomes a walk over the registry

**Files:**
- Modify: `services/backend/arm_backend/metadata/dispatcher.py` (whole class; keep `_normalize_volume_label` and the regexes untouched)
- Modify: `services/backend/arm_backend/main.py:202`
- Modify: `services/backend/tests/test_dispatcher.py` (monkeypatch targets, `_call` test, `identify_from_imdb` test, one new order test)
- Modify: `services/backend/tests/test_dispatcher_full.py` (only if a test references `_PROVIDER_BY_LABEL_PREFIX` or `_search_kind`; check with grep)

**Interfaces:**
- Consumes: `build_online_sources`, `capability`, `MUSICBRAINZ_USER_AGENT` (Task 1); `sources_for`, `fingerprint_sources` (Task 2).
- Produces:
  - `MetadataDispatcher(http, *, omdb_api_key_override=None, sources: Mapping[str, OnlineSource] | None = None)`; `.sources` property returning the registry map (routers and `main.py` share it).
  - `identify(...)`, `identify_from_imdb(...)`, `aclose()` unchanged in signature and outcome.
  - `_call(source_id: str, coro)` stamps `result.provider = source_id`.

- [ ] **Step 1: Update the tests that pin internals**

In `tests/test_dispatcher.py`, make these edits:

1. Every `from arm_backend.metadata import dispatcher as dispatcher_mod` paired with `monkeypatch.setattr(dispatcher_mod, "TMDBClient", FakeTMDB)` or `monkeypatch.setattr(dispatcher_mod, "OMDBClient", FakeOMDB)` becomes `from arm_backend.metadata import sources as sources_mod` and `monkeypatch.setattr(sources_mod, "TMDBClient", FakeTMDB)` / `monkeypatch.setattr(sources_mod, "OMDBClient", FakeOMDB)`. Nine tests: `test_identify_tries_title_hint_before_volume_label`, `test_identify_falls_back_to_label_when_hint_misses`, `test_identify_dedupes_hint_equal_to_label`, `test_identify_hint_is_tv_searches_tv_before_movie`, `test_identify_hint_not_tv_keeps_movie_first_order`, `test_identify_tv_first_falls_back_to_movie_when_tv_misses`, `test_identify_hint_candidate_reuses_label_year`, `test_identify_from_imdb_uses_tmdb_find`, `test_identify_prefer_tv_searches_tv_first_for_every_candidate`, `test_identify_prefer_tv_omdb_only_searches_series_then_movie`.

2. Replace `test_call_stamps_canonical_provider` with:

```python
async def test_call_stamps_the_source_id_as_provider() -> None:
    """_call is the one place that knows which source produced a hit; it
    stamps MetadataResult.provider with the source id so identity and
    provider_raw key on it, overwriting anything the client set."""
    from arm_backend.metadata.base import MetadataResult

    dispatcher = MetadataDispatcher(httpx.AsyncClient())

    async def _hit() -> MetadataResult:
        return MetadataResult(title="X", year=None, kind="movie", payload={}, provider="spoofed")

    for sid in ("tmdb", "omdb", "arm_server", "musicbrainz"):
        result = await dispatcher._call(sid, _hit())
        assert result is not None and result.provider == sid, sid

    async def _miss() -> None:
        return None

    assert await dispatcher._call("tmdb", _miss()) is None
    await dispatcher.aclose()
```

3. Add the kind-major order test (the one intentional change, spec D-6):

```python
async def test_title_search_is_kind_major(monkeypatch):
    """All movie sources before any TV source for a movie-shaped candidate:
    tmdb movie, omdb movie, tmdb tv, omdb tv (spec D-6)."""
    from arm_backend.metadata import sources as sources_mod

    order: list[str] = []

    class FakeTMDB:
        def __init__(self, api_key, http):
            pass

        async def search_movie(self, title, year):
            order.append("tmdb:movie")
            return None

        async def search_tv(self, title):
            order.append("tmdb:tv")
            return None

    class FakeOMDB:
        def __init__(self, api_key, http):
            pass

        async def lookup_by_title(self, title, year=None, kind="movie"):
            order.append(f"omdb:{kind}")
            return None

    monkeypatch.setattr(sources_mod, "TMDBClient", FakeTMDB)
    monkeypatch.setattr(sources_mod, "OMDBClient", FakeOMDB)
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="SOMETHING")
        assert await dispatcher.identify(scan, _config()) is None
    assert order == ["tmdb:movie", "omdb:movie", "tmdb:tv", "omdb:tv"]
```

4. Add the injected-registry test:

```python
async def test_dispatcher_accepts_an_injected_registry():
    from arm_backend.metadata.base import MetadataResult

    class OnlyOmdb:
        id = "omdb"
        media_types = frozenset({"movie", "tv"})
        requires_key = "omdb_api_key"

        def configured(self, cfg):
            return None

        async def search_title(self, cfg, kind, title, year):
            return MetadataResult(title=f"{kind}:{title}", year=year, kind=kind)

    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources={"omdb": OnlyOmdb()})
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="BLADE_RUNNER_1982")
        hit = await dispatcher.identify(scan, _config(tmdb_api_key=None, omdb_api_key=None))
    assert hit is not None and hit.title == "movie:BLADE RUNNER" and hit.provider == "omdb"
    assert dispatcher.sources["omdb"].id == "omdb"
```

- [ ] **Step 2: Run the dispatcher suites to verify the new tests fail**

Run: `uv run pytest services/backend/tests/test_dispatcher.py -q`
Expected: FAIL. `test_call_stamps_the_source_id_as_provider` fails on the `"spoofed"`-overwrite assertion or label mapping; the nine patched tests fail because `sources_mod` is not consulted by the old dispatcher; the two new tests fail with `TypeError` (`sources` kwarg) and an order mismatch.

- [ ] **Step 3: Rewrite the dispatcher class**

Replace everything from `class MetadataDispatcher:` to the end of the file with:

```python
class MetadataDispatcher:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        omdb_api_key_override: str | None = None,
        sources: Mapping[str, OnlineSource] | None = None,
    ) -> None:
        self._http = http
        self._sources: dict[str, OnlineSource] = (
            dict(sources)
            if sources is not None
            else build_online_sources(http, omdb_api_key_override=omdb_api_key_override)
        )

    @property
    def sources(self) -> Mapping[str, OnlineSource]:
        """The online-source registry (shared with the metadata routes)."""
        return self._sources

    async def aclose(self) -> None:
        await self._http.aclose()

    async def identify(
        self,
        scan: ScanResult,
        cfg: Config,
        *,
        title_hint: str | None = None,
        title_hint_is_tv: bool = False,
        prefer_tv: bool = False,
    ) -> MetadataResult | None:
        if scan.disc_type in (DiscType.DATA, DiscType.UNKNOWN):
            return None

        if scan.disc_type == DiscType.CD:
            return await self._identify_cd(scan, cfg)

        hit = await self._identify_video(
            scan, cfg, title_hint=title_hint, title_hint_is_tv=title_hint_is_tv, prefer_tv=prefer_tv
        )
        return await self._with_tmdb_ids(hit, cfg)

    async def _identify_cd(self, scan: ScanResult, cfg: Config) -> MetadataResult | None:
        if not scan.musicbrainz_disc_id:
            return None
        for source in sources_for(cfg, "music", self._sources):
            lookup = capability(source, "lookup_disc_id")
            if lookup is None:
                continue
            hit = await self._call(source.id, lookup(cfg, scan.musicbrainz_disc_id))
            if hit is not None:
                return hit
        return None

    async def _identify_video(
        self,
        scan: ScanResult,
        cfg: Config,
        *,
        title_hint: str | None = None,
        title_hint_is_tv: bool = False,
        prefer_tv: bool = False,
    ) -> MetadataResult | None:
        # Fingerprint sources first (the community crc64 → title DB). A hit
        # beats fuzzy title matching because the fingerprint is unique to the
        # disc and there's no false-positive risk.
        crc64 = next(
            (fp.value for fp in scan.fingerprints if fp.algo == "crc64" and fp.value),
            None,
        )
        if crc64:
            for source in fingerprint_sources(cfg, self._sources):
                lookup = capability(source, "lookup_fingerprint")
                if lookup is None:
                    continue
                hit = await self._call(source.id, lookup(cfg, "crc64", crc64))
                if hit is not None:
                    return hit

        # Disc hints (bd_title / label, see arm_backend.identity) supply a
        # cleaner search title than the raw volume label — try it first, then
        # fall back to the normalized volume-label title. Empty and duplicate
        # (case-insensitive) candidates are skipped so a hint equal to the
        # label title doesn't double the provider calls. A hint that carries
        # a season claim (a season/box-set disc) is TV-shaped: search TV before
        # movie for THAT candidate only. The label-derived candidate keeps the
        # movie-first order. The label candidate's year is computed first so
        # the hint candidate — which has no year of its own — is searched with
        # the same year filter.
        label_title: str | None = None
        label_year: int | None = None
        if scan.volume_label:
            label_title, label_year = _normalize_volume_label(scan.volume_label)

        candidates: list[tuple[str, int | None, bool]] = []
        if title_hint and title_hint.strip():
            candidates.append((title_hint.strip(), label_year, title_hint_is_tv))
        if label_title:
            candidates.append((label_title, label_year, False))
        seen: set[str] = set()
        unique: list[tuple[str, int | None, bool]] = []
        for title, year, tv_first in candidates:
            key = title.casefold()
            if key not in seen:
                seen.add(key)
                unique.append((title, year, tv_first))
        if prefer_tv:
            # The disc itself is TV-shaped (arm_common.disc_shape): search TV for
            # every candidate before any movie, so one candidate's movie
            # fallback can't win while another candidate would have found the
            # series.
            for kind in ("tv", "movie"):
                for title, year, _ in unique:
                    hit = await self._search_kind(title, year, cfg, kind)
                    if hit is not None:
                        return hit
            return None
        for title, year, tv_first in unique:
            kinds: tuple[Kind, Kind] = ("tv", "movie") if tv_first else ("movie", "tv")
            for kind in kinds:
                hit = await self._search_kind(title, year, cfg, kind)
                if hit is not None:
                    return hit
        return None

    async def _search_kind(self, title: str, year: int | None, cfg: Config, kind: Kind) -> MetadataResult | None:
        """One kind: every enabled source for it, in the operator's order."""
        for source in sources_for(cfg, kind, self._sources):
            search = capability(source, "search_title")
            if search is None:
                continue
            hit = await self._call(source.id, search(cfg, kind, title, year))
            if hit is not None:
                return hit
        return None

    async def identify_from_imdb(self, imdb_id: str, cfg: Config) -> MetadataResult | None:
        """Exact-ID identify for a TheDiscDB-matched disc. TMDb's /find
        endpoint resolves an IMDb id for both movies and TV; requires a TMDb
        key. Returns None (caller falls back to fuzzy identify) otherwise.
        PR 2 (spec D-1) replaces the fixed TMDb choice with a walk over
        `sources_for`."""
        tmdb = self._sources.get("tmdb")
        if not imdb_id or tmdb is None or tmdb.configured(cfg) is not None:
            return None
        lookup = capability(tmdb, "lookup_imdb")
        if lookup is None:
            return None
        hit = await self._call(tmdb.id, lookup(cfg, imdb_id))
        if hit is not None:
            hit.payload.setdefault("imdb_id", imdb_id)
        return await self._with_tmdb_ids(hit, cfg)

    async def _with_tmdb_ids(self, hit: MetadataResult | None, cfg: Config) -> MetadataResult | None:
        """Fill a TMDb hit's IMDb / TVDB ids (one `external_ids` call) so the
        stored identity lets every episode source find the show (spec 3.4).
        Ids already in the payload win; a failed or timed-out call (bounded
        by PROVIDER_TIMEOUT_SECONDS) changes nothing. The last direct client
        use in this module; PR 2b generalizes it to `fill_external_ids`."""
        if hit is None or hit.provider != "tmdb" or hit.kind not in ("movie", "tv") or not cfg.tmdb_api_key:
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

    async def _call(self, source_id: str, coro) -> MetadataResult | None:  # type: ignore[no-untyped-def]
        try:
            result: MetadataResult | None = await asyncio.wait_for(coro, timeout=PROVIDER_TIMEOUT_SECONDS)
            if result is not None:
                # The source id keys provider_raw and identity.provider.
                result.provider = source_id
            return result
        except asyncio.TimeoutError:
            logger.info("metadata.%s timeout", source_id)
            return None
        except LookupError as e:
            logger.info("metadata.%s miss: %s", source_id, e)
            return None
```

Update the module header: delete `_PROVIDER_BY_LABEL_PREFIX` and the `MUSICBRAINZ_USER_AGENT` constant and its comment; delete the imports of `ArmServerClient`, `MusicBrainzClient`, `OMDBClient`; keep `TMDBClient` (used by `_with_tmdb_ids`); add:

```python
from collections.abc import Mapping

from arm_backend.identity.sources.registry import fingerprint_sources, sources_for
from arm_backend.metadata.sources import Kind, OnlineSource, build_online_sources, capability
```

and drop `from typing import Literal` if nothing else uses it. Keep `PROVIDER_TIMEOUT_SECONDS` and `DISPATCH_TIMEOUT_SECONDS` where they are.

- [ ] **Step 4: Run the dispatcher suites**

Run: `uv run pytest services/backend/tests/test_dispatcher.py services/backend/tests/test_dispatcher_full.py -q`
Expected: all passed (35 existing minus 1 replaced plus 2 new in `test_dispatcher.py`; 13 in `test_dispatcher_full.py`). If `test_dispatcher_full.py` fails on `test_no_providers_configured_returns_none`, check that `sources_for` really returns `()` when both keys are None.

- [ ] **Step 5: Share the registry from `main.py`**

Change `services/backend/arm_backend/main.py:202` to:

```python
    app.state.dispatcher = MetadataDispatcher(http, omdb_api_key_override=settings.OMDB_API_KEY)
    app.state.online_sources = app.state.dispatcher.sources
```

- [ ] **Step 6: Run the router suites that stub the dispatcher, then lint**

Run: `uv run pytest services/backend/tests/test_ripper_router.py -q && uv run ruff check services/backend/arm_backend && uv run mypy services/backend/arm_backend/metadata/dispatcher.py services/backend/arm_backend/main.py`
Expected: all passed; no lint or type errors.

- [ ] **Step 7: Commit**

```bash
git add services/backend/arm_backend/metadata/dispatcher.py services/backend/arm_backend/main.py services/backend/tests/test_dispatcher.py services/backend/tests/test_dispatcher_full.py
git commit -m "refactor(metadata): dispatcher walks the online-source registry"
```

---

### Task 4: Metadata routes read the registry

**Files:**
- Modify: `services/backend/arm_backend/routers/metadata.py:14-18, 42-43, 67-140, 145-170`
- Modify: `services/backend/tests/test_metadata_search_router.py:40-51` (`_make_app`) and add four tests

**Interfaces:**
- Consumes: `request.app.state.online_sources` (set by `main.py` in Task 3), `capability`, `MUSICBRAINZ_USER_AGENT` (Task 1), `sources_for`, `search_source`, `known_source_ids` (Task 2).
- Produces: no API change. `SearchProvider` stays `Literal["tmdb", "omdb"]`.

- [ ] **Step 1: Update `_make_app` and add the failing tests**

In `_make_app`, after `app.state.http = httpx.AsyncClient(timeout=5.0)` add:

```python
    app.state.online_sources = build_online_sources(app.state.http)
```

with `from arm_backend.metadata.sources import build_online_sources  # noqa: E402` among the imports.

Add these tests at the end of the file (five; the key-check one needs no app):

```python
def test_search_provider_literal_matches_registry() -> None:
    """One spelling of the movie/TV source ids (spec S-8): the OpenAPI enum
    and the registry cannot drift apart."""
    from typing import get_args

    from arm_backend.identity.sources.registry import known_source_ids

    reg = build_online_sources(httpx.AsyncClient())
    assert set(get_args(metadata_router.SearchProvider)) == set(known_source_ids("movie", reg))
    assert set(get_args(metadata_router.SearchProvider)) == set(known_source_ids("tv", reg))


def test_key_check_map_matches_registry_requires_key() -> None:
    """The key-check route's name → Config attribute map (routers/config.py
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
            json={"Response": "True", "Search": [{"Title": "Heat", "Year": "1995", "imdbID": "tt0113277", "Type": "movie"}]},
        )
    )
    db = FakeSession()
    _seed(db, tmdb_api_key=None, omdb_api_key="k", metadata_provider="tmdb")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/search", params={"title": "heat"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"][0]["title"] == "Heat"


@respx.mock
def test_lookup_imdb_walks_to_omdb_when_tmdb_unkeyed(signing_key: bytes) -> None:
    """/lookup?imdb_id tries the listed sources in order; with no TMDb key,
    OMDb `i=` answers (today's metadata_provider=omdb behaviour, now by walk)."""
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200, json={"Response": "True", "Title": "Heat", "Year": "1995", "Type": "movie", "imdbID": "tt0113277"}
        )
    )
    db = FakeSession()
    _seed(db, tmdb_api_key=None, omdb_api_key="k", metadata_provider="omdb")
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/metadata/lookup", params={"imdb_id": "tt0113277"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["candidates"][0]["title"] == "Heat"
```

Also change two existing tests whose premise moves from `metadata_provider` to the walk:

- `test_search_default_provider_is_first_configured_source` above replaces nothing, but `test_lookup_imdb_no_omdb_key_returns_400` (seeded `metadata_provider="omdb", omdb_api_key=None`, no TMDb key) now expects detail `"no tmdb key configured"`: with no key at all, the error names the first listed source. Update its assertion accordingly.
- `test_lookup_uses_omdb_when_provider_omdb` seeds `metadata_provider="omdb", omdb_api_key="k"` and no TMDb key; it still passes by the walk. Leave it, but rename it `test_lookup_uses_omdb_when_tmdb_unkeyed` and update its docstring.

- [ ] **Step 2: Run the router suite to verify the new tests fail**

Run: `uv run pytest services/backend/tests/test_metadata_search_router.py -q`
Expected: the four new tests fail (`build_online_sources` import works, but the literal test may pass already; the three HTTP tests fail because the route still reads `metadata_provider`).

- [ ] **Step 3: Rewrite the three routes**

Replace the imports of `ArmServerClient`, `MusicBrainzClient`, `OMDBClient`, `TMDBClient` and the `MUSICBRAINZ_USER_AGENT` block with:

```python
from collections.abc import Mapping

from arm_backend.identity.sources.registry import fingerprint_sources, search_source, sources_for
from arm_backend.metadata.musicbrainz import MusicBrainzClient
from arm_backend.metadata.sources import MUSICBRAINZ_USER_AGENT, OnlineSource, capability
```

(`MusicBrainzClient` stays for `/music/{release_id}`, which is MusicBrainz-specific per spec §5.3.)

Add a helper under `_to_candidate`:

```python
def _registry(request: Request) -> Mapping[str, OnlineSource]:
    registry: Mapping[str, OnlineSource] = request.app.state.online_sources
    return registry


async def _config(db: AsyncSession) -> Config:
    cfg = (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="config not initialised")
    return cfg
```

Replace the body of `search_metadata`:

```python
    cfg = await _config(db)
    registry = _registry(request)
    if provider is not None:
        source = registry.get(provider)
        if source is None or source.configured(cfg) is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"no {provider} key configured")
    else:
        source = search_source(cfg, type, registry)
        if source is None:
            first = next(iter(online_source_ids(cfg, type)), "tmdb")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"no {first} key configured")
    search = capability(source, "search_candidates")
    if search is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{source.id} cannot search titles")
    try:
        results = await search(cfg, type, title)
    except (MetaLookupError, LookupTimeout) as exc:
        return MetadataSearchResponse(candidates=[], detail=str(exc))
    except httpx.HTTPError as exc:
        return MetadataSearchResponse(candidates=[], detail=f"{source.id} unavailable: {exc}")
    for r in results:
        r.provider = source.id
    return MetadataSearchResponse(candidates=[_to_candidate(r) for r in results])
```

`online_source_ids` is imported from the registry alongside the other accessors. The error for a missing default key therefore stays `no tmdb key configured` when nothing is keyed (the existing `test_search_no_key_returns_400` assertion).

Replace the body of `lookup_metadata` after the XOR guard:

```python
    registry = _registry(request)
    try:
        if imdb_id is not None:
            cfg = await _config(db)
            ranked = [s for s in sources_for(cfg, "movie", registry) if capability(s, "lookup_imdb")]
            if not ranked:
                first = next(iter(online_source_ids(cfg, "movie")), "tmdb")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"no {first} key configured")
            result = None
            for source in ranked:
                result = await capability(source, "lookup_imdb")(cfg, imdb_id)  # type: ignore[misc]
                if result is not None:
                    result.provider = source.id
                    break
            if result is None:
                return MetadataSearchResponse(candidates=[], detail="no match")
        else:
            # The community DB needs no key or Config; a missing Config row
            # must not block it (today's behaviour), so read the row nullable.
            cfg = (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
            result = None
            for source in fingerprint_sources(cfg, registry):
                lookup = capability(source, "lookup_fingerprint")
                if lookup is None:
                    continue
                result = await lookup(cfg, "crc64", crc64)
                if result is not None:
                    result.provider = source.id
                    break
            if result is None:
                return MetadataSearchResponse(candidates=[], detail="no match")
    except (MetaLookupError, LookupTimeout) as exc:
        return MetadataSearchResponse(candidates=[], detail=str(exc))
    except httpx.HTTPError as exc:
        return MetadataSearchResponse(candidates=[], detail=f"lookup unavailable: {exc}")
    return MetadataSearchResponse(candidates=[_to_candidate(result)])
```

`test_lookup_config_not_initialised_returns_400` sends `imdb_id`, so it goes through `_config(db)` and gets `config not initialised`. `test_lookup_by_crc64` seeds a Config row; the nullable read above keeps the crc64 path working without one.

Replace the `MusicBrainzClient(...).search_releases(...)` call in `search_music` with:

```python
    cfg = await _config(db)
    source = search_source(cfg, "music", _registry(request))
    search = capability(source, "search_releases") if source is not None else None
    if source is None or search is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no music source configured")
    try:
        results = await search(
            cfg,
            query,
            artist=artist,
            track_count=track_count,
            release_type=release_type,
            format=format,
            country=country,
            status=status,
        )
    except (MetaLookupError, LookupTimeout) as exc:
        return MetadataSearchResponse(candidates=[], detail=str(exc))
    except httpx.HTTPError as exc:
        return MetadataSearchResponse(candidates=[], detail=f"{source.id} unavailable: {exc}")
```

`search_music` gains `db: AsyncSession = Depends(get_session)`; `test_music_search` and its siblings call `_seed(db)` already, so a Config row exists. The `status` query parameter shadows the `fastapi.status` module inside this function (it already does today); keep using the numeric `400` literal there or alias the import as `from fastapi import status as http_status` at the top and use it throughout the file.

Leave `music_release_detail` on `MusicBrainzClient(MUSICBRAINZ_USER_AGENT, http).get_release(release_id)`.

- [ ] **Step 4: Run the router suite**

Run: `uv run pytest services/backend/tests/test_metadata_search_router.py -q`
Expected: 37 passed. Expected casualties to fix as they show: `mock.patch.object(omdb_mod.OMDBClient, "search_candidates", …)` and the MusicBrainz patch still work because the adapters construct the real classes.

- [ ] **Step 5: Full backend suite, lint, types**

Run: `uv run pytest -q && uv run pre-commit run --all-files`
Expected: all green. The OpenAPI drift check must not fire: run `bash devtools/regen-openapi-snapshot.sh && git diff --stat services/ui-neu/openapi.snapshot.json` and expect no diff (no route signature changed except the added `db` dependency on `/music/search`, which does not appear in the schema). If a diff appears, inspect it; if it is only the new dependency, commit the regenerated snapshot and the TS types (`bash services/ui-neu/scripts/codegen.sh`) in this task.

- [ ] **Step 6: Commit**

```bash
git add services/backend/arm_backend/routers/metadata.py services/backend/tests/test_metadata_search_router.py
git commit -m "refactor(metadata): search and lookup routes read the online-source registry"
```

---

### Task 5: Architecture note and spec cross-reference

**Files:**
- Modify: `docs/developers/architecture/02-job-lifecycle.md` (insert before the `### Unidentified and placeholder rips` heading, line 343 today)
- Modify: `docs/superpowers/specs/2026-10-14-identification-sources-design.md` §10

**Interfaces:** none.

- [ ] **Step 1: Add the registry paragraph to the job lifecycle doc**

Before `### Unidentified and placeholder rips`, add:

```markdown
#### Online sources

Every online title lookup goes through one registry (`arm_backend/metadata/sources.py`, accessors in `arm_backend/identity/sources/registry.py`). An adapter per provider (`tmdb`, `omdb`, `musicbrainz`, `arm_server`) wraps the HTTP client and reports whether it is configured; `sources_for(cfg, media_type, registry)` is the only function that decides which sources run and in which order. The dispatcher walks that list per kind (movie or TV, in the order the disc shape suggests), the job page's search and IMDb lookup routes read the same list, and `MetadataResult.provider` is always the source id. The order is a built-in default until the Identification settings (spec `2026-10-14-identification-sources-design.md`) make it operator-configurable.
```

- [ ] **Step 2: Record the TV-list question in the spec**

Append to §10 of the spec:

```markdown
- PR 0 keeps OMDb in the TV title-search order (`tmdb, omdb`), as today. The v4.2 card's TV
  list is `episode_sources` (`tmdb, tvmaze, tvdb`), which has no OMDb row. PR 2 must either
  add `omdb` as a TV source in that list's `enum_values` or accept that OMDb series search is
  dropped; decide before PR 2.
```

- [ ] **Step 3: Commit**

```bash
git add docs/developers/architecture/02-job-lifecycle.md docs/superpowers/specs/2026-10-14-identification-sources-design.md
git commit -m "docs: online-source registry in the job lifecycle; TV-list open item"
```

---

## Self-review notes

- **Spec coverage.** §5.1 protocol and adapters: Task 1. §5.2 accessors: Task 2 (`search_source` reads the first usable listed source instead of `search_provider_*` until PR 1, as §6 PR 0 says). §5.3 consumers: dispatcher rows in Task 3; metadata routes in Task 4; `stage_runner`, `routers/config.py`, `RankedListField` are later PRs by the spec's own table. §6 PR 0 scope: all four bullets. §7 tests: dispatcher and router suites.
- **Deviation recorded.** Capability methods take `cfg` first (the spec's signatures omit it). Spec §5.1 should be updated to match when PR 0 merges; Task 5 does not edit §5.1 to keep the spec diff minimal during review.
- **Behaviour change recorded.** Kind-major title search (Task 3 test) per spec D-6.
- **Type consistency.** `sources_for(cfg, media_type, registry)`, `search_source(cfg, media_type, registry)`, `fingerprint_sources(cfg, registry)`, `known_source_ids(media_type, registry)`, `online_source_ids(cfg, media_type)` are used with those argument orders in Tasks 3 and 4. Capability names match Task 1 throughout.
