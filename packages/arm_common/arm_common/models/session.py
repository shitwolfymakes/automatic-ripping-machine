from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Field, SQLModel

from arm_common.models._columns import created_at_column, enum_column, updated_at_column
from arm_common.enums import MediaType, MusicCoverSize
from arm_common.music_tags import MUSIC_TAG_CHOICES
from arm_common.ulid import new_id


def _session_id() -> str:
    return new_id("ses")


class Session(SQLModel, table=True):
    __tablename__ = "sessions"

    id: str = Field(default_factory=_session_id, primary_key=True)
    name: str = Field(sa_column=Column(String, nullable=False))
    media_type: MediaType = Field(sa_column=enum_column(MediaType, "media_type"))
    is_builtin: bool = Field(sa_column=Column(Boolean, nullable=False, server_default="false"))
    rip_preset_id: str = Field(
        sa_column=Column(String, ForeignKey("rip_presets.id", ondelete="RESTRICT"), nullable=False)
    )
    transcode_preset_id: str | None = Field(
        sa_column=Column(String, ForeignKey("transcode_presets.id", ondelete="RESTRICT"), nullable=True)
    )
    output_path_template: str = Field(sa_column=Column(String, nullable=False))
    overrides_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    # Music sessions only: the tags, and whether the cover, written into each
    # encoded track. Values from MUSIC_TAG_CHOICES; every one by default.
    music_tag_fields: list[str] = Field(
        default_factory=lambda: list(MUSIC_TAG_CHOICES),
        sa_column=Column(ARRAY(String), nullable=False, server_default="{" + ",".join(MUSIC_TAG_CHOICES) + "}"),
    )
    # Music sessions only: the Cover Art Archive size embedded as the cover.
    # VARCHAR, validated app-side by MusicCoverSize.
    music_cover_size: MusicCoverSize = Field(
        default=MusicCoverSize.PX_500,
        sa_column=enum_column(MusicCoverSize, "music_cover_size", server_default=MusicCoverSize.PX_500.value),
    )
    created_by_user_id: str | None = Field(
        sa_column=Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    )
    created_at: datetime | None = Field(sa_column=created_at_column())
    updated_at: datetime | None = Field(sa_column=updated_at_column())
