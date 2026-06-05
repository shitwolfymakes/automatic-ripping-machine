"""Auth and UI-side response schemas (Phase 5).

Login / logout / change-password live here. Read-side `JobDetailView` and
`ConfigView` / `ConfigUpdateRequest` are also UI-shaped projections — kept
in this module rather than `jobs.py` / a new `config.py` so the UI types
land in one place.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from arm_common.enums import RetentionPolicy
from arm_common.schemas.jobs import DiscFingerprintView, JobView, TrackView


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    expires_at: datetime
    password_must_change: bool


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class JobDetailView(BaseModel):
    job: JobView
    tracks: list[TrackView]
    fingerprints: list[DiscFingerprintView] = Field(default_factory=list)


class ConfigView(BaseModel):
    """`Config` row projected for the UI. `session_signing_key` is intentionally absent."""

    tmdb_api_key: str | None
    omdb_api_key: str | None
    musicbrainz_user_agent: str | None
    auto_transcode_on_idle: bool
    auto_rip_on_insert: bool
    block_on_miss: bool
    default_retention_policy: RetentionPolicy
    notification_apprise_urls: list[str]
    notifications_enabled: bool
    updated_by_user_id: str | None
    updated_at: datetime | None


class ConfigUpdateRequest(BaseModel):
    tmdb_api_key: str | None = None
    omdb_api_key: str | None = None
    musicbrainz_user_agent: str | None = None
    auto_transcode_on_idle: bool | None = None
    auto_rip_on_insert: bool | None = None
    block_on_miss: bool | None = None
    default_retention_policy: RetentionPolicy | None = None
    notification_apprise_urls: list[str] | None = None
    notifications_enabled: bool | None = None


class DiagnosticsServiceView(BaseModel):
    name: str
    log_level: str


class DiagnosticsResponse(BaseModel):
    services: list[DiagnosticsServiceView]
