from pydantic import BaseModel


class PreflightCheck(BaseModel):
    name: str
    status: str  # "ok" | "warning" | "error"
    detail: str | None = None


class PreflightResponse(BaseModel):
    status: str
    checks: list[PreflightCheck]


class PathStatus(BaseModel):
    name: str
    path: str
    exists: bool
    writable: bool


class PathsResponse(BaseModel):
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


class HostResourcesSnapshot(BaseModel):
    cpu_percent: float
    cpu_temp: float
    memory: MemoryInfo
    storage: list[StorageRoot]


class HostResourcesView(BaseModel):
    role: str  # "backend" | "ripper"
    hostname: str
    version: str
    snapshot: HostResourcesSnapshot
