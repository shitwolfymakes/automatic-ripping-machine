from pydantic import BaseModel

from arm_common.enums import MediaType


class NamingVariable(BaseModel):
    token: str
    description: str


class NamingVariablesResponse(BaseModel):
    # keyed by media_type value, e.g. {"movie": [...], "tv": [...]}
    variables: dict[str, list[NamingVariable]]


class NamingPreviewItem(BaseModel):
    track_id: str
    track_number: int | None = None
    output_path: str
    output_dir: str
    output_name: str


class JobNamingPreviewResponse(BaseModel):
    job_output_dir: str
    job_output_name: str
    items: list[NamingPreviewItem]


class NamingValidateRequest(BaseModel):
    template: str
    media_type: MediaType
    has_transcode_preset: bool = False


class NamingValidateResponse(BaseModel):
    valid: bool
