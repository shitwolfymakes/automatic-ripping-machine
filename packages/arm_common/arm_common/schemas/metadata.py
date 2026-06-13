from typing import Literal

from pydantic import BaseModel

MetadataProvider = Literal["omdb", "tmdb", "tvdb", "makemkv"]


class MetadataKeyTestResponse(BaseModel):
    provider: MetadataProvider
    valid: bool
    detail: str | None = None
