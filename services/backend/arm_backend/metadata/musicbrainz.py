import asyncio
import logging
import time
from typing import Any

import httpx

from arm_backend.metadata.base import LookupError, LookupTimeout, MetadataResult

logger = logging.getLogger("arm_backend.metadata.musicbrainz")

_BASE_URL = "https://musicbrainz.org/ws/2"
_MIN_INTERVAL_SECONDS = 1.0

_lock = asyncio.Lock()
_last_call_at: float = 0.0


async def _rate_limit() -> None:
    """Hold the global MB semaphore + enforce 1 req/s minimum spacing.

    MusicBrainz blocks clients that exceed 1 req/s; the lock + min-interval
    guard keeps us compliant even if multiple identify handlers hit the
    dispatcher concurrently.
    """
    global _last_call_at
    async with _lock:
        delta = time.monotonic() - _last_call_at
        if delta < _MIN_INTERVAL_SECONDS:
            await asyncio.sleep(_MIN_INTERVAL_SECONDS - delta)
        _last_call_at = time.monotonic()


class MusicBrainzClient:
    def __init__(self, user_agent: str, http: httpx.AsyncClient) -> None:
        if not user_agent:
            raise ValueError("MusicBrainz requires a non-empty user-agent string")
        self._user_agent = user_agent
        self._http = http

    async def _get(self, path: str, params: dict[str, Any], *, not_found_detail: str | None = None) -> dict[str, Any]:
        """Rate-limit, execute GET, handle transport errors and bad statuses.

        Enforces the 1 req/s rate limit, sets the required User-Agent header,
        and converts transport failures and non-200 HTTP statuses into the
        appropriate LookupError / LookupTimeout. Returns the parsed JSON body.

        `not_found_detail`, when set, gives a 404 a caller-specific message
        (e.g. "disc_id not found" — an expected miss, not a generic HTTP error).
        """
        await _rate_limit()

        try:
            r = await self._http.get(
                f"{_BASE_URL}{path}",
                params=params,
                headers={"User-Agent": self._user_agent, "Accept": "application/json"},
            )
        except httpx.TimeoutException as e:
            raise LookupTimeout("musicbrainz timeout") from e
        except httpx.HTTPError as e:
            raise LookupError(f"musicbrainz transport error: {e}") from e

        if not_found_detail is not None and r.status_code == 404:
            raise LookupError(not_found_detail)
        if r.status_code >= 500:
            raise LookupError(f"musicbrainz 5xx status={r.status_code}")
        if r.status_code != 200:
            raise LookupError(f"musicbrainz status={r.status_code}")

        return r.json()  # type: ignore[no-any-return]

    async def lookup_disc_id(self, disc_id: str) -> MetadataResult:
        body = await self._get(
            f"/discid/{disc_id}",
            params={"inc": "artists+recordings", "fmt": "json"},
            not_found_detail="musicbrainz disc_id not found",
        )

        releases = body.get("releases") or []
        if not releases:
            raise LookupError("musicbrainz disc_id has no releases")

        top = releases[0]
        title_val = top.get("title")
        date = top.get("date") or ""
        year_val = int(date[:4]) if date[:4].isdigit() else None
        if not title_val:
            raise LookupError("musicbrainz top release missing title")

        # Parse fields the path-template tokens look for at the top level of
        # job.metadata_json. The raw release dict is spread in alongside so
        # extract_poster_url() can still derive the Cover Art Archive URL
        # from release["id"], and downstream debugging has the full payload.
        artist = _join_artist_credit(top.get("artist-credit") or [])
        medium = _pick_medium_for_disc(top.get("media") or [], disc_id)
        tracks = _extract_tracks(medium)

        payload: dict[str, Any] = {
            "artist": artist,
            "album": title_val,
            "tracks": tracks,
            **top,
        }

        return MetadataResult(title=title_val, year=year_val, kind="music", payload=payload)

    async def search_releases(self, query: str, limit: int = 10) -> list[MetadataResult]:
        """Lucene release search for interactive lookup. Returns up to `limit`."""
        body = await self._get(
            "/release",
            params={"query": query, "fmt": "json", "limit": limit},
        )

        results: list[MetadataResult] = []
        for rel in (body.get("releases") or [])[:limit]:
            title = rel.get("title")
            if not title:
                continue
            date = rel.get("date") or ""
            year: int | None = int(date[:4]) if date[:4].isdigit() else None
            artist = _join_artist_credit(rel.get("artist-credit") or [])
            payload: dict[str, Any] = {"artist": artist, "album": title, **rel}
            results.append(MetadataResult(title=title, year=year, kind="music", payload=payload))

        return results


def _join_artist_credit(credit: list[dict[str, Any]]) -> str:
    """Render a MusicBrainz `artist-credit` list as a single display string.

    Each entry has `name` and an optional `joinphrase` that follows it (e.g.
    `" & "`, `" feat. "`). MB places the join AFTER the entry it follows; the
    last entry's joinphrase is usually empty.
    """
    parts: list[str] = []
    for entry in credit:
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        parts.append(name)
        join = entry.get("joinphrase")
        if isinstance(join, str) and join:
            parts.append(join)
    return "".join(parts).strip()


def _pick_medium_for_disc(media: list[dict[str, Any]], disc_id: str) -> dict[str, Any] | None:
    """Pick the medium whose `discs[].id` matches `disc_id`.

    For multi-disc releases (e.g. a 2-CD album), MB returns each medium
    separately and tags each with its own disc-id list. Matching by disc-id
    is the only way to know whether we're looking at Disc 1 or Disc 2.
    Falls back to `media[0]` when no disc-id match is found — single-disc
    releases sometimes omit the `discs[]` array entirely.
    """
    for medium in media:
        for disc in medium.get("discs") or []:
            if isinstance(disc, dict) and disc.get("id") == disc_id:
                return medium
    if media:
        return media[0]
    return None


def _extract_tracks(medium: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Build the `metadata_json["tracks"]` array consumed by `_build_track_ctx`.

    Each entry is `{"title": str, "position": int}`. Position is parsed from
    the string MB returns; a non-integer position falls through with the raw
    string preserved.
    """
    if medium is None:
        return []
    out: list[dict[str, Any]] = []
    for raw in medium.get("tracks") or []:
        title = raw.get("title")
        if not isinstance(title, str):
            continue
        entry: dict[str, Any] = {"title": title}
        position = raw.get("position")
        if isinstance(position, str) and position.isdigit():
            entry["position"] = int(position)
        elif isinstance(position, int):
            entry["position"] = position
        out.append(entry)
    return out
