from pydantic import BaseModel, Field

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
    # Constraints/defaults mirror TemplatePreviewRequest and the session save
    # path (min_length=1; has_transcode_preset=True) so the same template
    # cannot validate here and then fail at save/preview.
    template: str = Field(min_length=1)
    media_type: MediaType
    has_transcode_preset: bool = True


class NamingValidateResponse(BaseModel):
    valid: bool


class NamingPreviewRequest(BaseModel):
    template: str
    media_type: MediaType
    has_transcode_preset: bool = False
    variables: dict[str, str] = {}


class NamingPreviewResponse(BaseModel):
    rendered: str
