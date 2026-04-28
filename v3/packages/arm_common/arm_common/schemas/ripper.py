from typing import Any

from pydantic import BaseModel, Field

from arm_common.enums import DiscType


class RegisterRequest(BaseModel):
    hostname: str
    device_path: str
    ripper_version: str
    hw_caps: dict[str, Any] = Field(default_factory=dict)


class IdentifyRequest(BaseModel):
    drive_id: str
    disc_type: DiscType
    volume_label: str | None = None
    scan_result: dict[str, Any] = Field(default_factory=dict)
