from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, SQLModel

from arm_common.models._columns import enum_column, updated_at_column
from arm_common.enums import RetentionPolicy


class Config(SQLModel, table=True):
    __tablename__ = "config"

    id: int = Field(sa_column=Column(Integer, primary_key=True, autoincrement=False))
    tmdb_api_key: str | None = Field(default=None)
    omdb_api_key: str | None = Field(default=None)
    tvdb_api_key: str | None = Field(default=None)
    # Operator's MakeMKV registration key (a purchased perma-key or a beta key
    # pasted in by hand). When set it is the authoritative source the ripper
    # writes into ~/.MakeMKV/settings.conf before each rip, overriding the
    # legacy MAKEMKV_KEY env var; when empty the ripper falls back to that env
    # var and then to the monthly forum beta-key scrape. See
    # services/ripper/arm_ripper/makemkv_key.py.
    makemkv_key: str | None = Field(default=None)
    # Disc-free makemkv key-validity, reported by the ripper's probe (see
    # services/ripper/arm_ripper/scan/makemkv.py probe_makemkv_key + the
    # /api/ripper/makemkv-key-status endpoint). All null until a ripper reports.
    makemkv_key_valid: bool | None = Field(sa_column=Column(Boolean, nullable=True))
    makemkv_key_state: str | None = Field(sa_column=Column(String, nullable=True))
    makemkv_key_checked_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    # MusicBrainz requires a non-empty User-Agent (they 403 blank UAs); `armv3`
    # is a reasonable shared default that won't blow up the first audio-CD rip
    # on a fresh install. Operators are still encouraged to override with an
    # app-name-plus-contact-info string per MB's etiquette guide — see the UI
    # form's placeholder hint.
    musicbrainz_user_agent: str | None = Field(default="armv3")
    # Persisted metadata provider for the identify flow (search + detail).
    # Default `tmdb` — free, effectively unlimited, richer than OMDb. Validated
    # app-side to {tmdb, omdb}; tvdb/makemkv are key-test-only, not search providers.
    metadata_provider: str = Field(
        default="tmdb",
        sa_column=Column(String, nullable=False, server_default="tmdb"),
    )
    auto_transcode_on_idle: bool = Field(sa_column=Column(Boolean, nullable=False, server_default="false"))
    auto_rip_on_insert: bool = Field(sa_column=Column(Boolean, nullable=False, server_default="true"))
    block_on_miss: bool = Field(sa_column=Column(Boolean, nullable=False, server_default="true"))
    ripping_paused: bool = Field(sa_column=Column(Boolean, nullable=False, server_default="false"))
    default_retention_policy: RetentionPolicy = Field(
        sa_column=enum_column(
            RetentionPolicy,
            "retention_policy",
            server_default=RetentionPolicy.PRUNE_AFTER_SESSION.value,
        )
    )
    notification_apprise_urls: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )
    notifications_enabled: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    session_signing_key: bytes | None = Field(sa_column=Column(LargeBinary, nullable=True))
    updated_by_user_id: str | None = Field(
        sa_column=Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    )
    updated_at: datetime | None = Field(sa_column=updated_at_column())
