import asyncio
import logging
import shutil
from pathlib import Path

import httpx

from arm_common import DiscType, Job, JobStatus, TrackStatus, with_log_context
from arm_common.schemas import JobView, RipStartResponse, ScanResult, TrackView, WSEnvelope
from arm_ripper.backend_client import BackendClient
from arm_ripper.makemkv_key import refresh_makemkv_key
from arm_ripper.rip import RipResult, rip_all
from arm_ripper.rip.dispatcher import DEFAULT_MIN_LENGTH_SECONDS
from arm_ripper.scan import ScanError, scan as scan_disc
from arm_ripper.source import is_iso_source
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

    def __init__(
        self,
        client: BackendClient,
        drive_id: str,
        *,
        ws: WSClient | None = None,
        device_path: str | None = None,
        default_min_length_seconds: int = DEFAULT_MIN_LENGTH_SECONDS,
    ) -> None:
        self._client = client
        self._drive_id = drive_id
        self._ws = ws
        # Each ripper container owns exactly one optical drive; storing the
        # device path here lets `handle_manual_trigger` run without re-reading
        # settings (which a unit test environment may not have populated).
        self._device_path = device_path
        # Host-side baseline `--minlength` for `makemkvcon mkv all`. The
        # backend can override per-rip via `RipStartResponse.min_length_seconds`
        # (resolved from the Session's `overrides_json["min_length_seconds"]`);
        # when no override is sent we fall back to this value. Injected by
        # `main.py` from `ARM_MIN_LENGTH_SECONDS`; tests get the dispatcher
        # default (600).
        self._default_min_length_seconds = default_min_length_seconds
        # job_id → asyncio.Event signalled when an `identify.resolved`
        # arrives over WS. Populated by `_await_resolution`, drained by
        # `on_ws_command`.
        self._resolution_events: dict[str, asyncio.Event] = {}
        # Single-flight gate: only one rip pipeline (insert-driven OR manual-
        # trigger) runs at a time per drive. Ensures the WS-triggered manual
        # path can't race with an in-progress disc-inserted task.
        self._active_lock = asyncio.Lock()
        # Backend abandons a job by emitting `job.abandoned` over WS; the
        # handler cancels this task to kill the running makemkvcon and free
        # the raw dir for cleanup. Set inside `_run_pipeline` only.
        self._active_task: asyncio.Task[None] | None = None
        self._active_job_id: str | None = None

    @property
    def is_active(self) -> bool:
        return self._active_lock.locked()

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
        elif envelope.event_type == "manual.trigger":
            payload = envelope.payload if isinstance(envelope.payload, dict) else {}
            session_id = payload.get("session_id")
            if session_id is not None and not isinstance(session_id, str):
                logger.warning("manual.trigger with non-string session_id: %r", session_id)
                session_id = None
            asyncio.create_task(self.handle_manual_trigger(session_id))
        elif envelope.event_type == "job.abandoned":
            payload = envelope.payload if isinstance(envelope.payload, dict) else {}
            job_id = payload.get("job_id")
            delete_raw = bool(payload.get("delete_raw"))
            if not isinstance(job_id, str):
                logger.warning("job.abandoned without job_id payload: %s", payload)
                return
            self._handle_abandon(job_id, delete_raw=delete_raw)
            # Also wake any `_await_resolution` waiter — abandoning a parked
            # job needs to unstick the pipeline the same way `identify.resolved`
            # does. The waiter polls and decides based on the new job status.
            event = self._resolution_events.get(job_id)
            if event is not None:
                event.set()
        else:
            logger.debug("ws command ignored: type=%s", envelope.event_type)

    def _handle_abandon(self, job_id: str, *, delete_raw: bool) -> None:
        """Cancel the active pipeline if it owns this job, then optionally
        wipe `/raw/<job_id>/`. Runs synchronously from the WS handler;
        cancel + rmtree are both fast and don't need awaitable plumbing.

        rmtree on Linux is safe even if makemkvcon still has file handles
        open: the directory entries are removed, existing fds keep working
        (writing to nowhere) until the cancelled subprocess dies.
        """
        if self._active_job_id == job_id and self._active_task is not None and not self._active_task.done():
            logger.info("job.abandoned: cancelling active task for job_id=%s", job_id)
            self._active_task.cancel()
        if delete_raw:
            target = RAW_ROOT / job_id
            try:
                shutil.rmtree(target)
                logger.info("wiped raw dir job_id=%s path=%s", job_id, target)
            except FileNotFoundError:
                logger.info("raw dir already absent job_id=%s path=%s", job_id, target)
            except OSError as exc:
                logger.warning("raw-dir cleanup failed job_id=%s path=%s: %s", job_id, target, exc)

    async def handle_manual_trigger(self, session_id: str | None) -> None:
        """Run the normal scan→identify→rip flow on demand, threading
        `session_id` (if any) into identify so it lands on the Job's
        metadata as `pending_session_id`. Caller is the WS dispatcher,
        which fires-and-forgets; we own all error handling.
        """
        if self.is_active:
            logger.info("manual.trigger ignored: drive busy with another rip")
            return
        if self._device_path is None:
            logger.warning("manual.trigger ignored: no device_path bound to controller")
            return
        await self._run_pipeline(self._device_path, pending_session_id=session_id)

    async def handle_disc_inserted(self, device_path: str) -> None:
        if self.is_active:
            logger.debug("disc-inserted ignored: drive already busy")
            return
        # Auto-rip-on-insert is the global Config switch; default true so
        # this is a no-op on standard deployments. Fail-open on lookup
        # error: a flapping backend must not silently halt ripping.
        try:
            cfg = await self._client.get_ripper_config()
            if not cfg.auto_rip_on_insert:
                logger.info("disc-inserted ignored: auto_rip_on_insert=false; trigger via UI to start a rip")
                return
        except httpx.HTTPError as e:
            logger.warning("auto-rip config lookup failed (%s); proceeding fail-open", e)
        await self._run_pipeline(device_path, pending_session_id=None)

    async def _run_pipeline(self, device_path: str, *, pending_session_id: str | None) -> None:
        async with self._active_lock:
            self._active_task = asyncio.current_task()
            try:
                # Refresh the MakeMKV key before makemkvcon first touches
                # the disc (the scan probe runs it for every disc), so a
                # container up across a beta-key rotation doesn't scan/rip
                # protected discs with a stale key.
                await refresh_makemkv_key(key=await self._configured_makemkv_key())
                try:
                    scan_result = await scan_disc(device_path)
                except ScanError as e:
                    logger.error("scan failed device=%s err=%s", device_path, e)
                    return

                try:
                    job = await self._identify_with_retry(scan_result, pending_session_id=pending_session_id)
                except httpx.HTTPStatusError as e:
                    # Non-retriable identify rejection (e.g. 409 ripping-paused). Park
                    # the pipeline quietly — the lock releases via the context manager.
                    logger.info(
                        "rip pipeline not started: identify rejected (%s) for drive %s",
                        e.response.status_code,
                        self._drive_id,
                    )
                    return
                self._active_job_id = job.id

                # Phase 12 — every log line below carries job_id once identify lands.
                with with_log_context(job_id=job.id):
                    if job.status == JobStatus.AWAITING_USER_ID:
                        resolved = await self._await_resolution(job.id)
                        if resolved is None:
                            return
                        job.status = resolved.status

                    if job.status != JobStatus.IDENTIFIED:
                        logger.info("job %s in unexpected status %s; not ripping", job.id, job.status.value)
                        return

                    try:
                        await self._run_rip(job, device_path)
                    except httpx.HTTPStatusError as e:
                        # Backend rejected a state transition (e.g. rip-start
                        # 422 because identify produced an empty scan_result).
                        # Retrying won't fix it — log clearly and let the
                        # pipeline exit so the operator can abandon the job.
                        logger.error(
                            "rip pipeline aborted: backend returned %s for %s — abandon job_id=%s manually",
                            e.response.status_code,
                            e.request.url,
                            job.id,
                        )
                        return
                    except asyncio.CancelledError:
                        # Backend abandon → WS `job.abandoned` → task cancel.
                        # makemkvcon (or the abcde/dd subprocess) gets killed
                        # by its own finally-block subprocess cleanup; we just
                        # log and let the cancellation propagate so the lock
                        # releases without calling rip-complete.
                        logger.info("rip cancelled job_id=%s", job.id)
                        raise
            finally:
                self._active_task = None
                self._active_job_id = None

    async def _identify_with_retry(
        self,
        scan_result: ScanResult,
        *,
        pending_session_id: str | None = None,
    ) -> Job:
        delay = IDENTIFY_RETRY_INITIAL_SECONDS
        while True:
            try:
                return await self._client.identify(
                    drive_id=self._drive_id,
                    scan_result=scan_result,
                    pending_session_id=pending_session_id,
                )
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if 400 <= status_code < 500 and status_code != 429:
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

    async def _configured_makemkv_key(self) -> str | None:
        """The operator's UI-set MakeMKV key, or None to fall back to the
        MAKEMKV_KEY env var / forum scrape.

        Fail-open: a flapping backend must not block ripping. On any lookup
        error we return None, which leaves the legacy env/scrape behaviour
        intact rather than wiping a key the operator already configured.
        """
        try:
            cfg = await self._client.get_ripper_config()
        except httpx.HTTPError as e:
            logger.warning("makemkv key lookup failed (%s); using env/scrape fallback", e)
            return None
        return cfg.makemkv_key

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
        with with_log_context(job_id=job.id):
            # Crash-resume skips the scan path, so refresh the key here too —
            # a rip resumed days after a crash must not run on a stale key.
            await refresh_makemkv_key(key=await self._configured_makemkv_key())
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
            with with_log_context(track_id=track.id):
                await self._patch_track_with_retry(track.id, status=TrackStatus.IN_PROGRESS)

        async def on_track_done(track: TrackView, result: RipResult) -> None:
            with with_log_context(track_id=track.id):
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
            with with_log_context(track_id=track.id):
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
            min_length_seconds=(
                rip_start.min_length_seconds
                if rip_start.min_length_seconds is not None
                else self._default_min_length_seconds
            ),
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

        Best-effort `umount` first covers the case where a sibling
        container or the ripper's own scan-poster path mounted the
        device internally.
        """
        # ISO sources have no tray to eject. probe_disc reads the file
        # directly via PyCdlib and makemkvcon opens it read-only; nothing
        # mounts it, so there's nothing to umount or eject.
        if is_iso_source(device_path):
            logger.info("eject skipped: source is ISO file %s", device_path)
            return
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

    @staticmethod
    def _is_retryable(exc: httpx.HTTPError) -> bool:
        """A 4xx response is the backend telling us the request itself
        is wrong (validation error, missing job, conflict). Retrying
        won't fix it and will keep hammering the backend forever — so
        bail. Transport errors and 5xx responses are transient and
        should keep retrying with backoff."""
        if isinstance(exc, httpx.HTTPStatusError) and 400 <= exc.response.status_code < 500:
            return False
        return True

    async def _rip_start_with_retry(self, job_id: str) -> RipStartResponse:
        delay = PATCH_RETRY_INITIAL_SECONDS
        while True:
            try:
                return await self._client.rip_start(job_id)
            except httpx.HTTPError as e:
                if not self._is_retryable(e):
                    logger.error("rip-start %s rejected by backend (%s); giving up", job_id, e)
                    raise
                logger.warning("rip-start %s failed (%s); retrying in %.1fs", job_id, e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, PATCH_RETRY_MAX_SECONDS)

    async def _rip_complete_with_retry(self, job_id: str) -> JobView:
        delay = PATCH_RETRY_INITIAL_SECONDS
        while True:
            try:
                return await self._client.rip_complete(job_id)
            except httpx.HTTPError as e:
                if not self._is_retryable(e):
                    logger.error("rip-complete %s rejected by backend (%s); giving up", job_id, e)
                    raise
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
                if not self._is_retryable(e):
                    logger.error("PATCH track %s rejected by backend (%s); giving up", track_id, e)
                    raise
                logger.warning("PATCH track %s failed (%s); retrying in %.1fs", track_id, e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, PATCH_RETRY_MAX_SECONDS)
