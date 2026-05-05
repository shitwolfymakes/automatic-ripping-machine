from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String
from sqlmodel import Field, SQLModel

from arm_common.models._columns import created_at_column, enum_column, updated_at_column
from arm_common.enums import DriveMediaStatus, DriveStatus
from arm_common.ulid import new_id


def _drive_id() -> str:
    return new_id("drv")


class Drive(SQLModel, table=True):
    __tablename__ = "drives"

    id: str = Field(default_factory=_drive_id, primary_key=True)
    hostname: str = Field(sa_column=Column(String, unique=True, nullable=False, index=True))
    device_path: str = Field(nullable=False)
    display_name: str | None = Field(default=None)
    status: DriveStatus = Field(
        sa_column=enum_column(DriveStatus, "drive_status", server_default=DriveStatus.ONLINE.value)
    )
    last_seen_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    # Reported by each ripper on a heartbeat. Lets the backend reject a
    # manual-rip request fast when the user clicks Start without loading
    # a disc, instead of letting identify land an empty scan_result.
    # Stale rows (older than HEARTBEAT_FRESHNESS_SECONDS in the manual-
    # trigger endpoint) are treated as UNKNOWN.
    media_status: DriveMediaStatus | None = Field(
        sa_column=enum_column(DriveMediaStatus, "drive_media_status", nullable=True)
    )
    media_status_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), nullable=True))
    rip_params_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default="{}"),
    )
    default_session_id: str | None = Field(
        sa_column=Column(String, ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True)
    )
    created_at: datetime | None = Field(sa_column=created_at_column())
    updated_at: datetime | None = Field(sa_column=updated_at_column())
