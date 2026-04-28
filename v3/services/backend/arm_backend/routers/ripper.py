from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_service_token
from arm_backend.db import get_session
from arm_common import Drive, DriveStatus, Job, JobStatus
from arm_common.schemas import (
    IdentifyRequest,
    IdentifyResponse,
    RegisterRequest,
    RegisterResponse,
)

router = APIRouter(
    prefix="/api/ripper",
    tags=["ripper"],
    dependencies=[Depends(require_service_token)],
)


@router.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest, session: AsyncSession = Depends(get_session)) -> RegisterResponse:
    stmt = (
        pg_insert(Drive)
        .values(
            hostname=req.hostname,
            device_path=req.device_path,
            status=DriveStatus.ONLINE.value,
        )
        .on_conflict_do_update(
            index_elements=[col(Drive.hostname)],
            set_={
                "device_path": req.device_path,
                "status": DriveStatus.ONLINE.value,
            },
        )
        .returning(col(Drive.id))
    )
    result = await session.execute(stmt)
    drive_id = result.scalar_one()
    await session.commit()
    return RegisterResponse(drive_id=drive_id, drive_config={}, service_token_verified=True)


@router.post("/identify", response_model=IdentifyResponse)
async def identify(req: IdentifyRequest, session: AsyncSession = Depends(get_session)) -> IdentifyResponse:
    drive = (await session.execute(select(Drive).where(col(Drive.id) == req.drive_id))).scalar_one_or_none()
    if drive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {req.drive_id}")

    job = Job(drive_id=req.drive_id, disc_type=req.disc_type, status=JobStatus.CREATED)
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return IdentifyResponse(job_id=job.id, status=JobStatus.CREATED)
