"""ISO-import scan: validate an ISO under the ingress root and suggest
title/year. Job creation is owned by the ripper register->identify flow (an ISO
is a Drive whose device_path is the iso path), so full ISO import — registering
the ISO as a drive and dispatching a ripper to it — is a separate follow-up.
This endpoint only validates + suggests metadata. Ports neu's POST /jobs/iso/scan."""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from arm_backend.auth import require_jwt
from arm_backend.config import settings
from arm_backend.iso_ingress import IngressError, parse_iso_filename, resolve_iso_path
from arm_common import User
from arm_common.schemas import IsoScanRequest, IsoScanResponse

router = APIRouter(prefix="/api/jobs/iso", tags=["iso"])


def _ingress_root(request: Request) -> str:
    # Tests inject app.state.iso_ingress_root; production reads settings.
    return getattr(request.app.state, "iso_ingress_root", settings.ISO_INGRESS_ROOT)


@router.post("/scan", response_model=IsoScanResponse)
async def scan_iso(
    req: IsoScanRequest,
    request: Request,
    _: User = Depends(require_jwt),
) -> IsoScanResponse:
    try:
        resolve_iso_path(_ingress_root(request), req.path)
    except IngressError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    title, year = parse_iso_filename(req.path)
    return IsoScanResponse(path=req.path, suggested_title=title, suggested_year=year, exists=True)
