from typing import Any

from pydantic import BaseModel, Field

from arm_common.enums import DiscType


class RegisterRequest(BaseModel):
    hostname: str
    device_path: str
    ripper_version: str
    hw_caps: dict[str, Any] = Field(default_factory=dict)


class ScanTitle(BaseModel):
    index: int
    duration_seconds: int
    chapter_count: int | None = None
    size_bytes: int | None = None
    source_file: str | None = None


class ScanResult(BaseModel):
    disc_type: DiscType
    volume_label: str | None = None
    titles: list[ScanTitle] = Field(default_factory=list)
    musicbrainz_disc_id: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class IdentifyRequest(BaseModel):
    drive_id: str
    scan_result: ScanResult
