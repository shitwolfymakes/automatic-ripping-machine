"""Online metadata sources (spec §5.1): one adapter per HTTP client.

An adapter knows which client method implements which capability and which
Config key it needs. It constructs the client per call from `cfg`, so a key
saved after boot is used on the next lookup. Order and enablement are not
decided here: `identity.sources.registry.sources_for` does that."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, Protocol

import httpx
from arm_common import Config

from arm_backend.metadata.arm_server import ArmServerClient
from arm_backend.metadata.base import MetadataResult
from arm_backend.metadata.musicbrainz import MusicBrainzClient
from arm_backend.metadata.omdb import OMDBClient
from arm_backend.metadata.tmdb import TMDBClient

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
    requires_key: str | None = "tmdb_api_key"

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
    requires_key: str | None = "omdb_api_key"

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
    requires_key: str | None = None

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
    requires_key: str | None = None

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
