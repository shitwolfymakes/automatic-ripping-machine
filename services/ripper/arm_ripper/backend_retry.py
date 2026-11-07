"""The backend calls a rip makes, each retried through transient failures."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

from arm_common import Job
from arm_common.schemas import JobView, RipStartResponse, ScanResult
from arm_ripper.backend_client import BackendClient

# Same logger name the calls had in job_controller, so log records and caplog filters are unchanged.
logger = logging.getLogger("arm_ripper.job_controller")

IDENTIFY_RETRY_INITIAL_SECONDS = 1.0
IDENTIFY_RETRY_MAX_SECONDS = 30.0
PATCH_RETRY_INITIAL_SECONDS = 1.0
PATCH_RETRY_MAX_SECONDS = 30.0


class BackendRetry:
    """The backend calls a rip makes, each retried through transient failures (transport errors and 5xx), with a
    rejection (4xx) re-raised."""

    def __init__(self, client: BackendClient, drive_id: str) -> None:
        self._client = client
        self._drive_id = drive_id

    @staticmethod
    def is_retryable(exc: httpx.HTTPError) -> bool:
        """A 4xx response is the backend telling us the request itself
        is wrong (validation error, missing job, conflict). Retrying
        won't fix it and will keep hammering the backend forever — so
        bail. Transport errors and 5xx responses are transient and
        should keep retrying with backoff."""
        if isinstance(exc, httpx.HTTPStatusError) and 400 <= exc.response.status_code < 500:
            return False
        return True

    async def call[T](self, call: Callable[[], Awaitable[T]], what: str) -> T:
        """Run one backend call, retrying a transient failure with doubling backoff up to PATCH_RETRY_MAX_SECONDS and
        re-raising a rejection."""
        delay = PATCH_RETRY_INITIAL_SECONDS
        while True:
            try:
                return await call()
            except httpx.HTTPError as e:
                if not self.is_retryable(e):
                    logger.error("%s rejected by backend (%s); giving up", what, e)
                    raise
                logger.warning("%s failed (%s); retrying in %.1fs", what, e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, PATCH_RETRY_MAX_SECONDS)

    async def rip_start(self, job_id: str) -> RipStartResponse:
        """Mark the job ripping on the backend, retrying a transient failure."""
        return await self.call(lambda: self._client.rip_start(job_id), f"rip-start {job_id}")

    async def rip_complete(self, job_id: str) -> JobView:
        """Mark the job's rip complete on the backend, retrying a transient failure."""
        return await self.call(lambda: self._client.rip_complete(job_id), f"rip-complete {job_id}")

    async def patch_track(self, track_id: str, **fields: object) -> None:
        """PATCH one track's fields on the backend, retrying a transient failure."""
        await self.call(lambda: self._client.update_track(track_id, **fields), f"PATCH track {track_id}")

    async def identify(
        self,
        scan_result: ScanResult,
        *,
        pending_session_id: str | None = None,
    ) -> Job:
        """Identify the scanned disc, retrying a transient failure and re-raising a 4xx other than 429."""
        delay = IDENTIFY_RETRY_INITIAL_SECONDS
        while True:
            try:
                return await self._client.identify(
                    drive_id=self._drive_id,
                    scan_result=scan_result,
                    pending_session_id=pending_session_id,
                )
            except httpx.HTTPError as e:
                status_code = e.response.status_code if isinstance(e, httpx.HTTPStatusError) else None
                if status_code is not None and 400 <= status_code < 500 and status_code != 429:
                    # Non-retriable client error (e.g. 409 ripping-paused). Retrying
                    # spins forever holding _active_lock and deadlocks the drive —
                    # re-raise so the pipeline exits and the lock releases.
                    logger.warning(
                        "identify rejected (%s) for drive %s — not retriable; parking pipeline",
                        status_code,
                        self._drive_id,
                    )
                    raise
                logger.warning("identify failed (%s); retrying in %.1fs", e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, IDENTIFY_RETRY_MAX_SECONDS)
