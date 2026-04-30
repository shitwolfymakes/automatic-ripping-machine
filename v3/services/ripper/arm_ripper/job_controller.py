import asyncio
import logging
from pathlib import Path

import httpx

from arm_common import DiscType, Job, JobStatus, TrackStatus
from arm_common.schemas import JobView, RipStartResponse, ScanResult, TrackView, WSEnvelope
from arm_ripper.backend_client import BackendClient
from arm_ripper.rip import RipResult, rip_all
from arm_ripper.scan import ScanError, scan as scan_disc
from arm_ripper.ws_client import WSClient

logger = logging.getLogger("arm_ripper.job_controller")

POLL_INITIAL_SECONDS = 5.0
POLL_MAX_SECONDS = 30.0
IDENTIFY_RETRY_INITIAL_SECONDS = 1.0
IDENTIFY_RETRY_MAX_SECONDS = 30.0
PATCH_RETRY_INITIAL_SECONDS = 1.0
PATCH_RETRY_MAX_SECONDS = 30.0
EJECT_GRACE_SECONDS = 3.0
# Hard ceiling on awaiting_user_id wait; if no WS event arrives by then,
# fall back to one REST GET to handle a stale-WS edge case (boot race or
# extended outage). Beyond that, we assume the user abandoned the disc
# and return — the next disc-insert event re-triggers identify.
RESOLUTION_WAIT_TIMEOUT_SECONDS = 30 * 60.0
RESOLUTION_WS_FIRST_WAIT_SECONDS = 5.0
# After makemkvcon exits, the kernel takes up to ~5s to release exclusive
# access on the optical drive — `eject` then sees EBUSY on open(). The
# delay schedule below is "best-effort with growing patience"; a healthy
# rip that holds the device briefly resolves on attempt 2.
EJECT_RETRY_DELAYS = (0.0, 2.0, 5.0, 10.0)
EJECT_PROCESS_TIMEOUT = 15.0
RAW_ROOT = Path("/raw")


class JobController:
    """Drives one disc through scan → identify → rip → eject."""

    def __init__(self, client: BackendClient, drive_id: str, *, ws: WSClient | None = None) -> None:
        self._client = client
        self._drive_id = drive_id
        self._ws = ws
        # job_id → asyncio.Event signalled when an `identify.resolved`
        # arrives over WS. Populated by `_await_resolution`, drained by
        # `on_ws_command`.
        self._resolution_events: dict[str, asyncio.Event] = {}

    async def on_ws_command(self, envelope: WSEnvelope) -> None:
        """Handler registered for `ripper.commands.{drive_id}` topic."""
        if envelope.event_type == "identify.resolved":
            job_id = envelope.payload.get("job_id") if isinstance(envelope.payload, dict) else None
            if not isinstance(job_id, str):
                logger.warning("identify.resolved without job_id payload: %s", envelope.payload)
                return
            event = self._resolution_events.get(job_id)
            if event is not None:
                event.set()
                logger.info("ws identify.resolved received for job_id=%s", job_id)
            else:
                logger.debug("identify.resolved for job_id=%s but no waiter registered", job_id)
        else:
            logger.debug("ws command ignored: type=%s", envelope.event_type)

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
        """Wait for the user to resolve identity.

        Primary path: the resolution arrives via WS (`identify.resolved`
        on `ripper.commands.{drive_id}`); we park on an asyncio.Event
        keyed by job_id and the WS handler sets it.

        Fallback path: if no WS event arrives within
        RESOLUTION_WS_FIRST_WAIT_SECONDS, do one REST get_job to cover
        the boot-race case where the disc landed `awaiting_user_id`
        before WSClient finished its handshake. After that, fall back
        to slow polling so an extended WS outage doesn't strand a job.
        """
        logger.info("job %s awaiting_user_id; waiting for resolve", job_id)
        event = asyncio.Event()
        self._resolution_events[job_id] = event
        try:
            return await self._wait_for_resolution(job_id, event)
        finally:
            self._resolution_events.pop(job_id, None)

    async def _wait_for_resolution(self, job_id: str, event: asyncio.Event) -> JobView | None:
        # First-wait window: covers the boot race where we missed the
        # resolve-event broadcast before subscribing.
        try:
            await asyncio.wait_for(event.wait(), timeout=RESOLUTION_WS_FIRST_WAIT_SECONDS)
        except asyncio.TimeoutError:
            view = await self._safe_get_job(job_id)
            if view is not None:
                if view.status == JobStatus.IDENTIFIED:
                    logger.info("job %s resolved (REST fallback) title=%s", job_id, view.title)
                    return view
                if view.status != JobStatus.AWAITING_USER_ID:
                    logger.info(
                        "job %s left awaiting_user_id with status=%s; abandoning",
                        job_id,
                        view.status.value,
                    )
                    return None

        # Long wait: WS-driven, with periodic REST sanity polls so we
        # don't hang forever on a torn WS connection.
        deadline = asyncio.get_event_loop().time() + RESOLUTION_WAIT_TIMEOUT_SECONDS
        while asyncio.get_event_loop().time() < deadline:
            try:
                await asyncio.wait_for(event.wait(), timeout=POLL_MAX_SECONDS)
                # WS event fired — confirm via REST.
                view = await self._safe_get_job(job_id)
                if view is None:
                    return None
                if view.status == JobStatus.IDENTIFIED:
                    logger.info("job %s resolved -> identified title=%s", job_id, view.title)
                    return view
                if view.status != JobStatus.AWAITING_USER_ID:
                    logger.info(
                        "job %s left awaiting_user_id with status=%s; abandoning",
                        job_id,
                        view.status.value,
                    )
                    return None
                # Spurious WS wake — clear and re-arm.
                event.clear()
            except asyncio.TimeoutError:
                # Periodic sanity poll — handles torn WS connections.
                view = await self._safe_get_job(job_id)
                if view is None:
                    continue
                if view.status == JobStatus.IDENTIFIED:
                    logger.info("job %s resolved (poll catch-up) title=%s", job_id, view.title)
                    return view
                if view.status != JobStatus.AWAITING_USER_ID:
                    logger.info(
                        "job %s left awaiting_user_id with status=%s; abandoning",
                        job_id,
                        view.status.value,
                    )
                    return None

        logger.warning("job %s resolution timed out after %.0fs", job_id, RESOLUTION_WAIT_TIMEOUT_SECONDS)
        return None

    async def _safe_get_job(self, job_id: str) -> JobView | None:
        try:
            return await self._client.get_job(job_id)
        except httpx.HTTPError as e:
            logger.warning("get_job %s failed (%s); will retry on next signal", job_id, e)
            return None

    async def _run_rip(self, job: Job, device_path: str) -> None:
        rip_start = await self._rip_start_with_retry(job.id)
        logger.info(
            "rip-start job_id=%s preset=%s tracks=%d",
            job.id,
            rip_start.rip_preset_id,
            len(rip_start.tracks),
        )
        await self._execute_rip(
            job_id=job.id,
            disc_type=job.disc_type,
            device_path=device_path,
            rip_start=rip_start,
        )

    async def resume_inflight_job(self, job: JobView, device_path: str) -> None:
        """Phase 9 — drive a crash-recovered rip from the boot probe.

        The backend's `/resume` endpoint resets tracks to QUEUED and
        sets `resumed_from_crash=True`; we then run the same rip-loop
        as a fresh disc would.
        """
        rip_start = await self._client.resume(job.id)
        logger.info("rip-resume job_id=%s tracks=%d", job.id, len(rip_start.tracks))
        await self._execute_rip(
            job_id=job.id,
            disc_type=job.disc_type,
            device_path=device_path,
            rip_start=rip_start,
        )

    async def _execute_rip(
        self,
        *,
        job_id: str,
        disc_type: DiscType,
        device_path: str,
        rip_start: RipStartResponse,
    ) -> None:
        output_dir = RAW_ROOT / job_id
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
            if self._ws is not None:
                await self._ws.publish(
                    topic=f"ripper.progress.{job_id}",
                    event_type="ripper.progress",
                    payload={
                        "track_id": track.id,
                        "progress_pct": round(fraction * 100, 1),
                    },
                )

        await rip_all(
            disc_type=disc_type,
            device_path=device_path,
            tracks=list(rip_start.tracks),
            output_dir=output_dir,
            on_track_start=on_track_start,
            on_track_done=on_track_done,
            on_track_progress=on_track_progress,
        )

        completed = await self._rip_complete_with_retry(job_id)
        logger.info("rip-complete job_id=%s status=%s", job_id, completed.status.value)

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
