"""Typed core for `jobs.metadata_json` (gap analysis §3.4).

The bag holds four kinds of content, and this module gives each a home:

- `scan_result` — the full ScanResult dump from identify time (load-bearing:
  rip-start's track selection reads it). Already typed by `ScanResult`.
- `identity` — what identification concluded: which provider, the external
  ids, the synopsis. Written at identify; never merged from raw payloads.
- `music` / `thediscdb` — provider-shaped sections with real readers (the
  music naming tokens; the TheDiscDB track map).
- `flags` — booleans that steer behaviour (`unidentified` parks placeholder
  rips at ripped_awaiting_identify; `dispatch_timeout` is diagnostic).
- `provider_raw` — everything a provider returned, keyed by provider name.
  Data for the raw viewer and future backfills, never read for behaviour.
  Rows migrated from the old top-level merge keep theirs under `"legacy"`.

`extra="allow"` everywhere: the `pending_session_id` mirror that used to live
in this bag is gone (removed in the job-identity-columns branch; the UIs now
read the `pending_session_id` job column). `extra="allow"` is kept
deliberately for one more release as a grace period for rows written before
migration 0031, so a validate/dump round-trip on old data doesn't drop
whatever was there; tighten to `forbid` once those rows are confirmed gone.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from arm_common.schemas.ripper import ScanResult


class ExternalIds(BaseModel):
    model_config = ConfigDict(extra="allow")

    imdb: str | None = None
    tmdb: str | None = None
    tvdb: str | None = None
    musicbrainz_release: str | None = None


class JobIdentity(BaseModel):
    """What identification concluded. Title/year/media_type/poster live on
    the Job row itself — this records where they came from and the ids that
    let a UI link out or re-query."""

    model_config = ConfigDict(extra="allow")

    provider: str
    external_ids: ExternalIds = Field(default_factory=ExternalIds)
    overview: str | None = None
    identified_at: datetime | None = None


class MusicTrackMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str
    position: int | None = None
    length_ms: int | None = None
    disc_number: int | None = None


class MusicMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    artist: str | None = None
    album: str | None = None
    tracks: list[MusicTrackMeta] = Field(default_factory=list)


class JobFlags(BaseModel):
    model_config = ConfigDict(extra="allow")

    unidentified: bool = False
    dispatch_timeout: bool = False


class JobMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    scan_result: ScanResult | None = None
    identity: JobIdentity | None = None
    music: MusicMeta | None = None
    # Per-title map from the TheDiscDB snapshot match: dynamic source-ref
    # keys plus `matched_at` — left as a dict until it grows a reader that
    # needs more than `apply_map` does.
    thediscdb: dict[str, Any] | None = None
    flags: JobFlags = Field(default_factory=JobFlags)
    provider_raw: dict[str, dict[str, Any]] = Field(default_factory=dict)


def flag_is_set(metadata_json: dict[str, Any] | None, name: str) -> bool:
    """Read a job flag: the `flags` section is authoritative, the old
    top-level key is the fallback for rows from before migration 0031."""
    md = metadata_json or {}
    flags = md.get("flags")
    if isinstance(flags, dict) and name in flags:
        return bool(flags[name])
    return bool(md.get(name))


def with_flags(metadata_json: dict[str, Any] | None, **flags: bool) -> dict[str, Any]:
    """Return a copy of the bag with the given flags set in the `flags`
    section (and any same-named legacy top-level keys removed)."""
    md = dict(metadata_json or {})
    section = dict(md.get("flags") or {})
    for name, value in flags.items():
        section[name] = value
        md.pop(name, None)
    md["flags"] = section
    return md
