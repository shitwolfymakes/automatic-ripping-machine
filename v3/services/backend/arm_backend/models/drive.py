from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Enum, String, func
from sqlmodel import Field, SQLModel

from arm_common import DriveStatus, new_id


def _drive_id() -> str:
    return new_id("drv")


class Drive(SQLModel, table=True):
    __tablename__ = "drives"

    id: str = Field(default_factory=_drive_id, primary_key=True)
    hostname: str = Field(sa_column=Column(String, unique=True, nullable=False, index=True))
    device_path: str = Field(nullable=False)
    display_name: str | None = Field(default=None)
    status: DriveStatus = Field(
        sa_column=Column(
            Enum(
                DriveStatus,
                name="drive_status",
                native_enum=True,
                create_type=False,
                values_callable=lambda e: [x.value for x in e],
            ),
            nullable=False,
            server_default=DriveStatus.ONLINE.value,
        )
    )
    last_seen_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    rip_params_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False, server_default="{}"),
    )
    default_session_id: str | None = Field(default=None)
    created_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    )
    updated_at: datetime | None = Field(
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        )
    )
