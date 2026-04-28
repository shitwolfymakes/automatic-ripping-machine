import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_service_token
from arm_backend.db import get_session
from arm_backend.metadata import MetadataDispatcher
from arm_backend.metadata.dispatcher import DISPATCH_TIMEOUT_SECONDS
from arm_backend.seeders import CONFIG_SINGLETON_ID
from arm_common import Config, Drive, DriveStatus, Job, JobStatus
from arm_common.schemas import IdentifyRequest, JobView, RegisterRequest

logger = logging.getLogger("arm_backend.routers.ripper")

router = APIRouter(
    prefix="/api/ripper",
    tags=["ripper"],
    dependencies=[Depends(require_service_token)],
)


def _get_dispatcher(request: Request) -> MetadataDispatcher:
    dispatcher: MetadataDispatcher = request.app.state.dispatcher
    return dispatcher


@router.post("/register", response_model=Drive)
async def register(req: RegisterRequest, session: AsyncSession = Depends(get_session)) -> Drive:
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

    drive = (await session.execute(select(Drive).where(col(Drive.id) == drive_id))).scalar_one()
    return drive


@router.post("/identify", response_model=Job)
async def identify(
    req: IdentifyRequest,
    session: AsyncSession = Depends(get_session),
    dispatcher: MetadataDispatcher = Depends(_get_dispatcher),
) -> Job:
    drive = (await session.execute(select(Drive).where(col(Drive.id) == req.drive_id))).scalar_one_or_none()
    if drive is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown drive_id: {req.drive_id}")

    cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one()

    scan = req.scan_result
    job = Job(
        drive_id=req.drive_id,
        disc_type=scan.disc_type,
        status=JobStatus.CREATED,
    )
    session.add(job)
    await session.flush()

    try:
        result = await asyncio.wait_for(
            dispatcher.identify(scan, cfg),
            timeout=DISPATCH_TIMEOUT_SECONDS,
        )
        timed_out = False
    except asyncio.TimeoutError:
        logger.info("identify dispatch_timeout job_id=%s", job.id)
        result = None
        timed_out = True

    if result is not None:
        job.title = result.title
        job.year = result.year
        job.metadata_json = result.payload
        job.status = JobStatus.IDENTIFIED
    else:
        diagnostic: dict[str, object] = {}
        if timed_out:
            diagnostic["dispatch_timeout"] = True
        if cfg.block_on_miss:
            job.status = JobStatus.AWAITING_USER_ID
            job.title = scan.volume_label
            if diagnostic:
                job.metadata_json = diagnostic
        else:
            job.status = JobStatus.IDENTIFIED
            job.title = scan.volume_label
            job.metadata_json = {"unidentified": True, **diagnostic}

    await session.commit()
    await session.refresh(job)
    logger.info("identify job_id=%s status=%s title=%s", job.id, job.status.value, job.title)
    return job


@router.get("/jobs/{job_id}", response_model=JobView)
async def get_job(job_id: str, session: AsyncSession = Depends(get_session)) -> Job:
    job = (await session.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")
    return job
