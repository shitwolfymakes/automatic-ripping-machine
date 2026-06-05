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

from arm_backend.metadata.base import LookupError, LookupTimeout, MetadataResult

logger = logging.getLogger("arm_backend.metadata.arm_server")

_BASE_URL = "https://1337server.pythonanywhere.com/api/v1/"
_USER_AGENT = "automatic-ripping-machine/v3"


class ArmServerClient:
    """Look up a DVD title by its pydvdid CRC64."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def lookup_by_crc64(self, crc64: str) -> MetadataResult:
        try:
            r = await self._http.get(
                _BASE_URL,
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

        results = body.get("results") or {}
        # 1337server keys results numerically as strings ("0", "1", …) — same
        # shape v2 reads. Only the first entry is the canonical match.
        top = results.get("0") if isinstance(results, dict) else None
        if not isinstance(top, dict):
            raise LookupError("arm_server response missing results.0")

        title_val = top.get("title")
        year_raw = top.get("year")
        if not isinstance(title_val, str) or not title_val:
            raise LookupError("arm_server result missing title")

        year_val: int | None = None
        if isinstance(year_raw, int):
            year_val = year_raw
        elif isinstance(year_raw, str) and year_raw[:4].isdigit():
            year_val = int(year_raw[:4])

        # 1337server's `video_type` distinguishes movie / tv but we only carry
        # `kind` ∈ {movie, tv, music} — anything not "tv" maps to movie.
        kind: Literal["movie", "tv", "music"] = "tv" if str(top.get("video_type", "")).lower() == "tv" else "movie"

        # Inject a synthetic OMDB-shaped Poster URL so the existing
        # `extract_poster_url` helper picks it up without special-casing.
        poster = top.get("poster_img")
        payload: dict[str, Any] = dict(top)
        if isinstance(poster, str) and poster.startswith("http"):
            payload.setdefault("Poster", poster)

        return MetadataResult(title=title_val, year=year_val, kind=kind, payload=payload)
