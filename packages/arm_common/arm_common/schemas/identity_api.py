"""Request/response schemas for the identity, match, pin and episode-browse
endpoints (design spec 2026-09-28-identity-sources, section 7).

`IdentityView` is a read-shaped projection of `IdentityClaims` (stored
`identity_claims`) plus each track's currently-resolved values -- not the
stored claims themselves, which stay internal to the backend (`arm_common.
schemas.identity`).
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from arm_common.enums import TrackRole
from arm_common.schemas.identity import ClaimStatus, TrackClaim

EpisodeSourceSetting = Literal["tmdb", "tvmaze", "tvdb"]


class SourceSummary(BaseModel):
    """One source's claims for a job, display-shaped."""

    status: ClaimStatus = "ok"
    detail: str | None = None
    run_at: datetime | None = None
    suggestion: bool = False
    inputs: dict[str, Any] = Field(default_factory=dict)
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class TrackIdentityView(BaseModel):
    """One track's currently-resolved identity values plus every source's
    competing proposal for it (`proposals`, keyed by source id)."""

    model_config = ConfigDict(from_attributes=True)

    track_id: str
    source_ref: str
    role: TrackRole | None = None
    title: str | None = None
    season: int | None = None
    episode_number: int | None = None
    episode_number_end: int | None = None
    episode_name: str | None = None
    custom_filename: str | None = None
    excluded: bool = False
    identity_provenance: dict[str, str] | None = None
    proposals: dict[str, TrackClaim] = Field(default_factory=dict)


class IdentityView(BaseModel):
    """`GET /api/jobs/{id}/identity` response."""

    sources: dict[str, SourceSummary] = Field(default_factory=dict)
    pin: dict[str, str] = Field(default_factory=dict)
    tracks: list[TrackIdentityView] = Field(default_factory=list)


class MatchRequest(BaseModel):
    """`POST /api/jobs/{id}/identity/match` body."""

    model_config = ConfigDict(extra="forbid")

    source: EpisodeSourceSetting | None = None
    season: int | None = None
    disc_number: int | None = None
    tolerance: int | None = Field(default=None, ge=1, le=1800)
    apply: bool = False


class MatchEntryView(BaseModel):
    """One title's episode match within a `MatchOutcomeView`."""

    source_ref: str
    season: int | None = None
    episode: int | None = None
    episode_end: int | None = None
    episode_name: str | None = None
    confidence: float | None = None


class MatchOutcomeView(BaseModel):
    """One provider's outcome from a `/identity/match` call."""

    source_id: str
    status: ClaimStatus = "ok"
    detail: str | None = None
    suggestion: bool = False
    coverage: float | None = None
    # Mean match confidence across this outcome's matched tracks; `None` when
    # none matched (a miss/skipped/error outcome, or "ok" with zero matches).
    score: float | None = None
    matches: list[MatchEntryView] = Field(default_factory=list)
    alternatives: list[dict[str, Any]] = Field(default_factory=list)


class MatchPreview(BaseModel):
    """`POST /api/jobs/{id}/identity/match` response, for both
    `apply=False` (a preview, nothing written) and `apply=True` (reflects the
    stored outcomes)."""

    outcomes: list[MatchOutcomeView] = Field(default_factory=list)


class EpisodeSummary(BaseModel):
    """One episode in an `EpisodeListView`."""

    number: int
    name: str | None = None
    runtime_s: int | None = None
    special: bool = False


class EpisodeListView(BaseModel):
    """`GET /api/jobs/{id}/identity/episodes` response."""

    source_id: str
    show_id: str
    season: int
    episodes: list[EpisodeSummary] = Field(default_factory=list)
