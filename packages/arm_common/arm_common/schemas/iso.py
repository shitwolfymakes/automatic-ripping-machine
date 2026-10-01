"""Wire schemas for `/api/iso` (Rip from ISO, spec 2026-09-30 section 5/6):
the library listing and the create-rip request/response."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
