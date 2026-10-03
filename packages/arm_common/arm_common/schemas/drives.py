"""Phase 8 wire schemas for drive mutations.

Read views still return the `Drive` SQLModel directly (the UI hand-types its
projection); this module only houses the update request body so the manual
PATCH endpoint and any future helpers can share validation rules.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from arm_common.enums import DriveIdentityKind, DriveLifecycle, DriveMediaStatus, DriveMode, DriveStatus, JobStatus


class DriveCurrentJobView(BaseModel):
    id: str
    title: str | None
    status: JobStatus


class DriveView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    hostname: str
    device_path: str
    display_name: str | None
    status: DriveStatus
    last_seen_at: datetime | None
    media_status: DriveMediaStatus | None
    media_status_at: datetime | None
    default_session_id: str | None
    rip_speed: int | None
    drive_mode: DriveMode | None
    uhd_capable: bool | None
    prescan_cache_mb: int | None
    prescan_timeout: int | None
    prescan_retries: int | None
    disc_enum_timeout: int | None
    created_at: datetime | None
    updated_at: datetime | None
    # Lifecycle (spec §1). `lifecycle` is the operator's decision; `present`
    # is whether the hardware is here right now — orthogonal.
    lifecycle: DriveLifecycle
    present: bool
    identity_kind: DriveIdentityKind | None
    serial: str | None
    by_id_name: str | None
    vendor: str | None
    model: str | None
    last_error: str | None
    current_job: DriveCurrentJobView | None = None


class DriveUpdateRequest(BaseModel):
    """PATCH /api/drives/{id} body. Both fields optional + nullable.

    `default_session_id=None` (explicit null) clears the field; omitting it
    leaves it untouched. `extra="forbid"` keeps the API honest — UI typos
    surface as 422 instead of being silently dropped.
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    default_session_id: str | None = None
    rip_speed: int | None = None
    drive_mode: DriveMode | None = None
    uhd_capable: bool | None = None
    prescan_cache_mb: int | None = None
    prescan_timeout: int | None = None
    prescan_retries: int | None = None
    disc_enum_timeout: int | None = None


class DriveDiagnosticItem(BaseModel):
    """One row of GET /api/drives/diagnostic's "Look for issues" panel: the
    lifecycle model's own verdict on a drive, not just heartbeat staleness."""

    id: str
    lifecycle: DriveLifecycle
    present: bool
    identity_kind: DriveIdentityKind | None
    device_path: str
    status: DriveStatus
    # DriveMediaStatus is a StrEnum, so this serializes to its string value
    # (e.g. "loaded") in the JSON response.
    media_status: DriveMediaStatus | None
    media_status_at: datetime | None
    # Enrolled only: "running" | "exited" | "missing" | "stale-image" |
    # "unknown"; None for detected/ignored rows (no ripper container).
    container: str | None
    last_error: str | None
    healthy: bool
    notes: list[str]


class DriveDiagnosticResponse(BaseModel):
    drives: list[DriveDiagnosticItem]
    # Scanner / manager / host-disk level notes — not tied to any one drive.
    system: list[str] = Field(default_factory=list)


class DriveRescanResponse(BaseModel):
    online: int
    stale: int
    detected: int = 0
    ignored: int = 0
    enrolled: int = 0
    absent: int = 0
    pruned: int = 0


class DriveDevicePathUpdateRequest(BaseModel):
    """Ripper → backend: the drive now occupies this node (replug under a
    new srN). Keeps the UI's node current without a re-register."""

    device_path: str
