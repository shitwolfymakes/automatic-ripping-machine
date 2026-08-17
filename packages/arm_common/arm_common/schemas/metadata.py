from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

MetadataProvider = Literal["omdb", "tmdb", "tvdb", "makemkv"]


class MetadataKeyTestResponse(BaseModel):
    provider: MetadataProvider
    valid: bool | None  # tri-state: True/False, or None = "unknown" (makemkv not-yet-checked / probe failed)
    detail: str | None = None
    checked_at: datetime | None = None  # when the makemkv probe last ran; None for live-checked providers


class MetadataCandidate(BaseModel):
    title: str
    year: int | None = None
    kind: str
    poster_url: str | None = None
    provider_id: str | None = None


class MetadataReleaseTrack(BaseModel):
    position: int | None = None
    title: str


class MetadataReleaseDetail(BaseModel):
    release_id: str
    title: str
    artist: str | None = None
    year: int | None = None
    poster_url: str | None = None
    tracks: list[MetadataReleaseTrack] = Field(default_factory=list)


class MetadataSearchResponse(BaseModel):
    candidates: list[MetadataCandidate]
    detail: str | None = None
