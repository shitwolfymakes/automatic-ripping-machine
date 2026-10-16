import asyncio
import logging
import math
import time
from typing import Any

import httpx

from arm_backend.config import settings
from arm_backend.metadata.base import LookupError, LookupTimeout, MetadataResult

logger = logging.getLogger("arm_backend.metadata.musicbrainz")


def _base_url() -> str:
    return settings.ARM_MUSICBRAINZ_BASE_URL


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


_DISC_NOT_FOUND = "musicbrainz disc_id not found"
_DISC_NO_RELEASES = "musicbrainz disc_id has no releases"
TOC_NOT_FOUND = "musicbrainz toc not found"
_TOC_CANDIDATES = 5


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
                f"{_base_url()}{path}",
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

    async def lookup_disc_id(self, disc_id: str, toc: str | None = None) -> MetadataResult:
        """Exact disc-ID lookup. When that disc isn't listed (404 or no
        releases) and `toc` is given, fall back to MusicBrainz's fuzzy TOC
        match (track count and lengths): other pressings of a listed album."""
        inc = "artists+recordings+release-groups"
        try:
            body = await self._get(
                f"/discid/{disc_id}",
                # release-groups: so extract_poster_url can prefer the (more often
                # populated) release-group cover over the specific release's.
                params={"inc": inc, "fmt": "json"},
                not_found_detail=_DISC_NOT_FOUND,
            )
            releases = body.get("releases") or []
            if not releases:
                raise LookupError(_DISC_NO_RELEASES)
        except LookupError as e:
            if not toc or str(e) not in (_DISC_NOT_FOUND, _DISC_NO_RELEASES):
                raise
            return await self._lookup_toc(toc, inc)
        return self._project_disc(releases, disc_id, None)

    async def _lookup_toc(self, toc: str, inc: str) -> MetadataResult:
        body = await self._get(
            "/discid/-",
            params={"toc": "+".join(toc.split()), "cdstubs": "no", "inc": inc, "fmt": "json"},
            not_found_detail=TOC_NOT_FOUND,
        )
        releases = body.get("releases") or []
        if not releases:
            raise LookupError(TOC_NOT_FOUND)
        # Closest fit first (best medium per release); a stable sort keeps
        # MusicBrainz's order among equal fits.
        lengths = _toc_track_lengths(toc)
        if lengths is not None:
            releases = sorted(releases, key=lambda r: _best_toc_distance(r.get("media") or [], lengths))
        return self._project_disc(releases, None, toc)

    def _project_disc(self, releases: list[dict[str, Any]], disc_id: str | None, toc: str | None) -> MetadataResult:
        top = releases[0]
        title_val = top.get("title")
        year_val = _parse_year(top.get("date") or "")
        if not title_val:
            raise LookupError("musicbrainz top release missing title")

        # Parse fields the path-template tokens look for at the top level of
        # job.metadata_json. The raw release dict is spread in alongside so
        # extract_poster_url() can still derive the Cover Art Archive URL
        # from release["id"], and downstream debugging has the full payload.
        artist = _join_artist_credit(top.get("artist-credit") or [])
        if disc_id is not None:
            medium, disc_number = _pick_medium_for_disc(top.get("media") or [], disc_id)
        else:
            medium, disc_number = _pick_medium_for_toc(top.get("media") or [], toc)
        tracks = _extract_tracks(medium, disc_number)

        payload: dict[str, Any] = {
            "artist": artist,
            "album": title_val,
            "tracks": tracks,
            **top,
        }
        # The matched medium's position IS this disc's number — plumb it so
        # the {disc} naming token resolves at apply time (transcode_apply
        # reads job.disc_number and falls back to metadata_json["disc"]; without
        # this fallback the token validates at save yet fails every real music
        # apply of a job whose disc_number is unset).
        if medium is not None and medium.get("position"):
            payload["disc"] = medium["position"]

        if toc is not None:
            payload["toc_match"] = "fuzzy"
            if len(releases) > 1:
                payload["toc_candidates"] = [
                    {
                        "id": r.get("id"),
                        "title": r.get("title"),
                        "date": r.get("date"),
                        "artist": _join_artist_credit(r.get("artist-credit") or []),
                    }
                    for r in releases[:_TOC_CANDIDATES]
                ]

        return MetadataResult(title=title_val, year=year_val, kind="music", payload=payload)

    async def get_release(self, release_id: str) -> MetadataResult:
        """Fetch a single MusicBrainz release by MBID for interactive detail.

        Mirrors lookup_disc_id's projection (artist/album/tracks spread over the
        raw release dict) but keyed on a known release MBID instead of a disc-id
        lookup. A 404 (unknown MBID) surfaces as the not-found LookupError.
        """
        body = await self._get(
            f"/release/{release_id}",
            # release-groups: so extract_poster_url can prefer the (more often
            # populated) release-group cover over the specific release's.
            params={"inc": "artists+recordings+labels+release-groups", "fmt": "json"},
            not_found_detail="musicbrainz release not found",
        )
        title_val = body.get("title")
        if not title_val:
            raise LookupError("musicbrainz release missing title")
        year_val = _parse_year(body.get("date") or "")
        artist = _join_artist_credit(body.get("artist-credit") or [])
        media = body.get("media") or []
        tracks: list[dict[str, Any]] = []
        for i, medium in enumerate(media):
            tracks.extend(_extract_tracks(medium, i + 1))
        label_info = body.get("label-info") or []
        catalog_number = None
        if label_info and isinstance(label_info[0], dict):
            catalog_number = label_info[0].get("catalog-number")
        fmt = media[0].get("format") if media and isinstance(media[0], dict) else None
        payload: dict[str, Any] = {
            "artist": artist,
            "album": title_val,
            "tracks": tracks,
            "catalog_number": catalog_number,
            "format": fmt,
            "disc_count": len(media),
            "track_count": len(tracks),
            **body,
        }
        return MetadataResult(title=title_val, year=year_val, kind="music", payload=payload)

    async def search_releases(
        self,
        query: str,
        limit: int = 10,
        *,
        artist: str | None = None,
        track_count: int | None = None,
        release_type: str | None = None,
        format: str | None = None,
        country: str | None = None,
        status: str | None = None,
    ) -> list[MetadataResult]:
        """Lucene release search for interactive lookup. Returns up to `limit`.
        Each present filter is AND-ed into the Lucene query."""
        lucene = query
        if artist:
            lucene = f'{lucene} AND artist:"{_escape_lucene(artist)}"'
        if track_count is not None:
            lucene = f"{lucene} AND tracks:{track_count}"
        if release_type:
            lucene = f"{lucene} AND primarytype:{_escape_lucene(release_type)}"
        if format:
            lucene = f'{lucene} AND format:"{_escape_lucene(format)}"'
        if country:
            lucene = f"{lucene} AND country:{_escape_lucene(country)}"
        if status:
            lucene = f"{lucene} AND status:{_escape_lucene(status)}"
        body = await self._get(
            "/release",
            params={"query": lucene, "fmt": "json", "limit": limit},
        )
        results: list[MetadataResult] = []
        for rel in (body.get("releases") or [])[:limit]:
            title = rel.get("title")
            if not title:
                continue
            year = _parse_year(rel.get("date") or "")
            artist_name = _join_artist_credit(rel.get("artist-credit") or [])
            media = rel.get("media") or []
            fmt = media[0].get("format") if media and isinstance(media[0], dict) else None
            payload: dict[str, Any] = {"artist": artist_name, "album": title, "format": fmt, **rel}
            results.append(MetadataResult(title=title, year=year, kind="music", payload=payload))
        return results


def _parse_year(date: str) -> int | None:
    """Year from a MusicBrainz date string ("1973-03-01" -> 1973), or None."""
    return int(date[:4]) if date[:4].isdigit() else None


def _escape_lucene(term: str) -> str:
    """Escape Lucene double-quotes/backslashes so a quoted phrase term is safe."""
    return term.replace("\\", "\\\\").replace('"', '\\"')


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


def _pick_medium_for_disc(media: list[dict[str, Any]], disc_id: str) -> tuple[dict[str, Any] | None, int]:
    """Return (medium, 1-based disc_number) for the medium whose discs[].id matches
    disc_id; fall back to (media[0], 1). (None, 1) when media is empty."""
    for i, medium in enumerate(media):
        for disc in medium.get("discs") or []:
            if isinstance(disc, dict) and disc.get("id") == disc_id:
                return medium, i + 1
    if media:
        return media[0], 1
    return None, 1


def _toc_track_count(toc: str | None) -> int | None:
    """Track count of a libdiscid TOC string ("first last leadout offsets…")."""
    try:
        first, last = (int(x) for x in (toc or "").split()[:2])
    except ValueError:
        return None
    return last - first + 1


# CD sectors per second: libdiscid TOC offsets are sector addresses.
_SECTORS_PER_SECOND = 75
# Distance charged for a track whose MusicBrainz length is unknown, in seconds.
_MISSING_LENGTH_PENALTY_S = 3600.0


def _toc_track_lengths(toc: str | None) -> list[float] | None:
    """Per-track lengths in seconds from a TOC string, or None when malformed."""
    try:
        first, last, leadout, *offsets = (int(x) for x in (toc or "").split())
    except ValueError:
        return None
    if last < first or len(offsets) != last - first + 1:
        return None
    bounds = [*offsets, leadout]
    return [(bounds[i + 1] - bounds[i]) / _SECTORS_PER_SECOND for i in range(len(offsets))]


def _medium_track_count(medium: dict[str, Any]) -> int:
    count = medium.get("track-count")
    return count if isinstance(count, int) else len(medium.get("tracks") or [])


def _toc_distance(medium: dict[str, Any], lengths: list[float]) -> float:
    """Total |MusicBrainz length - TOC length| in seconds over the disc's
    tracks; a missing length (or track) costs a large flat penalty."""
    tracks = medium.get("tracks") or []
    total = 0.0
    for i, seconds in enumerate(lengths):
        ms = tracks[i].get("length") if i < len(tracks) else None
        total += abs(ms / 1000 - seconds) if isinstance(ms, (int, float)) else _MISSING_LENGTH_PENALTY_S
    return total


def _best_toc_distance(media: list[dict[str, Any]], lengths: list[float]) -> float:
    """Distance of a release's closest medium with the TOC's track count;
    infinity when none has it."""
    return min(
        (_toc_distance(m, lengths) for m in media if _medium_track_count(m) == len(lengths)),
        default=math.inf,
    )


def _pick_medium_for_toc(media: list[dict[str, Any]], toc: str | None) -> tuple[dict[str, Any] | None, int]:
    """Fuzzy hit: among the media with the TOC's track count, the one whose
    track lengths fit the TOC best (the first on a tie or when the lengths
    can't be read); else media[0]."""
    track_count = _toc_track_count(toc)
    lengths = _toc_track_lengths(toc)
    matching = [
        (i, m) for i, m in enumerate(media) if track_count is not None and _medium_track_count(m) == track_count
    ]
    if matching:
        if lengths is not None:
            i, medium = min(matching, key=lambda im: _toc_distance(im[1], lengths))
        else:
            i, medium = matching[0]
        return medium, i + 1
    if media:
        return media[0], 1
    return None, 1


def _extract_tracks(medium: dict[str, Any] | None, disc_number: int) -> list[dict[str, Any]]:
    """Build `metadata_json["tracks"]` entries for one medium (disc). Each entry
    is {title, position?, length_ms, disc_number}. `length` from MB is already ms."""
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
        length = raw.get("length")
        entry["length_ms"] = length if isinstance(length, int) else None
        entry["disc_number"] = disc_number
        out.append(entry)
    return out
