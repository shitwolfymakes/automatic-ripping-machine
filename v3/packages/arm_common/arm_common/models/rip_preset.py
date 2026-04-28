from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from arm_common.models._columns import created_at_column, enum_column, updated_at_column
from arm_common.enums import IdentificationMode, MediaType, OutputMode, TrackSelection
from arm_common.ulid import new_id


def _rip_preset_id() -> str:
    return new_id("rpr")


class RipPreset(SQLModel, table=True):
    __tablename__ = "rip_presets"

    id: str = Field(default_factory=_rip_preset_id, primary_key=True)
    name: str = Field(sa_column=Column(String, nullable=False))
    media_type: MediaType = Field(sa_column=enum_column(MediaType, "media_type"))
    is_builtin: bool = Field(sa_column=Column(Boolean, nullable=False, server_default="false"))
    track_selection: TrackSelection = Field(sa_column=enum_column(TrackSelection, "track_selection"))
    identification_mode: IdentificationMode = Field(sa_column=enum_column(IdentificationMode, "identification_mode"))
    output_mode: OutputMode = Field(sa_column=enum_column(OutputMode, "output_mode"))
    track_filters_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    created_by_user_id: str | None = Field(
        sa_column=Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    )
    created_at: datetime | None = Field(sa_column=created_at_column())
    updated_at: datetime | None = Field(sa_column=updated_at_column())
