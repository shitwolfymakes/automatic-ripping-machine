from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, SQLModel

from arm_backend.models._columns import created_at_column, enum_column, updated_at_column
from arm_common import GpuStatus, GpuVendor, new_id


def _gpu_id() -> str:
    return new_id("gpu")


class Gpu(SQLModel, table=True):
    __tablename__ = "gpus"

    id: str = Field(default_factory=_gpu_id, primary_key=True)
    vendor: GpuVendor = Field(sa_column=enum_column(GpuVendor, "gpu_vendor"))
    device_path: str = Field(sa_column=Column(String, nullable=False))
    encoder_kinds: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(String), nullable=False, server_default="{}"),
    )
    status: GpuStatus = Field(
        sa_column=enum_column(GpuStatus, "gpu_status", server_default=GpuStatus.AVAILABLE.value)
    )
    claimed_by_task_id: str | None = Field(
        sa_column=Column(
            String, ForeignKey("transcode_tasks.id", ondelete="SET NULL"), nullable=True
        )
    )
    last_seen_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime | None = Field(sa_column=created_at_column())
    updated_at: datetime | None = Field(sa_column=updated_at_column())
