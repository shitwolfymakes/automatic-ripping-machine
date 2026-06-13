"""Metadata API-key tester. Validates omdb/tmdb/tvdb keys against the upstream
service; makemkv is a structural/presence check only (the ripper owns the
update-key script, so true validity is confirmed at rip time). Ports neu's
GET /api/v1/metadata/test-key."""

import logging
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_backend.metadata.base import LookupError as MetaLookupError
from arm_backend.metadata.tvdb import TVDBClient
from arm_backend.seeders import CONFIG_SINGLETON_ID
from arm_common import Config, User
from arm_common.schemas import MetadataKeyTestResponse, MetadataProvider

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
