"""Typed core for `jobs.metadata_json`.

The bag holds four kinds of content, and this module gives each a home:

- `scan_result` — the full ScanResult dump from identify time (load-bearing:
  rip-start's track selection reads it). Already typed by `ScanResult`.
- `identity` — what identification concluded: which provider, the external
  ids, the synopsis. Written at identify; never merged from raw payloads.
- `music` — provider-shaped section with a real reader (the music naming tokens).
- `identity_claims` — per-source identity proposals (arm_backend.identity).
- `flags` — booleans that steer behaviour (`unidentified` parks placeholder
  rips at ripped_awaiting_identify; `dispatch_timeout` is diagnostic;
  `rerip_allowed` lets a ripped disc through the previously-ripped check once).
- `previously_ripped` — the earlier rip a held disc matched (the review hold's
  reason; no countdown runs while it is set).
- `identity_suggestion` — a confident match held for the operator to confirm (auto-apply
  off; no countdown runs while it is set).
- `identify_attempts` — on an automatic-match miss, each source the dispatcher
  tried and its outcome (`{source, step, kind, outcome, detail}`, at most 20);
  the review card says why the match missed. Dropped on a hit or a resolve.
- `identify_match` — the weighted title search's breakdown (evidence, queries, call counts, the scored
  candidates and why the top one won). Written on every automatic video identify (accepted, shortlisted,
  no match or exact hit) and replaced by the next one; a shortlist's rows are its leading candidates.
- `provider_raw` — everything a provider returned, keyed by provider name.
  Data for the raw viewer and future backfills, never read for behaviour.
  Rows migrated from the old top-level merge keep theirs under `"legacy"`.

`extra="allow"` everywhere, so a validate/dump round-trip on rows written
before migration 0032 doesn't drop whatever was there; tighten to `forbid`
once those rows are confirmed gone. The pending session lives in the
`pending_session_id` job column, not in this bag.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from arm_common.schemas.identity import IdentityClaims
from arm_common.schemas.ripper import ScanResult


class ExternalIds(BaseModel):
    model_config = ConfigDict(extra="allow")

    imdb: str | None = None
    tmdb: str | None = None
    tvdb: str | None = None
    tvmaze: str | None = None
    anidb: str | None = None  # reserved
    musicbrainz_release: str | None = None
    # Whether `tmdb` names a movie or a TV show: TMDb numbers the two
    # separately, so a movie's id must never be used as a show id (episode
    # stage). None for ids stored before this field existed.
    tmdb_kind: Literal["movie", "tv"] | None = None


class IdentityFacts(BaseModel):
    """What a person uses to tell titles apart: run, plot, rating, people.
    Filled from a provider payload by `arm_backend.metadata.facts`; shown in
    the match picker and snapshotted on the job when a match is used."""

    model_config = ConfigDict(extra="ignore")

    end_year: int | None = None
    overview: str | None = None
    rating: float | None = None  # 0-10
    rating_source: Literal["imdb", "tmdb", "tvmaze"] | None = None
    votes: int | None = None
    genres: list[str] = Field(default_factory=list)
    creators: list[str] = Field(default_factory=list)  # series creators, or a movie's directors
    cast: list[str] = Field(default_factory=list)  # top billed, at most three
    episode_count: int | None = None


class JobIdentity(BaseModel):
    """What identification concluded. Title/year/media_type/poster live on
    the Job row itself — this records where they came from and the ids that
    let a UI link out or re-query."""

    model_config = ConfigDict(extra="allow")

    provider: str
    external_ids: ExternalIds = Field(default_factory=ExternalIds)
    overview: str | None = None
    identified_at: datetime | None = None
    # Snapshot of the picked match's facts. Not refreshed; a later identify or accept replaces the whole identity.
    facts: IdentityFacts | None = None
    facts_fetched_at: datetime | None = None


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
    # On a ripped job: the operator chose "Rip again", so the next identify of
    # this disc skips the previously-ripped check once (and clears the flag).
    rerip_allowed: bool = False


class PreviouslyRipped(BaseModel):
    """Why a held job sits in AWAITING_REVIEW without a countdown: its disc
    matched the fingerprint of an earlier rip (on_previously_ripped=hold)."""

    model_config = ConfigDict(extra="allow")

    job_id: str


class SuggestionCandidate(BaseModel):
    """One row of a shortlist. It carries no provider record: accepting it asks the provider for the title again by
    `ids`, so the job's metadata does not grow by five payloads."""

    title: str
    year: int | None = None
    kind: Literal["movie", "tv"]
    runtime: float | None = None
    # Every provider that returned it, and the best-ranked one (asked first on accept).
    providers: list[str] = Field(default_factory=list)
    provider: str | None = None
    ids: dict[str, str] = Field(default_factory=dict)
    score: float


class IdentitySuggestion(BaseModel):
    """A match identify did not apply: a confident one the media type's "Apply confident matches" switch held
    (`auto_apply_off`, `ambiguous_toc`), or a shortlist of close ones (`close`; `alternatives` are its rows, best
    first, and the top-level fields repeat the first). The job keeps its miss title and the `unidentified` flag and
    waits until the operator accepts it (POST /api/jobs/{id}/identity/accept, with `alternative` for a shortlist) or
    identifies the disc another way (any resolve clears this section). A held job waits in AWAITING_REVIEW with no
    countdown; a shortlist with `block_on_miss` off lets the disc rip unidentified and keeps the section."""

    model_config = ConfigDict(extra="allow")

    reason: Literal["auto_apply_off", "close", "ambiguous_toc"] = "auto_apply_off"
    score: float | None = None
    alternatives: list[SuggestionCandidate] = Field(default_factory=list)

    provider: str
    title: str
    year: int | None = None
    kind: Literal["movie", "tv", "music"]
    poster_url: str | None = None
    external_ids: ExternalIds = Field(default_factory=ExternalIds)
    overview: str | None = None
    # The provider's raw hit, so accepting re-applies exactly what identify
    # would have applied (provider_raw, music section, disc number).
    payload: dict[str, Any] = Field(default_factory=dict)
    suggested_at: datetime


class MatchTitle(BaseModel):
    """One disc text the search read: where it came from, as written, and the title left once noise was stripped."""

    source: str
    text: str
    core: str
    # Format and edition words stripped from the tail: counted when a candidate has them, free when not.
    optional: list[str] = Field(default_factory=list)


class MatchYear(BaseModel):
    year: int
    sources: list[str]
    reliability: float


class MatchEvidence(BaseModel):
    titles: list[MatchTitle] = Field(default_factory=list)
    years: list[MatchYear] = Field(default_factory=list)
    # Numbers a candidate title must carry (`2049` in Blade Runner 2049).
    numbers: list[str] = Field(default_factory=list)
    runtime_min: list[float] = Field(default_factory=list)
    runtime_source: Literal["structure", "titles", "episodes"] | None = None
    p_tv: float
    kind_reasons: list[str] = Field(default_factory=list)


class MatchQuery(BaseModel):
    text: str
    kinds: list[Literal["movie", "tv"]]


class MatchCalls(BaseModel):
    list: int = 0
    detail: int = 0
    # Answers served from the cache: no provider call.
    cached: int = 0


class MatchParts(BaseModel):
    """The weighted parts of a candidate's score; they add up to `score`."""

    title: float
    year: float
    runtime: float
    kind: float
    agreement: float


class MatchCandidate(BaseModel):
    title: str
    year: int | None = None
    kind: Literal["movie", "tv"]
    runtime: float | None = None
    # Every provider that returned it, and the best-ranked one (whose own record an accept applies).
    providers: list[str] = Field(default_factory=list)
    provider: str | None = None
    ids: dict[str, str] = Field(default_factory=dict)
    score: float
    parts: MatchParts
    # `numbers_differ`, `numbers_partial`, `disc_number_missing`, `candidate_sequel_number`, `year_mismatch`,
    # `runtime_far`, `edition_tolerance`, `text_disagrees`.
    flags: list[str] = Field(default_factory=list)


class MatchThresholds(BaseModel):
    accept: float
    margin: float
    floor: float
    title_min: float


class IdentifyMatch(BaseModel):
    """Why the weighted search decided what it did (spec 6). `candidates` holds at most five, best first; for a
    shortlist the first `shortlist` of them are the rows to offer. An exact hit (TheDiscDB, fingerprint) is never
    re-ranked: its own text score is stored with `exact`, and `text_disagrees` when that score is very low."""

    model_config = ConfigDict(extra="allow")

    version: Literal[1] = 1
    decision: Literal["accept", "shortlist", "no_match", "exact"]
    exact: Literal["thediscdb", "fingerprint"] | None = None
    text_disagrees: bool = False
    evidence: MatchEvidence
    queries: list[MatchQuery] = Field(default_factory=list)
    calls: MatchCalls = Field(default_factory=MatchCalls)
    candidates: list[MatchCandidate] = Field(default_factory=list)
    shortlist: int = 0
    # The shortlist row the operator picked: its breakdown is the one that explains the applied title.
    picked: int | None = None
    runner_up: float | None = None
    thresholds: MatchThresholds


class JobMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    scan_result: ScanResult | None = None
    identity: JobIdentity | None = None
    music: MusicMeta | None = None
    # What every identity source proposed (typed; see arm_common.schemas.identity).
    # Left-to-right union: a valid section parses as IdentityClaims; a corrupt
    # or future-version one passes through raw, so one bad row never fails a
    # bulk read and a validate/dump round-trip (resolve) never wipes it. The
    # backend's claims_of() warns and treats an invalid section as empty.
    identity_claims: IdentityClaims | dict[str, Any] | None = Field(default=None, union_mode="left_to_right")
    flags: JobFlags = Field(default_factory=JobFlags)
    # Set when on_previously_ripped=hold parked this job; names the earlier rip.
    previously_ripped: PreviouslyRipped | None = None
    # Set when a media type's auto-apply switch held a confident match for
    # the operator to confirm; no countdown runs while it is set.
    identity_suggestion: IdentitySuggestion | None = None
    # Set on an automatic-match miss: what the dispatcher tried and how each
    # attempt ended (arm_backend.metadata.dispatcher.last_attempts).
    identify_attempts: list[dict[str, Any]] | None = None
    # The weighted search's breakdown, kept after an apply (unlike the miss attempts above).
    identify_match: IdentifyMatch | None = None
    provider_raw: dict[str, dict[str, Any]] = Field(default_factory=dict)


def flag_is_set(metadata_json: dict[str, Any] | None, name: str) -> bool:
    """Read a job flag: the `flags` section is authoritative, the old
    top-level key is the fallback for rows from before migration 0032."""
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


def previously_ripped_job_id(metadata_json: dict[str, Any] | None) -> str | None:
    """The earlier rip a held job matched (see PreviouslyRipped), or None."""
    section = (metadata_json or {}).get("previously_ripped")
    if isinstance(section, dict) and isinstance(section.get("job_id"), str):
        return str(section["job_id"])
    return None


def identity_suggestion_of(metadata_json: dict[str, Any] | None) -> IdentitySuggestion | None:
    """The confident match a held job is waiting for the operator to
    confirm (see IdentitySuggestion), or None when absent or malformed."""
    section = (metadata_json or {}).get("identity_suggestion")
    if not isinstance(section, dict):
        return None
    try:
        return IdentitySuggestion.model_validate(section)
    except ValidationError:
        return None


def without_identity_suggestion(metadata_json: dict[str, Any] | None) -> dict[str, Any]:
    """A copy of the bag with the suggestion section removed."""
    md = dict(metadata_json or {})
    md.pop("identity_suggestion", None)
    return md
