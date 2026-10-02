"""Wire schemas for `/api/iso` (Rip from ISO, spec 2026-09-30 section 5/6):
the library listing, the create-rip request/response, and the "preparing"
status an ISO ripper reports before its job exists."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from arm_common.enums import IsoPreparePhase


class IsoLibraryEntry(BaseModel):
    name: str
    kind: Literal["folder", "iso"]
    size_bytes: int | None = None
    modified_at: datetime | None = None
    ripping: bool = False


class IsoLibraryListing(BaseModel):
    host_path: str
    subpath: str
    parent_subpath: str | None
    entries: list[IsoLibraryEntry]


class IsoRipRequest(BaseModel):
    path: str = Field(min_length=1)  # relative to the library
    session_id: str | None = None


class IsoRipCreated(BaseModel):
    drive_id: str


class IsoPrepareReport(BaseModel):
    """POST /api/ripper/iso-prepare: what an ISO ripper is doing before
    identify creates its job. Sent on every phase change, throttled progress
    updates, and as a keepalive while a phase runs."""

    drive_id: str
    phase: IsoPreparePhase
    progress_pct: int | None = Field(default=None, ge=0, le=100)
    current_file: str | None = None


class IsoPrepareView(BaseModel):
    """GET /api/iso/rips/preparing: one ISO rip that has no job yet."""

    drive_id: str
    phase: IsoPreparePhase
    progress_pct: int | None = None
    current_file: str | None = None
    updated_at: datetime
