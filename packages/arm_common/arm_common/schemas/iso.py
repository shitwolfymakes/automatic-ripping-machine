from pydantic import BaseModel, Field


class IsoScanRequest(BaseModel):
    path: str = Field(min_length=1)


class IsoScanResponse(BaseModel):
    path: str
    suggested_title: str
    suggested_year: int | None
    exists: bool
