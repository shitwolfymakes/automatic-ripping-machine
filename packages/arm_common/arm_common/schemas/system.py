from pydantic import BaseModel


class SystemDiagnosticCheck(BaseModel):
    name: str
    status: str  # "ok" | "warning" | "error"
    detail: str | None = None


class PathStatus(BaseModel):
    name: str
    path: str
    exists: bool
    writable: bool


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
