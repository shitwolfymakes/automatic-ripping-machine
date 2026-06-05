from dataclasses import dataclass, field
from typing import Any, Literal

# TMDB serves posters from a CDN; `w500` (500px-wide) is the v2 default
# and renders fine for thumbnail and detail-card use. Full hashed path is
# `{base}{poster_path}` where poster_path is the leading-slash fragment
# returned in the API payload.
TMDB_POSTER_BASE_URL = "https://image.tmdb.org/t/p/w500"
# Cover Art Archive serves the front cover at this canonical path. May 404
# for releases with no uploaded art; the UI handles broken images via
# onerror fallback rather than a pre-flight check (avoids a request-per-rip
# even when no one is looking at the dashboard).
COVERART_FRONT_URL_TEMPLATE = "https://coverartarchive.org/release/{mbid}/front"


@dataclass(slots=True)
class MetadataResult:
    title: str
    year: int | None
    kind: Literal["movie", "tv", "music"]
    payload: dict[str, Any] = field(default_factory=dict)


def extract_poster_url(result: MetadataResult) -> str | None:
    """Pull a renderable poster URL out of a provider hit.

    Order: TMDB poster_path > OMDB Poster (full URL) > Cover Art Archive
    derived from MusicBrainz release id. Returns None if none apply or if
    the value isn't a useful absolute URL.
    """
    payload = result.payload or {}

    # TMDB returns a leading-slash fragment, e.g. "/abc123.jpg".
    poster_path = payload.get("poster_path")
    if isinstance(poster_path, str) and poster_path.startswith("/"):
        return f"{TMDB_POSTER_BASE_URL}{poster_path}"

    # OMDB returns a full URL or the literal "N/A" when missing.
    omdb_poster = payload.get("Poster")
    if isinstance(omdb_poster, str) and omdb_poster.startswith("http") and omdb_poster != "N/A":
        return omdb_poster

    # MusicBrainz: derive from the release MBID. The CAA endpoint may 404
    # for releases with no uploaded front cover; UI handles fallback.
    if result.kind == "music":
        release_id = payload.get("id")
        if isinstance(release_id, str) and release_id:
            return COVERART_FRONT_URL_TEMPLATE.format(mbid=release_id)

    return None


class LookupError(Exception):
    """Provider returned no usable result, or auth/transport failed."""


class LookupTimeout(LookupError):
    """Provider exceeded its per-call timeout budget."""
