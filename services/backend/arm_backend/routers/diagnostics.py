"""Read-only diagnostics surface for the UI.

Per-job log download lives on the logs router (`/api/logs/{job_id}.zip`)
— this endpoint stays scope-agnostic and just reports per-service log
levels.
"""

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
    )
