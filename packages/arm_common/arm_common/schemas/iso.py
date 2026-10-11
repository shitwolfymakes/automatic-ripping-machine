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


class IsoFolderEntry(BaseModel):
    """One disc folder in the library (GET /api/iso/folders)."""

    path: str  # relative to the library; what POST /api/iso/rips takes
    name: str
    parent: str  # the path above it ("" at the library root)
    disc_type: Literal["bluray", "dvd"]
    ripping: bool = False


class IsoFolderListing(BaseModel):
    host_path: str
    entries: list[IsoFolderEntry]
    # The walk gave up before covering the whole library (folder budget).
    partial: bool = False


class IsoRipRequest(BaseModel):
    path: str = Field(min_length=1)  # relative to the library: an .iso file or a disc folder
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
