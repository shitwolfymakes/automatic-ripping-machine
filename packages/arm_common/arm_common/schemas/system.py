from pydantic import BaseModel


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
    # so the UI can print the exact `chown` fix (setup spec §6.3).
    host_path: str | None = None
    uid: int | None = None
    gid: int | None = None


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


class SystemResourcesResponse(BaseModel):
    cpu_percent: float
    cpu_temp: float
    memory: MemoryInfo
    storage: list[StorageRoot]
