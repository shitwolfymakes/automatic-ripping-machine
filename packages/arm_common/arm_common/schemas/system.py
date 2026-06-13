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
