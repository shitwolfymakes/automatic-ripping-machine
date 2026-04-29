import asyncio
import logging
from pathlib import Path

import httpx

from arm_common import Job, JobStatus, TrackStatus
from arm_common.schemas import JobView, RipStartResponse, ScanResult, TrackView
from arm_ripper.backend_client import BackendClient
from arm_ripper.rip import RipResult, rip_all
from arm_ripper.scan import ScanError, scan as scan_disc

logger = logging.getLogger("arm_ripper.job_controller")

POLL_INITIAL_SECONDS = 5.0
POLL_MAX_SECONDS = 30.0
IDENTIFY_RETRY_INITIAL_SECONDS = 1.0
IDENTIFY_RETRY_MAX_SECONDS = 30.0
PATCH_RETRY_INITIAL_SECONDS = 1.0
PATCH_RETRY_MAX_SECONDS = 30.0
EJECT_GRACE_SECONDS = 3.0
# After makemkvcon exits, the kernel takes up to ~5s to release exclusive
# access on the optical drive — `eject` then sees EBUSY on open(). The
# delay schedule below is "best-effort with growing patience"; a healthy
# rip that holds the device briefly resolves on attempt 2.
EJECT_RETRY_DELAYS = (0.0, 2.0, 5.0, 10.0)
EJECT_PROCESS_TIMEOUT = 15.0
RAW_ROOT = Path("/raw")


class JobController:
    """Drives one disc through scan → identify → rip → eject."""

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

        if job.status == JobStatus.AWAITING_USER_ID:
            resolved = await self._await_resolution(job.id)
            if resolved is None:
                return
            job.status = resolved.status

        if job.status != JobStatus.IDENTIFIED:
            logger.info("job %s in unexpected status %s; not ripping", job.id, job.status.value)
            return

        await self._run_rip(job, device_path)

    async def _identify_with_retry(self, scan_result: ScanResult) -> Job:
        delay = IDENTIFY_RETRY_INITIAL_SECONDS
        while True:
            try:
                return await self._client.identify(drive_id=self._drive_id, scan_result=scan_result)
            except httpx.HTTPError as e:
                logger.warning("identify failed (%s); retrying in %.1fs", e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, IDENTIFY_RETRY_MAX_SECONDS)

    async def _await_resolution(self, job_id: str) -> JobView | None:
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
                return view
            if view.status != JobStatus.AWAITING_USER_ID:
                logger.info("job %s left awaiting_user_id with status=%s; abandoning poll", job_id, view.status.value)
                return None
            delay = min(delay * 2, POLL_MAX_SECONDS) if delay < POLL_MAX_SECONDS else POLL_MAX_SECONDS

    async def _run_rip(self, job: Job, device_path: str) -> None:
        rip_start = await self._rip_start_with_retry(job.id)
        logger.info(
            "rip-start job_id=%s preset=%s tracks=%d",
            job.id,
            rip_start.rip_preset_id,
            len(rip_start.tracks),
        )

        output_dir = RAW_ROOT / job.id
        output_dir.mkdir(parents=True, exist_ok=True)

        async def on_track_start(track: TrackView) -> None:
            if track.status != TrackStatus.QUEUED:
                return
            await self._patch_track_with_retry(track.id, status=TrackStatus.IN_PROGRESS)

        async def on_track_done(track: TrackView, result: RipResult) -> None:
            if result.ok:
                fields: dict[str, object] = {"status": TrackStatus.DONE}
                if result.output_path is not None:
                    fields["output_path"] = str(result.output_path)
                if result.size_bytes is not None:
                    fields["size_bytes"] = result.size_bytes
                if result.sha256 is not None:
                    fields["sha256"] = result.sha256
                if result.duration_seconds is not None:
                    fields["duration_seconds"] = result.duration_seconds
                await self._patch_track_with_retry(track.id, **fields)
                logger.info(
                    "track %s done size=%s duration=%s",
                    track.id,
                    result.size_bytes,
                    result.duration_seconds,
                )
            else:
                await self._patch_track_with_retry(
                    track.id,
                    status=TrackStatus.FAILED,
                    last_error=result.error or "unknown error",
                )
                logger.warning("track %s failed err=%s", track.id, result.error)

        async def on_track_progress(track: TrackView, fraction: float) -> None:
            logger.debug("track %s progress=%.2f", track.id, fraction)

        await rip_all(
            disc_type=job.disc_type,
            device_path=device_path,
            tracks=list(rip_start.tracks),
            output_dir=output_dir,
            on_track_start=on_track_start,
            on_track_done=on_track_done,
            on_track_progress=on_track_progress,
        )

        completed = await self._rip_complete_with_retry(job.id)
        logger.info("rip-complete job_id=%s status=%s", job.id, completed.status.value)

        await self._eject_with_retry(device_path)
        await asyncio.sleep(EJECT_GRACE_SECONDS)

    async def _eject_with_retry(self, device_path: str) -> None:
        """Auto-eject with retries; non-fatal — logs but never raises.

        Two failure modes we have to tolerate:
        - EBUSY immediately post-rip while the kernel still holds the
          device for makemkvcon's close. Retries with growing delay clear
          this. (See EJECT_RETRY_DELAYS.)
        - The host (typical desktop with udisks2/gvfs) auto-mounted the
          disc behind our back. We cannot unmount the host's mount from
          inside the container, so the retries will all fail. Document
          host-side disable in [06-deployment.md].

        Best-effort `umount` first matches v2's eject() pattern — covers
        the case where a sibling container or the ripper's own
        scan-poster path mounted the device internally.
        """
        await self._run_command("umount", device_path, log_failure=False)
        for attempt, delay in enumerate(EJECT_RETRY_DELAYS, start=1):
            if delay > 0:
                await asyncio.sleep(delay)
            rc, stderr = await self._run_command("eject", "-sv", device_path)
            if rc == 0:
                logger.info("ejected %s on attempt %d", device_path, attempt)
                return
            logger.warning(
                "eject %s attempt %d failed (rc=%s): %s",
                device_path,
                attempt,
                rc,
                stderr or "<no stderr>",
            )

        logger.error(
            "eject %s failed after %d attempts; check host auto-mount config",
            device_path,
            len(EJECT_RETRY_DELAYS),
        )

    @staticmethod
    async def _run_command(*argv: str, log_failure: bool = True) -> tuple[int | None, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, OSError) as e:
            if log_failure:
                logger.warning("%s errored: %s", argv[0], e)
            return None, str(e)
        try:
            _, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=EJECT_PROCESS_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            if log_failure:
                logger.warning("%s timed out", argv[0])
            return None, "timeout"
        return proc.returncode, stderr_b.decode(errors="replace").strip()

    async def _rip_start_with_retry(self, job_id: str) -> RipStartResponse:
        delay = PATCH_RETRY_INITIAL_SECONDS
        while True:
            try:
                return await self._client.rip_start(job_id)
            except httpx.HTTPError as e:
                logger.warning("rip-start %s failed (%s); retrying in %.1fs", job_id, e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, PATCH_RETRY_MAX_SECONDS)

    async def _rip_complete_with_retry(self, job_id: str) -> JobView:
        delay = PATCH_RETRY_INITIAL_SECONDS
        while True:
            try:
                return await self._client.rip_complete(job_id)
            except httpx.HTTPError as e:
                logger.warning("rip-complete %s failed (%s); retrying in %.1fs", job_id, e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, PATCH_RETRY_MAX_SECONDS)

    async def _patch_track_with_retry(self, track_id: str, **fields: object) -> None:
        delay = PATCH_RETRY_INITIAL_SECONDS
        while True:
            try:
                await self._client.update_track(track_id, **fields)
                return
            except httpx.HTTPError as e:
                logger.warning("PATCH track %s failed (%s); retrying in %.1fs", track_id, e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, PATCH_RETRY_MAX_SECONDS)
