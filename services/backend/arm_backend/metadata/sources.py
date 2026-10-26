"""Online metadata sources (spec §5.1): one adapter per HTTP client.

An adapter knows which client method implements which capability and which
Config key it needs. It reads the key off `cfg` on every call, so a key saved
after boot is used on the next lookup (TVDB, whose client holds a login token,
keeps one client per key and replaces it when the key changes). Order and
enablement are not decided here: `identity.sources.registry.sources_for` does
that."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, Protocol

import httpx
from arm_common import DEFAULT_MUSICBRAINZ_USER_AGENT, Config

from arm_backend.metadata.arm_server import ArmServerClient
from arm_backend.metadata.base import MetadataResult
from arm_backend.metadata.musicbrainz import MusicBrainzClient
from arm_backend.metadata.omdb import OMDBClient
from arm_backend.metadata.tmdb import TMDBClient
from arm_backend.metadata.tvdb import TVDBClient
from arm_backend.metadata.tvmaze import TVMazeClient

Kind = Literal["movie", "tv"]

# MusicBrainz 403s any User-Agent that doesn't follow their etiquette guide's
# `AppName/version ( contact )` shape. Not operator-configurable (Config.
# musicbrainz_user_agent is dormant — see config_metadata.py), and the one
# spelling lives in arm_common so a version bump is a single edit.
MUSICBRAINZ_USER_AGENT = DEFAULT_MUSICBRAINZ_USER_AGENT


class OnlineSource(Protocol):
    id: str
    media_types: frozenset[str]
    # The Config column this source needs, or None when it needs nothing.
    # `configured()` is derived from it (see `_Adapter`), and a test pins the
    # key-check route's `_KEY_ATTR` map to it, so the Keys tab cannot end up
    # checking one key while the source reads another.
    requires_key: str | None

    def configured(self, cfg: Config | None) -> str | None:
        """None when usable; otherwise the skip reason (e.g. "no tmdb key")."""
        ...

    # Capabilities are optional methods; `capability()` finds them. Each takes
    # `cfg` first. Names and signatures:
    #   search_title(cfg, kind, title, year) -> MetadataResult | None
    #   search_candidates(cfg, kind, title, limit=10) -> list[MetadataResult]
    #   lookup_imdb(cfg, imdb_id) -> MetadataResult | None
    #   details(cfg, kind, provider_id) -> MetadataResult
    #   lookup_disc_id(cfg, disc_id, toc=None) -> MetadataResult | None
    #   lookup_fingerprint(cfg, algo, value) -> MetadataResult | None
    #   search_releases(cfg, query, *, artist, track_count, release_type,
    #                   format, country, status) -> list[MetadataResult]


def capability(source: object, name: str) -> Callable[..., Any] | None:
    """The capability method `name` of `source`, or None when it lacks it."""
    method = getattr(source, name, None)
    return method if callable(method) else None


class _Adapter:
    """Shared adapter plumbing: the app's httpx client plus the one place a
    source names the key it needs. `requires_key` is that declaration and
    `configured` is read off it, so the two can never disagree and a keyless
    source states nothing at all."""

    id: str
    media_types: frozenset[str] = frozenset()
    requires_key: str | None = None

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    def _key(self, cfg: Config | None) -> str:
        if self.requires_key is None:
            return ""
        return (getattr(cfg, self.requires_key, None) or "").strip()

    def configured(self, cfg: Config | None) -> str | None:
        """None when usable; otherwise the skip reason (e.g. "no tmdb key")."""
        if self.requires_key is None:
            return None
        return None if self._key(cfg) else f"no {self.id} key"


class TmdbSource(_Adapter):
    id = "tmdb"
    media_types = frozenset({"movie", "tv"})
    requires_key: str | None = "tmdb_api_key"

    def _client(self, cfg: Config) -> TMDBClient:
        return TMDBClient(self._key(cfg), self._http)

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

    async def details(self, cfg: Config, kind: Kind, provider_id: str) -> MetadataResult:
        return await self._client(cfg).detail_result(provider_id, kind)


class OmdbSource(_Adapter):
    id = "omdb"
    media_types = frozenset({"movie", "tv"})
    requires_key: str | None = "omdb_api_key"

    def _client(self, cfg: Config) -> OMDBClient:
        return OMDBClient(self._key(cfg), self._http)

    async def search_title(self, cfg: Config, kind: Kind, title: str, year: int | None) -> MetadataResult | None:
        return await self._client(cfg).lookup_by_title(title, year, kind=kind)

    async def search_candidates(self, cfg: Config, kind: Kind, title: str, limit: int = 10) -> list[MetadataResult]:
        return await self._client(cfg).search_candidates(title, kind=kind, limit=limit)

    async def lookup_imdb(self, cfg: Config, imdb_id: str) -> MetadataResult | None:
        return await self._client(cfg).lookup_by_imdb_id(imdb_id)

    async def details(self, cfg: Config, kind: Kind, provider_id: str) -> MetadataResult:
        return await self._client(cfg).lookup_by_imdb_id(provider_id)


class TvmazeSource(_Adapter):
    """TVmaze: keyless TV title search, candidates and IMDb lookup."""

    id = "tvmaze"
    media_types = frozenset({"tv"})

    async def search_title(self, cfg: Config | None, kind: Kind, title: str, year: int | None) -> MetadataResult | None:
        if kind != "tv":
            return None
        return await TVMazeClient(self._http).search_show(title)

    async def search_candidates(
        self, cfg: Config | None, kind: Kind, title: str, limit: int = 10
    ) -> list[MetadataResult]:
        if kind != "tv":
            return []
        return await TVMazeClient(self._http).search_candidates(title, limit=limit)

    async def lookup_imdb(self, cfg: Config | None, imdb_id: str) -> MetadataResult | None:
        return await TVMazeClient(self._http).lookup_by_imdb_id(imdb_id)

    async def details(self, cfg: Config | None, kind: Kind, provider_id: str) -> MetadataResult:
        return await TVMazeClient(self._http).show_details(provider_id)


class TvdbSource(_Adapter):
    """TVDB v4: keyed TV title search, candidates and IMDb lookup."""

    id = "tvdb"
    media_types = frozenset({"tv"})
    requires_key: str | None = "tvdb_api_key"

    def __init__(self, http: httpx.AsyncClient) -> None:
        super().__init__(http)
        self._cached: TVDBClient | None = None
        self._cached_key: str | None = None

    def _client(self, cfg: Config | None) -> TVDBClient:
        """One client per key, reused. TVDB v4 authenticates with a login
        handshake and caches the bearer token on the client, so building a
        fresh one per call (as every other adapter does, their keys riding on
        each request) cost a POST /login before every search and lookup. A key
        saved after boot replaces the cached client on the next call."""
        key = self._key(cfg)
        if self._cached is None or self._cached_key != key:
            self._cached = TVDBClient(key, self._http)
            self._cached_key = key
        return self._cached

    async def search_title(self, cfg: Config | None, kind: Kind, title: str, year: int | None) -> MetadataResult | None:
        if kind != "tv":
            return None
        return await self._client(cfg).search_series(title)

    async def search_candidates(
        self, cfg: Config | None, kind: Kind, title: str, limit: int = 10
    ) -> list[MetadataResult]:
        if kind != "tv":
            return []
        return await self._client(cfg).search_candidates(title, limit=limit)

    async def lookup_imdb(self, cfg: Config | None, imdb_id: str) -> MetadataResult | None:
        return await self._client(cfg).lookup_by_imdb_id(imdb_id)

    async def details(self, cfg: Config | None, kind: Kind, provider_id: str) -> MetadataResult:
        return await self._client(cfg).series_details(provider_id)


class MusicBrainzSource(_Adapter):
    id = "musicbrainz"
    media_types = frozenset({"music"})

    def _client(self) -> MusicBrainzClient:
        return MusicBrainzClient(MUSICBRAINZ_USER_AGENT, self._http)

    async def lookup_disc_id(self, cfg: Config | None, disc_id: str, toc: str | None = None) -> MetadataResult | None:
        return await self._client().lookup_disc_id(disc_id, toc)

    async def search_releases(
        self,
        cfg: Config | None,
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


class ArmServerSource(_Adapter):
    """The ARM community database: DVD CRC64 → title. A fingerprint source
    only (spec Step 2), never a title-search source."""

    id = "arm_server"

    async def lookup_fingerprint(self, cfg: Config | None, algo: str, value: str) -> MetadataResult | None:
        if algo != "crc64" or not value:
            return None
        return await ArmServerClient(self._http).lookup_by_crc64(value)


def build_online_sources(http: httpx.AsyncClient) -> dict[str, OnlineSource]:
    """Every online source, keyed by id, sharing the app's httpx client."""
    sources: list[OnlineSource] = [
        TmdbSource(http),
        OmdbSource(http),
        TvmazeSource(http),
        TvdbSource(http),
        MusicBrainzSource(http),
        ArmServerSource(http),
    ]
    return {s.id: s for s in sources}
