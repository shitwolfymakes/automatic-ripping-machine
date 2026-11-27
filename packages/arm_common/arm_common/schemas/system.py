from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class StoragePlacement(StrEnum):
    """Where the staging area sits relative to the raw folder."""

    INSIDE_RAW = "inside_raw"
    SAME_DEVICE = "same_device"
    SEPARATE_DEVICE = "separate_device"


class DiagnosticDetail(BaseModel):
    """One sub-check row (e.g. docker socket vs image) under a diagnostics check."""

    label: str
    ok: bool
    message: str | None = None


class SystemDiagnosticCheck(BaseModel):
    name: str
    status: str  # "ok" | "warning" | "error"
    detail: str | None = None
    details: list[DiagnosticDetail] = []
    # transcoder only: where encode containers run ("local" | "remote" | "none")
    location: str | None = None
    remote_host: str | None = None


class PathStatus(BaseModel):
    name: str
    path: str
    exists: bool
    writable: bool
    # Host-side bind source (ARM_HOST_*_PATH) and the backend's effective ids,
    # so the UI can print the exact `chown` fix.
    host_path: str | None = None
    uid: int | None = None
    gid: int | None = None
    # Staging only: its placement relative to raw. None for every other root, or
    # when either path is missing.
    placement: StoragePlacement | None = None


class SystemDiagnosticsResponse(BaseModel):
    status: str
    checks: list[SystemDiagnosticCheck]
    paths: list[PathStatus]


class StatsResponse(BaseModel):
    uptime_seconds: int
    jobs_by_status: dict[str, int]
    drives_online: int
    events_unsent: int


class SystemVersionResponse(BaseModel):
    version: str
    # None until a background check against the release feed has succeeded.
    latest_version: str | None = None
    update_available: bool | None = None
    release_url: str | None = None
    # The project's GitHub page; always set by the Backend so the UI can link to it.
    repo_url: str | None = None


class MemoryInfo(BaseModel):
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float


class StorageRoot(BaseModel):
    name: str
    path: str
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float
    # Staging only; see PathStatus.placement.
    placement: StoragePlacement | None = None


class SystemResourcesResponse(BaseModel):
    cpu_percent: float
    cpu_temp: float
    memory: MemoryInfo
    storage: list[StorageRoot]


class JobLogFileView(BaseModel):
    """One per-job aggregated log file under `/logs/jobs/` (`GET /api/logs`)."""

    job_id: str
    size_bytes: int
    modified_at: datetime  # UTC, timezone-aware
