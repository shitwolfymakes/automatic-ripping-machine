"""The ids and identity a provider hit contributes to a job's metadata."""

from datetime import datetime
from typing import Any

from arm_backend.metadata.base import MetadataResult
from arm_common.schemas import ExternalIds, JobIdentity, MusicMeta


def first_str(*candidates: Any) -> str | None:
    for c in candidates:
        if isinstance(c, str) and c and c != "N/A":
            return c
        if isinstance(c, int):
            return str(c)
    return None


def external_ids_of(result: MetadataResult) -> ExternalIds:
    """Every id a provider hit carries, plus the kind of its TMDb id.

    The single derivation used by identify (`metadata_with_identity`) and
    the title-search candidates, so both store the same ids."""
    payload = result.payload or {}
    provider = result.provider or "unknown"
    tmdb = first_str(payload.get("tmdb_id"), payload.get("id") if provider == "tmdb" else None)
    return ExternalIds(
        imdb=first_str(payload.get("imdb_id"), payload.get("imdbID")),
        tmdb=tmdb,
        tvdb=first_str(payload.get("tvdb_id"), payload.get("id") if provider == "tvdb" else None),
        tvmaze=first_str(payload.get("tvmaze_id"), payload.get("id") if provider == "tvmaze" else None),
        musicbrainz_release=first_str(payload.get("id") if provider == "musicbrainz" else None),
        tmdb_kind=result.kind if tmdb and result.kind in ("movie", "tv") else None,
    )


def metadata_with_identity(
    metadata_json: dict[str, Any] | None,
    result: MetadataResult,
    *,
    identified_at: datetime,
) -> dict[str, Any]:
    """Fold a provider hit into the job's metadata bag.

    The raw payload is
    filed under `provider_raw[<provider>]`, the conclusions land in the
    typed `identity` section, and a music hit fills `music`. Nothing from a
    provider reaches the top level, so re-identifying with a different
    provider can no longer leave contradictory keys behind.
    """
    payload = result.payload or {}
    provider = result.provider or "unknown"
    external = external_ids_of(result)
    identity = JobIdentity(
        provider=provider,
        external_ids=external,
        overview=first_str(payload.get("overview"), payload.get("Plot")),
        identified_at=identified_at,
    )
    md = dict(metadata_json or {})
    md["identity"] = identity.model_dump(mode="json", exclude_none=True)
    md["provider_raw"] = {**(md.get("provider_raw") or {}), provider: payload}
    if result.kind == "music":
        music = MusicMeta(
            artist=first_str(payload.get("artist")),
            album=first_str(payload.get("album")),
            tracks=payload.get("tracks") or [],
        )
        md["music"] = music.model_dump(mode="json", exclude_none=True)
    return md
