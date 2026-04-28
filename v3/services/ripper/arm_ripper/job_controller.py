import asyncio
import logging

import httpx

from arm_common import Job, JobStatus
from arm_common.schemas import ScanResult
from arm_ripper.backend_client import BackendClient
from arm_ripper.scan import ScanError, scan as scan_disc

logger = logging.getLogger("arm_ripper.job_controller")

POLL_INITIAL_SECONDS = 5.0
POLL_MAX_SECONDS = 30.0
IDENTIFY_RETRY_INITIAL_SECONDS = 1.0
IDENTIFY_RETRY_MAX_SECONDS = 30.0


class JobController:
    """Drives one disc through scan → identify → (optional) await-resolve."""

    def __init__(self, client: BackendClient, drive_id: str) -> None:
        self._client = client
        self._drive_id = drive_id

    async def handle_disc_inserted(self, device_path: str) -> None:
        try:
            scan_result = await scan_disc(device_path)
        except ScanError as e:
            logger.error("scan failed device=%s err=%s", device_path, e)
            return

        job = await self._identify_with_retry(scan_result)

        if job.status == JobStatus.IDENTIFIED:
            logger.info("job %s identified, ready for rip (Phase 3)", job.id)
            return
        if job.status == JobStatus.AWAITING_USER_ID:
            await self._await_resolution(job.id)
            return

        logger.info("job %s in unexpected status %s after identify", job.id, job.status.value)

    async def _identify_with_retry(self, scan_result: ScanResult) -> Job:
        delay = IDENTIFY_RETRY_INITIAL_SECONDS
        while True:
            try:
                return await self._client.identify(drive_id=self._drive_id, scan_result=scan_result)
            except httpx.HTTPError as e:
                logger.warning("identify failed (%s); retrying in %.1fs", e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, IDENTIFY_RETRY_MAX_SECONDS)

    async def _await_resolution(self, job_id: str) -> None:
        logger.info("job %s awaiting_user_id; polling for resolve", job_id)
        delay = POLL_INITIAL_SECONDS
        while True:
            await asyncio.sleep(delay)
            try:
                view = await self._client.get_job(job_id)
            except httpx.HTTPError as e:
                logger.warning("get_job %s failed (%s); retrying in %.1fs", job_id, e, delay)
                delay = min(delay * 2, POLL_MAX_SECONDS)
                continue

            if view.status == JobStatus.IDENTIFIED:
                logger.info("job %s resolved -> identified title=%s", job_id, view.title)
                return
            if view.status != JobStatus.AWAITING_USER_ID:
                logger.info("job %s left awaiting_user_id with status=%s; abandoning poll", job_id, view.status.value)
                return
            delay = min(delay * 2, POLL_MAX_SECONDS) if delay < POLL_MAX_SECONDS else POLL_MAX_SECONDS
