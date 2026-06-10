from pydantic import BaseModel


class NamingVariable(BaseModel):
    token: str
    description: str


class NamingVariablesResponse(BaseModel):
    # keyed by media_type value, e.g. {"movie": [...], "tv": [...]}
    variables: dict[str, list[NamingVariable]]


class NamingPreviewItem(BaseModel):
    track_id: str
    filename: str


class JobNamingPreviewResponse(BaseModel):
    items: list[NamingPreviewItem]
