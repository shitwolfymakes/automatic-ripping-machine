"""Image proxy with disk-backed caching."""

from __future__ import annotations

import time
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response

from arm_backend import image_cache
from arm_backend.auth import require_jwt
from arm_backend.config import settings
from arm_common import User

_NEGATIVE_CACHE: dict[str, float] = {}
_NEGATIVE_TTL_SECONDS = 3600
_MAX_FETCH_BYTES = 2 * 1024 * 1024  # 2 MB — matches the cache cap; rejects oversized at fetch time

router = APIRouter(prefix="/api", tags=["images"])

_SAFE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
}

_ALLOWED_IMAGE_HOSTS = {
    "m.media-amazon.com",
    "image.tmdb.org",
    "images-na.ssl-images-amazon.com",
    "coverartarchive.org",
    "ia.media-imdb.com",
}


def _allowed_image_hosts() -> frozenset[str]:
    """Built-in allowlist plus any operator-added ARM_EXTRA_IMAGE_HOSTS.

    Additive only — extras never remove a built-in (SSRF guard property)."""
    return frozenset(_ALLOWED_IMAGE_HOSTS) | frozenset(settings.ARM_EXTRA_IMAGE_HOSTS)


def _not_found(detail: str) -> Response:
    """Return a cacheable 404 so the browser stops re-requesting missing images."""
    return JSONResponse(
        {"detail": detail},
        status_code=404,
        headers={"Cache-Control": "public, max-age=3600"},
    )


# Intentionally unauthenticated: hit via <img src> (no bearer header possible).
# The host allowlist + size cap + scheme guard are the security boundary.
@router.get("/images/proxy")
async def proxy_image(url: str = Query(..., description="Image URL to proxy")) -> Response:
    """Proxy and cache external images to avoid browser ORB/CORS issues."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return _not_found("Only HTTP(S) URLs are allowed")
    if parsed.hostname not in _allowed_image_hosts():
        return _not_found("Image host not allowed")

    safe_url = parsed.geturl()

    cached = image_cache.retrieve(safe_url)
    if cached is not None:
        content, content_type = cached
        safe_type = content_type if content_type in _SAFE_CONTENT_TYPES else "application/octet-stream"
        return Response(content=content, media_type=safe_type, headers={"Cache-Control": "public, max-age=604800"})

    now = time.time()
    neg_expiry = _NEGATIVE_CACHE.get(safe_url)
    if neg_expiry is not None and neg_expiry > now:
        return _not_found("Image unavailable")

    try:
        # NOSONAR — host allowlisted + redirects disabled (no SSRF via redirect)
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            async with client.stream("GET", safe_url) as resp:
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "image/jpeg")
                safe_type = content_type if content_type in _SAFE_CONTENT_TYPES else "image/jpeg"
                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > _MAX_FETCH_BYTES:
                        _NEGATIVE_CACHE[safe_url] = now + _NEGATIVE_TTL_SECONDS
                        return _not_found("Image too large")
                    chunks.append(chunk)
                content = b"".join(chunks)
            image_cache.store(safe_url, content, safe_type)
            _NEGATIVE_CACHE.pop(safe_url, None)
            return Response(content=content, media_type=safe_type, headers={"Cache-Control": "public, max-age=604800"})
    except httpx.HTTPError:
        _NEGATIVE_CACHE[safe_url] = now + _NEGATIVE_TTL_SECONDS
        return _not_found("Failed to fetch image")


@router.get("/images/cache")
async def image_cache_stats(_: User = Depends(require_jwt)) -> dict[str, object]:
    """Image-cache statistics (count, size)."""
    return image_cache.stats()


@router.post("/images/cache/clear")
async def image_cache_clear(_: User = Depends(require_jwt)) -> dict[str, object]:
    """Clear the image cache. Returns {success, cleared, freed_bytes}."""
    return image_cache.clear()
