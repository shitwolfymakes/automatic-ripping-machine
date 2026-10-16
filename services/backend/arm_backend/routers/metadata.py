"""Metadata search / lookup / music endpoints. Per-key validity checks live at
POST /api/config/keys/{name}/check (routers/config.py)."""

import logging
from collections.abc import Mapping
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_backend.identity.sources.registry import (
    fingerprint_sources,
    known_source_ids,
    lookup_sources,
    online_source_ids,
    search_provider_setting,
    search_source,
)
from arm_backend.metadata.base import LookupError as MetaLookupError
from arm_backend.metadata.base import LookupTimeout, MetadataResult, external_ids_of, extract_poster_url
from arm_backend.metadata.musicbrainz import MusicBrainzClient
from arm_backend.metadata.sources import MUSICBRAINZ_USER_AGENT, OnlineSource, capability
from arm_backend.seeders import CONFIG_SINGLETON_ID
from arm_common import Config, User
from arm_common.schemas import (
    MetadataCandidate,
    MetadataReleaseDetail,
    MetadataReleaseTrack,
    MetadataSearchResponse,
)

logger = logging.getLogger("arm_backend.routers.metadata")

router = APIRouter(prefix="/api/metadata", tags=["metadata"])


# ---------------------------------------------------------------------------
# Search / lookup / music endpoints
# ---------------------------------------------------------------------------

SearchType = Literal["movie", "tv"]
SearchProvider = Literal["tmdb", "omdb", "tvmaze", "tvdb"]


def _to_candidate(r: MetadataResult) -> MetadataCandidate:
    payload = r.payload or {}
    provider_id = payload.get("imdb_id") or payload.get("imdbID") or payload.get("id")
    rg = payload.get("release-group") or {}
    track_count = payload.get("track_count") or payload.get("track-count")
    return MetadataCandidate(
        title=r.title,
        year=r.year,
        kind=r.kind,
        poster_url=extract_poster_url(r),
        provider_id=str(provider_id) if provider_id is not None else None,
        release_type=(rg.get("primary-type") if isinstance(rg, dict) else None),
        format=payload.get("format"),
        country=payload.get("country"),
        status=payload.get("status"),
        track_count=int(track_count) if isinstance(track_count, int) else None,
        external_ids=external_ids_of(r),
    )


def _registry(request: Request) -> Mapping[str, OnlineSource]:
    registry: Mapping[str, OnlineSource] = request.app.state.online_sources
    return registry


async def _config(db: AsyncSession) -> Config:
    cfg = (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="config not initialised")
    return cfg


def _preferred_id(cfg: Config | None, media_type: str, registry: Mapping[str, OnlineSource]) -> str:
    """The provider a "no key configured" error names: the operator's chosen
    one, else the first listed source, else tmdb."""
    chosen = search_provider_setting(cfg, media_type)
    if chosen in known_source_ids(media_type, registry):
        return str(chosen)
    return next(iter(online_source_ids(cfg, media_type)), "tmdb")


@router.get("/search", response_model=MetadataSearchResponse)
async def search_metadata(
    request: Request,
    title: str,
    type: SearchType = "movie",
    provider: SearchProvider | None = None,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> MetadataSearchResponse:
    cfg = await _config(db)
    registry = _registry(request)
    if provider is not None:
        source = registry.get(provider)
        if source is not None and type not in source.media_types:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST, detail=f"{provider} does not search {type}"
            )
        if source is None or source.configured(cfg) is not None:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=f"no {provider} key configured")
    else:
        source = search_source(cfg, type, registry)
        if source is None:
            name = _preferred_id(cfg, type, registry)
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=f"no {name} key configured")
    search = capability(source, "search_candidates")
    if search is None:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=f"{source.id} cannot search titles")
    try:
        results = await search(cfg, type, title)
    except (MetaLookupError, LookupTimeout) as exc:
        return MetadataSearchResponse(candidates=[], detail=str(exc))
    except httpx.HTTPError as exc:
        return MetadataSearchResponse(candidates=[], detail=f"{source.id} unavailable: {exc}")
    for r in results:
        r.provider = source.id
    return MetadataSearchResponse(candidates=[_to_candidate(r) for r in results])


@router.get("/lookup", response_model=MetadataSearchResponse)
async def lookup_metadata(
    request: Request,
    imdb_id: str | None = None,
    crc64: str | None = None,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> MetadataSearchResponse:
    if (imdb_id is None) == (crc64 is None):
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="exactly one of imdb_id or crc64 is required",
        )
    registry = _registry(request)
    try:
        if imdb_id is not None:
            cfg = await _config(db)
            ranked = [(s, fn) for s in lookup_sources(cfg, "movie", registry) if (fn := capability(s, "lookup_imdb"))]
            if not ranked:
                name = _preferred_id(cfg, "movie", registry)
                raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=f"no {name} key configured")
            result = None
            for source, imdb_lookup in ranked:
                result = await imdb_lookup(cfg, imdb_id)
                if result is not None:
                    result.provider = source.id
                    break
            if result is None:
                return MetadataSearchResponse(candidates=[], detail="no match")
        else:
            # The community DB needs no key or Config; a missing Config row
            # must not block it (today's behaviour), so read the row nullable.
            fp_cfg = (
                await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))
            ).scalar_one_or_none()
            result = None
            for source in fingerprint_sources(fp_cfg, registry):
                lookup = capability(source, "lookup_fingerprint")
                if lookup is None:
                    continue
                result = await lookup(fp_cfg, "crc64", crc64)
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


@router.get("/music/search", response_model=MetadataSearchResponse)
async def search_music(
    request: Request,
    query: str,
    artist: str | None = None,
    track_count: int | None = None,
    release_type: str | None = None,
    format: str | None = None,
    country: str | None = None,
    status: str | None = None,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> MetadataSearchResponse:
    cfg = await _config(db)
    source = search_source(cfg, "music", _registry(request))
    search = capability(source, "search_releases") if source is not None else None
    if source is None or search is None:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="no music source configured")
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
    return MetadataSearchResponse(candidates=[_to_candidate(r) for r in results])


@router.get("/music/{release_id}", response_model=MetadataReleaseDetail)
async def music_release_detail(
    release_id: str,
    request: Request,
    _: User = Depends(require_jwt),
) -> MetadataReleaseDetail:
    http: httpx.AsyncClient = request.app.state.http
    try:
        result = await MusicBrainzClient(MUSICBRAINZ_USER_AGENT, http).get_release(release_id)
    except MetaLookupError as exc:
        # _get collapses every failure mode into a MetaLookupError subclass:
        # a real 404 (unknown MBID), transport failures (wrapped LookupError),
        # and timeouts (LookupTimeout, a LookupError subclass). We discriminate
        # on the message: the not-found path carries the `not_found_detail`
        # string ("...release not found") → 404; anything else (transport /
        # timeout / 5xx / bad status) is an upstream outage → 502.
        if "not found" in str(exc):
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY, detail=f"musicbrainz unavailable: {exc}"
        ) from exc
    payload = result.payload or {}
    raw_tracks = payload.get("tracks") or []
    tracks = [
        MetadataReleaseTrack(
            position=t.get("position"),
            title=t.get("title") or "",
            length_ms=t.get("length_ms"),
            disc_number=t.get("disc_number"),
        )
        for t in raw_tracks
    ]
    return MetadataReleaseDetail(
        release_id=release_id,
        title=result.title,
        artist=payload.get("artist"),
        year=result.year,
        poster_url=extract_poster_url(result),
        catalog_number=payload.get("catalog_number"),
        barcode=payload.get("barcode"),
        country=payload.get("country"),
        format=payload.get("format"),
        status=payload.get("status"),
        disc_count=payload.get("disc_count"),
        track_count=payload.get("track_count"),
        tracks=tracks,
    )
