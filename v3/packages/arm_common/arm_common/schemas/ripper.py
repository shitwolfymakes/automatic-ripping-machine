from typing import Any

from pydantic import BaseModel, Field

from arm_common.enums import DiscType, JobStatus


class RegisterRequest(BaseModel):
    hostname: str
    device_path: str
    ripper_version: str
    hw_caps: dict[str, Any] = Field(default_factory=dict)


class RegisterResponse(BaseModel):
    drive_id: str
    drive_config: dict[str, Any] = Field(default_factory=dict)
    service_token_verified: bool = True


class IdentifyRequest(BaseModel):
    drive_id: str
    disc_type: DiscType
    volume_label: str | None = None
    scan_result: dict[str, Any] = Field(default_factory=dict)


class IdentifyResponse(BaseModel):
    job_id: str
    status: JobStatus
