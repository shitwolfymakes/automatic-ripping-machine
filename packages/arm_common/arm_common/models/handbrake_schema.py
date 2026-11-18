from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from arm_common.ulid import new_id


def _handbrake_schema_id() -> str:
    return new_id("hbs")


class HandbrakeSchemaRecord(SQLModel, table=True):
    """One HandBrake schema dump a transcoder image reported, keyed by content hash."""

    __tablename__ = "handbrake_schemas"

    id: str = Field(default_factory=_handbrake_schema_id, primary_key=True)
    content_hash: str = Field(sa_column=Column(String, nullable=False, unique=True))
    handbrake_tag: str = Field(sa_column=Column(String, nullable=False))
    preset_version: str = Field(sa_column=Column(String, nullable=False))
    image_ref: str = Field(sa_column=Column(String, nullable=False))
    raw: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    fetched_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
