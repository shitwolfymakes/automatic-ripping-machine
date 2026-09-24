from typing import Literal

from pydantic import BaseModel, Field

MetadataProvider = Literal["omdb", "tmdb", "tvdb", "makemkv"]


class MetadataCandidate(BaseModel):
    title: str
    year: int | None = None
    kind: str
    poster_url: str | None = None
    provider_id: str | None = None
    release_type: str | None = None
    format: str | None = None
    country: str | None = None
    status: str | None = None
    track_count: int | None = None


class MetadataReleaseTrack(BaseModel):
    position: int | None = None
    title: str
    length_ms: int | None = None
    disc_number: int | None = None


class MetadataReleaseDetail(BaseModel):
    release_id: str
    title: str
    artist: str | None = None
    year: int | None = None
    poster_url: str | None = None
    catalog_number: str | None = None
    barcode: str | None = None
    country: str | None = None
    format: str | None = None
    status: str | None = None
    disc_count: int | None = None
    track_count: int | None = None
    tracks: list[MetadataReleaseTrack] = Field(default_factory=list)


class MetadataSearchResponse(BaseModel):
    candidates: list[MetadataCandidate]
    detail: str | None = None
