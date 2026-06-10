from typing import Literal

from pydantic import BaseModel

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


class MetadataSearchResponse(BaseModel):
    candidates: list[MetadataCandidate]
    detail: str | None = None
