"""Metadata API-key tester. Validates omdb/tmdb/tvdb keys against the upstream
service; makemkv is a structural/presence check only (the ripper owns the
update-key script, so true validity is confirmed at rip time). Ports neu's
GET /api/v1/metadata/test-key."""

import logging
import re
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_backend.metadata.arm_server import ArmServerClient
from arm_backend.metadata.base import LookupError as MetaLookupError
from arm_backend.metadata.base import LookupTimeout, MetadataResult, extract_poster_url
from arm_backend.metadata.musicbrainz import MusicBrainzClient
from arm_backend.metadata.omdb import OMDBClient
from arm_backend.metadata.tmdb import TMDBClient
from arm_backend.metadata.tvdb import TVDBClient
from arm_backend.seeders import CONFIG_SINGLETON_ID
from arm_common import Config, User
from arm_common.schemas import MetadataCandidate, MetadataKeyTestResponse, MetadataProvider, MetadataSearchResponse

logger = logging.getLogger("arm_backend.routers.metadata")

router = APIRouter(prefix="/api/metadata", tags=["metadata"])

# MakeMKV registration keys look like `M-xxxx...` (Crockford-ish base32 with
# dashes). We can only confirm the format offline; true validity is checked by
# the ripper at scan time. Mirrors neu's INVALID_MAKEMKV_SERIAL case.
_MAKEMKV_SERIAL_RE = re.compile(r"^M-[0-9A-Za-z-]+$")
_TMDB_CONFIG_URL = "https://api.themoviedb.org/3/configuration"
_OMDB_URL = "https://www.omdbapi.com/"
_TIMEOUT_SECONDS = 8.0


@router.get("/test-key", response_model=MetadataKeyTestResponse)
async def test_key(
    request: Request,
    provider: MetadataProvider,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> MetadataKeyTestResponse:
    cfg = (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="config not initialised")

    http: httpx.AsyncClient = request.app.state.http

    if provider == "makemkv":
        key = (cfg.makemkv_key or "").strip()
        if not key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no makemkv key configured")
        valid = bool(_MAKEMKV_SERIAL_RE.match(key))
        detail = (
            "format/presence only — MakeMKV validity is confirmed at rip time"
            if valid
            else "key does not match the MakeMKV serial format (M-...)"
        )
        return MetadataKeyTestResponse(provider=provider, valid=valid, detail=detail)

    key_attr = {"omdb": "omdb_api_key", "tmdb": "tmdb_api_key", "tvdb": "tvdb_api_key"}[provider]
    key = (getattr(cfg, key_attr) or "").strip()
    if not key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"no {provider} key configured")

    try:
        if provider == "tvdb":
            await TVDBClient(key, http).validate_key()
        elif provider == "tmdb":
            r = await http.get(
                _TMDB_CONFIG_URL,
                headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
                timeout=_TIMEOUT_SECONDS,
            )
            if r.status_code != 200:
                raise MetaLookupError(f"tmdb status={r.status_code}")
        else:  # omdb
            r = await http.get(_OMDB_URL, params={"apikey": key, "t": "the matrix"}, timeout=_TIMEOUT_SECONDS)
            if r.status_code != 200:
                raise MetaLookupError(f"omdb status={r.status_code}")
            body = r.json()
            # OMDB returns 200 + {"Response":"False","Error":"Invalid API key!"} on a bad key.
            if body.get("Response") != "True" and "API key" in (body.get("Error") or ""):
                raise MetaLookupError(body.get("Error", "omdb auth failed"))
    except MetaLookupError as exc:
        logger.warning("test-key invalid provider=%s", provider)
        return MetadataKeyTestResponse(provider=provider, valid=False, detail=str(exc))
    except httpx.TimeoutException:
        return MetadataKeyTestResponse(provider=provider, valid=False, detail="request timed out")
    except httpx.HTTPError as exc:
        return MetadataKeyTestResponse(provider=provider, valid=False, detail=f"transport error: {exc}")

    return MetadataKeyTestResponse(provider=provider, valid=True, detail=None)


# ---------------------------------------------------------------------------
# Search / lookup / music endpoints
# ---------------------------------------------------------------------------

SearchType = Literal["movie", "tv"]
SearchProvider = Literal["tmdb", "omdb"]


def _to_candidate(r: MetadataResult) -> MetadataCandidate:
    payload = r.payload or {}
    provider_id = payload.get("id") or payload.get("imdbID")
    return MetadataCandidate(
        title=r.title,
        year=r.year,
        kind=r.kind,
        poster_url=extract_poster_url(r),
        provider_id=str(provider_id) if provider_id is not None else None,
    )


@router.get("/search", response_model=MetadataSearchResponse)
async def search_metadata(
    request: Request,
    title: str,
    type: SearchType = "movie",
    provider: SearchProvider = "tmdb",
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> MetadataSearchResponse:
    cfg = (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="config not initialised")
    http: httpx.AsyncClient = request.app.state.http
    key = (cfg.tmdb_api_key if provider == "tmdb" else cfg.omdb_api_key) or ""
    if not key.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"no {provider} key configured")
    try:
        if provider == "tmdb":
            client = TMDBClient(key, http)
            results = await (client.search_movie_candidates(title) if type == "movie" else client.search_tv_candidates(title))
        else:
            results = await OMDBClient(key, http).search_candidates(title, kind=type)
    except (MetaLookupError, LookupTimeout) as exc:
        return MetadataSearchResponse(candidates=[], detail=str(exc))
    except httpx.HTTPError as exc:
        return MetadataSearchResponse(candidates=[], detail=f"{provider} unavailable: {exc}")
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="exactly one of imdb_id or crc64 is required",
        )
    cfg = (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="config not initialised")
    http: httpx.AsyncClient = request.app.state.http
    if imdb_id is not None:
        key = (cfg.omdb_api_key or "").strip()
        if not key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no omdb key configured")
    try:
        if imdb_id is not None:
            result = await OMDBClient(key, http).lookup_by_imdb_id(imdb_id)  # type: ignore[possibly-undefined]
        else:
            result = await ArmServerClient(http).lookup_by_crc64(crc64)  # type: ignore[arg-type]
    except (MetaLookupError, LookupTimeout) as exc:
        return MetadataSearchResponse(candidates=[], detail=str(exc))
    except httpx.HTTPError as exc:
        return MetadataSearchResponse(candidates=[], detail=f"lookup unavailable: {exc}")
    return MetadataSearchResponse(candidates=[_to_candidate(result)])


@router.get("/music/search", response_model=MetadataSearchResponse)
async def search_music(
    request: Request,
    query: str,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> MetadataSearchResponse:
    cfg = (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    ua = (cfg.musicbrainz_user_agent if cfg else None) or "armv3"
    http: httpx.AsyncClient = request.app.state.http
    try:
        results = await MusicBrainzClient(ua, http).search_releases(query)
    except (MetaLookupError, LookupTimeout) as exc:
        return MetadataSearchResponse(candidates=[], detail=str(exc))
    except httpx.HTTPError as exc:
        return MetadataSearchResponse(candidates=[], detail=f"musicbrainz unavailable: {exc}")
    return MetadataSearchResponse(candidates=[_to_candidate(r) for r in results])
