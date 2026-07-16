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


class SystemVersionResponse(BaseModel):
    version: str
