from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from arm_common.enums import DiscType, JobStatus


class ResolveRequest(BaseModel):
    title: str
    year: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    drive_id: str
    disc_type: DiscType
    status: JobStatus
    title: str | None
    year: int | None
    metadata_json: dict[str, Any]
