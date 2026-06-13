from typing import Literal

from pydantic import BaseModel, Field

MetadataProvider = Literal["omdb", "tmdb", "tvdb", "makemkv"]


class MetadataKeyTestResponse(BaseModel):
    provider: MetadataProvider
    valid: bool
    detail: str | None = None


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
