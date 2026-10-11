"""Typed `jobs.metadata_json["identity_claims"]`: what each identity source
proposed for a job (design spec 2026-09-28-identity-sources, section 4.1).

Field PRESENCE is meaningful in TrackClaim / JobClaim: an absent field means
"no opinion"; a field present with value null means "propose empty" (only the
`manual` source does this, when the operator clears a value). Always dump
with `exclude_unset=True` so presence survives storage.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from arm_common.enums import TrackRole

ClaimStatus = Literal["ok", "miss", "skipped", "error"]

# claim field -> Track attribute. `selected` is stored inverted as `excluded`.
TRACK_CLAIM_FIELDS: dict[str, str] = {
    "role": "role",
    "title": "title",
    "season": "season",
    "episode": "episode_number",
    "episode_end": "episode_number_end",
    "episode_name": "episode_name",
    "filename": "custom_filename",
    "selected": "excluded",
}

# claim field -> Job attribute. JobClaim.title is a search hint only and is
# deliberately NOT applied (job.title belongs to identify / resolve).
JOB_CLAIM_FIELDS: dict[str, str] = {
    "season": "season",
    "disc_number": "disc_number",
    "disc_total": "disc_total",
}


class TrackClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: TrackRole | None = None
    title: str | None = None
    season: int | None = None
    episode: int | None = None
    episode_end: int | None = None
    episode_name: str | None = None
    filename: str | None = None
    selected: bool | None = None
    confidence: float | None = None


class JobClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    season: int | None = None
    disc_number: int | None = None
    disc_total: int | None = None
    title: str | None = None


class SourceClaims(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_at: datetime | None = None
    status: ClaimStatus = "ok"
    detail: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    job: JobClaim = Field(default_factory=JobClaim)
    tracks: dict[str, TrackClaim] = Field(default_factory=dict)
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class IdentityClaims(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: dict[str, SourceClaims] = Field(default_factory=dict)
    # capability name -> source id the operator pinned for this job (PR 3 uses
    # "episode"); a pinned source outranks its tier-mates in the resolver.
    pin: dict[str, str] = Field(default_factory=dict)
