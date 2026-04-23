from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from arm_backend.models._columns import created_at_column, enum_column, updated_at_column
from arm_common import ContainerFormat, HwPreference, MediaType, TranscodeTool, new_id


def _transcode_preset_id() -> str:
    return new_id("tpr")


class TranscodePreset(SQLModel, table=True):
    __tablename__ = "transcode_presets"

    id: str = Field(default_factory=_transcode_preset_id, primary_key=True)
    name: str = Field(sa_column=Column(String, nullable=False))
    media_type: MediaType = Field(sa_column=enum_column(MediaType, "media_type"))
    is_builtin: bool = Field(
        sa_column=Column(Boolean, nullable=False, server_default="false")
    )
    tool: TranscodeTool = Field(sa_column=enum_column(TranscodeTool, "transcode_tool"))
    preset_ref: str | None = Field(default=None)
    preset_json: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSONB, nullable=True)
    )
    container: ContainerFormat = Field(
        sa_column=enum_column(ContainerFormat, "container_format")
    )
    hw_preference: HwPreference | None = Field(
        sa_column=enum_column(HwPreference, "hw_preference", nullable=True)
    )
    extra_args: str | None = Field(default=None)
    created_by_user_id: str | None = Field(
        sa_column=Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    )
    created_at: datetime | None = Field(sa_column=created_at_column())
    updated_at: datetime | None = Field(sa_column=updated_at_column())
