"""The background MakeMKV title read of a disc whose review card was posted from the playlist structure.

The structure read gives the card in seconds; `makemkvcon info` then runs while the operator reviews, to name
MakeMKV's own title numbers and to prove it can decrypt the disc. Its outcome goes to the backend either way
(`POST /api/ripper/jobs/{id}/titles`), and a rip waits for it (`wait`).
"""

import asyncio
import contextlib
import logging

import httpx

from arm_common import ScanFailureReason
from arm_common.schemas import ScanFailure, TitlesReport
from arm_ripper.backend_retry import BackendRetry
from arm_ripper.scan.makemkv import MakemkvScanFailed, ScanError, scan_titles

logger = logging.getLogger("arm_ripper.titles_read")

NO_TITLES_FAILURE = "MakeMKV listed no titles on this disc"


class TitlesRead:
    """One background title read per job: started after identify, awaited before the rip."""

    def __init__(self, backend: BackendRetry) -> None:
        self._backend = backend
        self._tasks: dict[str, asyncio.Task[bool]] = {}

    def start(self, job_id: str, device_path: str, min_title_length_seconds: int, timeout_seconds: float) -> None:
        """Begin reading MakeMKV's titles for the job, down to the minimum its scan recorded and within the drive's
        scan ceiling; a read still running for it is replaced."""
        previous = self._tasks.get(job_id)
        if previous is not None:
            previous.cancel()
        self._tasks[job_id] = asyncio.create_task(
            self._read(job_id, device_path, min_title_length_seconds, timeout_seconds)
        )

    async def wait(self, job_id: str) -> bool:
        """True when MakeMKV's titles are posted or no read is in flight for the job; False when the read failed (its
        reason is already on the job)."""
        task = self._tasks.get(job_id)
        return True if task is None else await task

    async def cancel(self, job_id: str) -> None:
        """Stop the job's read (killing its makemkvcon) and forget it."""
        task = self._tasks.pop(job_id, None)
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _read(self, job_id: str, device_path: str, min_title_length_seconds: int, timeout_seconds: float) -> bool:
        report = await self._report(device_path, min_title_length_seconds, timeout_seconds)
        try:
            await self._backend.post_titles(job_id, report)
        except httpx.HTTPStatusError as e:
            logger.warning("titles post for %s rejected by the backend (%s)", job_id, e)
            return False
        return report.failure is None

    @staticmethod
    async def _report(device_path: str, min_title_length_seconds: int, timeout_seconds: float) -> TitlesReport:
        try:
            titles = await scan_titles(device_path, min_title_length_seconds, timeout_seconds=timeout_seconds)
        except MakemkvScanFailed as e:
            logger.warning("makemkv title read failed device=%s reason=%s err=%s", device_path, e.reason.value, e)
            return TitlesReport(failure=ScanFailure(reason=e.reason, detail=e.detail, output_tail=list(e.tail)))
        except (ScanError, OSError) as e:
            logger.warning("makemkv title read failed device=%s err=%s", device_path, e)
            return TitlesReport(failure=ScanFailure(reason=ScanFailureReason.MAKEMKV_ERROR, detail=str(e)))
        if not titles:
            logger.warning("makemkv listed no titles device=%s", device_path)
            return TitlesReport(failure=ScanFailure(reason=ScanFailureReason.MAKEMKV_ERROR, detail=NO_TITLES_FAILURE))
        return TitlesReport(titles=titles)
