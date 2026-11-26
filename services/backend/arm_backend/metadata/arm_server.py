"""ARM community server (1337server) lookup by DVD CRC64.

Free, community-maintained crc64 → title database. Hits a single endpoint:
  https://1337server.pythonanywhere.com/api/v1/?mode=s&crc64={crc64}

When matched, the API returns a JSON envelope with title / year / imdb_id /
video_type / poster_img — used as the *first-class* lookup for DVDs since
the fingerprint is unique to the disc (no false fuzzy-title matches like
"Frozen" hitting the wrong release).

No API key needed. We send a User-Agent so the maintainer can attribute
traffic and shape rate limits.
"""

import logging
from typing import Any, Literal

import httpx

from arm_backend.config import settings
from arm_backend.metadata.base import LookupError, LookupTimeout, MetadataResult
from arm_backend.metadata.years import year_from_any

logger = logging.getLogger("arm_backend.metadata.arm_server")


def _base_url() -> str:
    return settings.ARM_ARMSERVER_BASE_URL


_USER_AGENT = "automatic-ripping-machine/v3"


def _top_result(body: dict[str, Any]) -> dict[str, Any]:
    """Return the first (canonical) result of the envelope, or raise LookupError."""
    results = body.get("results") or {}
    # 1337server keys results numerically as strings ("0", "1", …). Only the first entry is the canonical match.
    top = results.get("0") if isinstance(results, dict) else None
    if not isinstance(top, dict):
        raise LookupError("arm_server response missing results.0")
    return top


def _kind_of(top: dict[str, Any]) -> Literal["movie", "tv", "music"]:
    """Map the result's `video_type` to a metadata kind."""
    # 1337server's `video_type` distinguishes movie / tv but we only carry
    # `kind` ∈ {movie, tv, music} — anything not "tv" maps to movie.
    return "tv" if str(top.get("video_type", "")).lower() == "tv" else "movie"


def _with_poster(top: dict[str, Any]) -> dict[str, Any]:
    """Copy the result into a payload, adding a synthetic OMDB-shaped Poster URL."""
    # Inject a synthetic OMDB-shaped Poster URL so the existing
    # `extract_poster_url` helper picks it up without special-casing.
    poster = top.get("poster_img")
    payload: dict[str, Any] = dict(top)
    if isinstance(poster, str) and poster.startswith("http"):
        payload.setdefault("Poster", poster)
    return payload


class ArmServerClient:
    """Look up a DVD title by its pydvdid CRC64."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def lookup_by_crc64(self, crc64: str) -> MetadataResult:
        # 1337server is keyed on the plain 16-hex CRC64 (`format(crc, "016x")`,
        # the form `pydvdid` produces). pydvdid-m stringifies
        # as "<high8>|<low8>"; the ripper already strips the pipe at the source
        # (disc_probe), but normalise here too so a stray separator from any
        # caller can't silently miss every disc on format alone.
        crc64 = crc64.replace("|", "")
        body = await self._fetch_envelope(crc64)
        top = _top_result(body)

        title_val = top.get("title")
        year_raw = top.get("year")
        if not isinstance(title_val, str) or not title_val:
            raise LookupError("arm_server result missing title")

        year_val = year_from_any(year_raw)

        return MetadataResult(title=title_val, year=year_val, kind=_kind_of(top), payload=_with_poster(top))

    async def _fetch_envelope(self, crc64: str) -> dict[str, Any]:
        """GET the 1337server envelope for `crc64`.

        Raises LookupTimeout on a timeout, and LookupError on a transport or status failure or a miss.
        """
        try:
            r = await self._http.get(
                _base_url(),
                params={"mode": "s", "crc64": crc64},
                headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            )
        except httpx.TimeoutException as e:
            raise LookupTimeout("arm_server timeout") from e
        except httpx.HTTPError as e:
            raise LookupError(f"arm_server transport error: {e}") from e

        if r.status_code >= 500:
            raise LookupError(f"arm_server 5xx status={r.status_code}")
        if r.status_code != 200:
            raise LookupError(f"arm_server status={r.status_code}")

        body: dict[str, Any] = r.json()
        if not body.get("success"):
            raise LookupError(f"arm_server miss: {body.get('error', 'no match')}")
        return body
