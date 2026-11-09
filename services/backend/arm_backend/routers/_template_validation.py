"""Path-template validation for the routers: a template that fails validation answers HTTP 422."""

from fastapi import HTTPException, status

from arm_backend.path_template import TemplateValidationError, validate_template
from arm_common.enums import MediaType


def validate_template_or_http(template: str, media_type: MediaType, has_transcode_preset: bool) -> str:
    """Validate a template; raise FastAPI HTTPException(422) on failure.

    Shared by the sessions-preview and naming routers so the validate->422
    behaviour lives in exactly one place. Returns the synthetic expansion.
    """
    try:
        return validate_template(template, media_type, has_transcode_preset)
    except TemplateValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
