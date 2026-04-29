"""Read-only diagnostics surface for the UI. Phase 12 will enrich it."""

from fastapi import APIRouter, Depends

from arm_backend.auth import require_jwt
from arm_backend.config import settings
from arm_common import User
from arm_common.schemas import DiagnosticsResponse, DiagnosticsServiceView

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


@router.get("", response_model=DiagnosticsResponse)
async def get_diagnostics(_: User = Depends(require_jwt)) -> DiagnosticsResponse:
    return DiagnosticsResponse(
        services=[DiagnosticsServiceView(name="arm-backend", log_level=settings.ARM_LOG_LEVEL)],
        bug_report_zip_url=None,  # Phase 12
    )
