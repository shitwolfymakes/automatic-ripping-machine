from dataclasses import dataclass, field
from typing import Any, Literal

# TMDB serves posters from a CDN; `w500` (500px-wide) is the v2 default
# and renders fine for thumbnail and detail-card use. Full hashed path is
# `{base}{poster_path}` where poster_path is the leading-slash fragment
# returned in the API payload.
TMDB_POSTER_BASE_URL = "https://image.tmdb.org/t/p/w500"
# Cover Art Archive front-cover endpoints (sized `front-250` variant, matching
# neu). Both 404 for entities with no uploaded art.
#
# Cover-art strategy (the canonical MusicBrainz Picard model): use the
# per-RELEASE cover as the primary so distinct pressings show distinct covers,
# and carry the album's release-GROUP id as a `fallback_group` query param so
# the image proxy can fall back to the group cover when the specific release
# has no art. Per-release art keeps covers distinct; the group rescues the
# (common) case of an art-less regional pressing.
COVERART_RELEASE_FRONT_URL_TEMPLATE = "https://coverartarchive.org/release/{mbid}/front-250"
COVERART_GROUP_FRONT_URL_TEMPLATE = "https://coverartarchive.org/release-group/{mbid}/front-250"


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

    # MusicBrainz: per-release front cover as the primary, with the album's
    # release-group id appended as `fallback_group` (the image proxy falls back
    # to the group cover on a release-level 404). Both endpoints may 404; the UI
    # shows its placeholder only when neither has art.
    if result.kind == "music":
        release_id = payload.get("id")
        if not (isinstance(release_id, str) and release_id):
            return None
        url = COVERART_RELEASE_FRONT_URL_TEMPLATE.format(mbid=release_id)
        group = payload.get("release-group")
        if isinstance(group, dict):
            group_id = group.get("id")
            if isinstance(group_id, str) and group_id:
                url = f"{url}?fallback_group={group_id}"
        return url

    return None


class LookupError(Exception):
    """Provider returned no usable result, or auth/transport failed."""


class LookupTimeout(LookupError):
    """Provider exceeded its per-call timeout budget."""
