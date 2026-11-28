"""Auth and UI-side response schemas.

Login / logout / change-password live here. Read-side `JobDetailView` and
`ConfigView` / `ConfigUpdateRequest` are also UI-shaped projections — kept
in this module rather than `jobs.py` / a new `config.py` so the UI types
land in one place.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from arm_common.enums import MissMediaType, MissTitlesKept, PreviouslyRippedAction, RetentionPolicy, UserRole
from arm_common.schemas.jobs import DiscFingerprintView, JobView, PreviousRipView, TrackView
from arm_common.schemas.ripper import ScanFailure


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    expires_at: datetime
    password_must_change: bool
    role: UserRole


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class TitlesReadView(BaseModel):
    """Where MakeMKV's title list stands for a job whose card is up: `pending` while it reads the disc,
    `failed` with its reason when it could not (Start stays off), else `ready`."""

    state: Literal["ready", "pending", "failed"]
    failure: ScanFailure | None = None
    # The sentence that tells the operator why MakeMKV failed and what to try; set with `failure`.
    message: str | None = None


class JobDetailView(BaseModel):
    job: JobView
    tracks: list[TrackView]
    fingerprints: list[DiscFingerprintView] = Field(default_factory=list)
    # The earlier rip this held disc matched (metadata previously_ripped);
    # None when there is none or it has since been deleted.
    previous_rip: PreviousRipView | None = None
    titles_read: TitlesReadView = Field(default_factory=lambda: TitlesReadView(state="ready"))


class ConfigView(BaseModel):
    """`Config` row projected for the UI. `session_signing_key` is intentionally absent."""

    tmdb_api_key: str | None
    omdb_api_key: str | None
    tvdb_api_key: str | None
    makemkv_key: str | None
    musicbrainz_user_agent: str | None
    auto_transcode_on_idle: bool
    auto_rip_on_insert: bool
    block_on_miss: bool
    rip_end_on_completion_message: bool
    community_keydb_enabled: bool
    # Drive scanner tunables — operator-editable, read every tick.
    drive_scan_interval_seconds: int
    drive_detected_prune_days: int
    # Transcode dispatcher parallelism cap — operator-editable, read every
    # tick (the MAX_PARALLEL_TRANSCODES env var only seeds it on first boot).
    max_parallel_transcodes: int
    # ISO-source ripping: concurrent ISO rips, 1 to 8 (default 1).
    max_parallel_iso_rips: int
    # Shortest title the scan lists and the rip writes, in seconds.
    min_title_length_seconds: int
    # The MakeMKV scan timeout a drive uses unless it sets its own (read-only).
    default_scan_timeout_seconds: int
    # transcode_enabled: the runtime switch (a Config DB column, editable).
    # transcode_capable: the deployment capability (read-only, derived from env
    # Settings, not a Config column). capable=False renders the toggle locked.
    transcode_enabled: bool
    transcode_capable: bool
    makemkv_sdf_enabled: bool
    thediscdb_enabled: bool
    thediscdb_refresh_days: int
    episode_sources: list[str]
    disc_hint_sources: list[str]
    episode_match_tolerance_seconds: int
    episode_auto_apply: bool
    ripping_paused: bool
    hold_for_review: bool
    manual_wait_seconds: int
    tick_one_version: bool
    on_previously_ripped: PreviouslyRippedAction
    miss_media_type: MissMediaType
    miss_titles_kept: MissTitlesKept
    default_retention_policy: RetentionPolicy
    notification_apprise_urls: list[str]
    notifications_enabled: bool
    movie_sources: list[str]
    music_sources: list[str]
    search_provider_movie: str
    search_provider_tv: str
    search_provider_music: str
    movie_auto_apply: bool
    music_auto_apply: bool
    crc64service_enabled: bool
    makemkv_key_valid: bool | None = None
    makemkv_key_state: str | None = None
    makemkv_key_checked_at: datetime | None = None
    # Drive whose ripper last reported the key status (the setup walkthrough's "checked by").
    makemkv_key_checked_by_drive_id: str | None = None
    updated_by_user_id: str | None
    updated_at: datetime | None


class ConfigUpdateRequest(BaseModel):
    tmdb_api_key: str | None = None
    omdb_api_key: str | None = None
    tvdb_api_key: str | None = None
    makemkv_key: str | None = None
    musicbrainz_user_agent: str | None = None
    auto_transcode_on_idle: bool | None = None
    auto_rip_on_insert: bool | None = None
    block_on_miss: bool | None = None
    rip_end_on_completion_message: bool | None = None
    community_keydb_enabled: bool | None = None
    drive_scan_interval_seconds: int | None = None
    drive_detected_prune_days: int | None = None
    max_parallel_transcodes: int | None = None
    max_parallel_iso_rips: int | None = None
    min_title_length_seconds: int | None = None
    transcode_enabled: bool | None = None
    makemkv_sdf_enabled: bool | None = None
    thediscdb_enabled: bool | None = None
    thediscdb_refresh_days: int | None = None
    episode_sources: list[str] | None = None
    disc_hint_sources: list[str] | None = None
    episode_match_tolerance_seconds: int | None = None
    episode_auto_apply: bool | None = None
    ripping_paused: bool | None = None
    hold_for_review: bool | None = None
    manual_wait_seconds: int | None = None
    tick_one_version: bool | None = None
    on_previously_ripped: PreviouslyRippedAction | None = None
    miss_media_type: MissMediaType | None = None
    miss_titles_kept: MissTitlesKept | None = None
    notifications_enabled: bool | None = None
    movie_sources: list[str] | None = None
    music_sources: list[str] | None = None
    search_provider_movie: str | None = None
    search_provider_tv: str | None = None
    search_provider_music: str | None = None
    movie_auto_apply: bool | None = None
    music_auto_apply: bool | None = None
    crc64service_enabled: bool | None = None


class KeyCheckRequest(BaseModel):
    """Body for POST /api/config/keys/{name}/check. `value` is an unsaved
    candidate key to probe; when omitted (None), the stored key is used."""

    value: str | None = None


class KeyCheckResponse(BaseModel):
    name: str
    status: Literal["ok", "invalid", "missing", "error", "unknown"]
    detail: str | None = None
    checked_at: datetime | None = None


class DiagnosticsServiceView(BaseModel):
    name: str
    log_level: str


class DiagnosticsResponse(BaseModel):
    services: list[DiagnosticsServiceView]


class UserView(BaseModel):
    id: str
    username: str
    role: UserRole
    disabled: bool
    last_login_at: datetime | None = None


class UserDisabledRequest(BaseModel):
    disabled: bool


class UserPasswordSetRequest(BaseModel):
    new_password: str = Field(min_length=8)
