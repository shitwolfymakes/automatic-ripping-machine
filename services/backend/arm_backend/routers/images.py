"""Image proxy with disk-backed caching."""

from __future__ import annotations

import logging
import time
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response

from arm_backend import image_cache
from arm_backend.auth import require_jwt
from arm_backend.config import settings
from arm_backend.metadata.base import COVERART_GROUP_FRONT_URL_TEMPLATE
from arm_common import User

logger = logging.getLogger("arm_backend.routers.images")

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

# Suffix-matched hosts: a request/redirect host is allowed when it equals the
# entry or ends with ".<entry>". Cover Art Archive 307s to archive.org, which
# 302s to a per-request data-node subdomain (e.g. dn710304.ca.archive.org), so
# the final host can't be exact-listed — match the apex + any subdomain.
_ALLOWED_IMAGE_HOST_SUFFIXES = {
    "archive.org",
}

# Cap redirect hops so a redirect loop can't hang or recurse.
_MAX_REDIRECTS = 5


def _allowed_image_hosts() -> frozenset[str]:
    """Built-in allowlist plus any operator-added ARM_EXTRA_IMAGE_HOSTS.

    Additive only — extras never remove a built-in (SSRF guard property)."""
    return frozenset(_ALLOWED_IMAGE_HOSTS) | frozenset(settings.ARM_EXTRA_IMAGE_HOSTS)


def _host_allowed(hostname: str | None) -> bool:
    """True if the host is exact-allowlisted or a subdomain of a suffix entry.

    The SSRF boundary: applied to the initial URL AND re-checked on every
    redirect hop, so a redirect can never escape to a non-allowlisted host."""
    if not hostname:
        return False
    if hostname in _allowed_image_hosts():
        return True
    return any(hostname == suffix or hostname.endswith(f".{suffix}") for suffix in _ALLOWED_IMAGE_HOST_SUFFIXES)


def _not_found(detail: str) -> Response:
    """Return a cacheable 404 so the browser stops re-requesting missing images."""
    return JSONResponse(
        {"detail": detail},
        status_code=404,
        headers={"Cache-Control": "public, max-age=3600"},
    )


def _split_fallback_group(url: str) -> tuple[str, str | None]:
    """Pull the optional `fallback_group` param out of a CAA cover URL.

    The backend appends `?fallback_group={rg}` to per-release cover URLs so the
    proxy can fall back to the album's release-group cover on a release-level
    404 (the canonical Picard model). Return (url_without_fallback_group,
    release_group_id_or_None). The stripped URL is what we actually fetch and
    cache-key on, keeping the upstream request and cache clean."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    fallback_values = qs.pop("fallback_group", None)
    fallback_group = fallback_values[0] if fallback_values else None
    clean_query = urlencode(qs, doseq=True)
    clean_url = urlunparse(parsed._replace(query=clean_query))
    return clean_url, (fallback_group or None)


class _ImageTooLarge(Exception):
    """Raised inside _fetch_image when the body exceeds the size cap."""


async def _fetch_image(client: httpx.AsyncClient, start_url: str) -> tuple[bytes, str] | None:
    """Fetch one image, following CAA redirects manually with a per-hop SSRF guard.

    Returns (content, safe_content_type) on success, or None when the chain
    terminates in a 404 (CAA returns 404 for entities with no art) or exhausts
    the redirect budget — both let the caller try a fallback. Raises
    httpx.HTTPError for transport/other-status failures and _ImageTooLarge when
    the body exceeds the cap; the caller maps those to a 404 response."""
    fetch_url = start_url
    for _ in range(_MAX_REDIRECTS + 1):
        async with client.stream("GET", fetch_url) as resp:
            if resp.is_redirect:
                location = resp.headers.get("location")
                if not location:
                    return None
                # Resolve relative redirects against the current URL, then
                # re-validate the destination host (SSRF guard per hop).
                next_url = str(httpx.URL(fetch_url).join(location))
                nxt = urlparse(next_url)
                if nxt.scheme not in ("http", "https") or not _host_allowed(nxt.hostname):
                    return None
                fetch_url = next_url
                continue
            # A 404 means "no art for this entity" — surface as None so the
            # caller can try the release-group fallback (other statuses raise).
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "image/jpeg")
            safe_type = content_type if content_type in _SAFE_CONTENT_TYPES else "image/jpeg"
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > _MAX_FETCH_BYTES:
                    raise _ImageTooLarge
                chunks.append(chunk)
            return b"".join(chunks), safe_type
    # Exhausted the hop budget without reaching a terminal response.
    return None


# Intentionally unauthenticated: hit via <img src> (no bearer header possible).
# The host allowlist + size cap + scheme guard are the security boundary.
@router.get("/images/proxy")
async def proxy_image(url: str = Query(..., description="Image URL to proxy")) -> Response:
    """Proxy and cache external images to avoid browser ORB/CORS issues."""
    safe_url, fallback_group = _split_fallback_group(url)
    parsed = urlparse(safe_url)
    if parsed.scheme not in ("http", "https"):
        return _not_found("Only HTTP(S) URLs are allowed")
    if not _host_allowed(parsed.hostname):
        return _not_found("Image host not allowed")

    # The cache is an optimization, never a hard dependency: a broken or
    # unwritable cache dir must degrade to a live fetch, not fail the request.
    try:
        cached = image_cache.retrieve(safe_url)
    except OSError:
        logger.warning("image cache read failed; serving uncached", exc_info=True)
        cached = None
    if cached is not None:
        content, content_type = cached
        safe_type = content_type if content_type in _SAFE_CONTENT_TYPES else "application/octet-stream"
        return Response(content=content, media_type=safe_type, headers={"Cache-Control": "public, max-age=604800"})

    now = time.time()
    neg_expiry = _NEGATIVE_CACHE.get(safe_url)
    if neg_expiry is not None and neg_expiry > now:
        return _not_found("Image unavailable")

    try:
        # Redirects are followed MANUALLY so every hop's host is re-validated
        # against the allowlist (no SSRF via redirect) — Cover Art Archive 307s
        # to archive.org then 302s to a per-request data-node subdomain.
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            fetched = await _fetch_image(client, safe_url)
            # On a release-level 404, fall back to the album's release-group
            # cover (Picard model) — re-validating the constructed host.
            if fetched is None and fallback_group:
                group_url = COVERART_GROUP_FRONT_URL_TEMPLATE.format(mbid=fallback_group)
                gp = urlparse(group_url)
                if gp.scheme in ("http", "https") and _host_allowed(gp.hostname):
                    fetched = await _fetch_image(client, group_url)
    except _ImageTooLarge:
        _NEGATIVE_CACHE[safe_url] = now + _NEGATIVE_TTL_SECONDS
        return _not_found("Image too large")
    except httpx.HTTPError:
        _NEGATIVE_CACHE[safe_url] = now + _NEGATIVE_TTL_SECONDS
        return _not_found("Failed to fetch image")

    if fetched is None:
        _NEGATIVE_CACHE[safe_url] = now + _NEGATIVE_TTL_SECONDS
        return _not_found("Image unavailable")

    content, safe_type = fetched
    try:
        image_cache.store(safe_url, content, safe_type)
    except OSError:
        logger.warning("image cache write failed; serving uncached", exc_info=True)
    _NEGATIVE_CACHE.pop(safe_url, None)
    return Response(content=content, media_type=safe_type, headers={"Cache-Control": "public, max-age=604800"})


@router.get("/images/cache")
async def image_cache_stats(_: User = Depends(require_jwt)) -> dict[str, object]:
    """Image-cache statistics (count, size)."""
    return image_cache.stats()


@router.post("/images/cache/clear")
async def image_cache_clear(_: User = Depends(require_jwt)) -> dict[str, object]:
    """Clear the image cache. Returns {success, cleared, freed_bytes}."""
    return image_cache.clear()
