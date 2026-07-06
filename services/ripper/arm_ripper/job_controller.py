import asyncio
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from arm_common import DiscType, Job, JobStatus, TrackStatus, with_log_context
from arm_common.schemas import JobView, RipperConfigView, RipStartResponse, ScanResult, TrackView, WSEnvelope
from arm_ripper.backend_client import BackendClient
from arm_ripper.community_keydb import refresh_community_keydb
from arm_ripper.drive_poll import DriveState, read_drive_status
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


@dataclass(frozen=True)
class _WaitSpec:
    """Parameterizes the park-and-wait machine for a held job.

    `parked` is the status the job sits in while waiting; `success` is the set of
    statuses that mean "stop waiting, proceed to rip". Any other status means the
    job left the gate some other way (abandoned, failed, …) → give up. This lets
    one wait loop serve both the identify gate (park awaiting_user_id, succeed on
    identified) and the review gate (park awaiting_review, succeed on
    identified/ripping).

    `timed` enables the review-gate countdown: while parked, the loop computes a
    deadline from `wait_start_time + manual_wait_seconds` and, on expiry while NOT
    paused (global `ripping_paused` OR per-job pause), self-starts the rip. Pause
    suspends the countdown; the deadline is only honoured while unpaused."""

    parked: JobStatus
    success: frozenset[JobStatus]
    label: str
    timed: bool = False


# Identify gate: disc couldn't auto-ID; wait for the operator to resolve identity.
_IDENTIFY_WAIT = _WaitSpec(
    parked=JobStatus.AWAITING_USER_ID,
    success=frozenset({JobStatus.IDENTIFIED}),
    label="awaiting_user_id",
)
# Review gate (timed): disc identified but held for review; wait for Start (which
# transitions to ripping), the auto-start countdown (ripper self-starts → ripping),
# or the operator otherwise leaving the gate.
_REVIEW_WAIT = _WaitSpec(
    parked=JobStatus.AWAITING_REVIEW,
    success=frozenset({JobStatus.IDENTIFIED, JobStatus.RIPPING}),
    label="awaiting_review",
    timed=True,
)
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
        self._keydb_tasks: set[asyncio.Task[None]] = set()
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
        # Abandon-triggered eject runs fire-and-forget (the WS handler is
        # sync); kept here so overlapping abandon signals don't stack
        # umount/eject subprocess retries. Set inside `_spawn_eject` only.
        self._eject_task: asyncio.Task[None] | None = None

    @property
    def is_active(self) -> bool:
        return self._active_lock.locked()

    def is_idle(self) -> bool:
        """True when no rip pipeline is running (no active task claimed the lock).

        Used by the heartbeat idle re-probe to decide whether to attempt pickup.
        """
        return self._active_task is None

    async def pickup(self, job: JobView, device_path: str) -> None:
        """Re-acquire a rip-ready job from a heartbeat reprobe.

        Claims _active_task before starting so is_idle() returns False from the
        moment we enter, preventing a double-rip if heartbeat fires again while
        the pipeline is starting up. The actual rip runs via _run_rip, which
        follows the same path as a normal pipeline (rip-start → execute → complete
        → eject) but skips scan/identify since the job already exists.
        """
        if not self.is_idle():
            logger.debug("pickup ignored: controller already busy")
            return
        if self._device_path is None and device_path:
            self._device_path = device_path
        async with self._active_lock:
            self._active_task = asyncio.current_task()
            self._active_job_id = job.id
            try:
                with with_log_context(job_id=job.id):
                    logger.info("pickup: re-acquiring job %s status=%s", job.id, job.status.value)
                    await self._run_rip(job, device_path)
            finally:
                self._active_task = None
                self._active_job_id = None

    async def on_ws_command(self, envelope: WSEnvelope) -> None:
        """Handler registered for `ripper.commands.{drive_id}` topic."""
        if envelope.event_type in ("identify.resolved", "rip.start", "review.pause"):
            # All wake the per-job wait Event; the waiter re-fetches the job and
            # re-evaluates (identify.resolved -> identified; rip.start -> ripping;
            # review.pause -> re-read manual_pause/wait_start_time so a per-job
            # pause/resume applies promptly instead of on the next periodic poll).
            job_id = envelope.payload.get("job_id") if isinstance(envelope.payload, dict) else None
            if not isinstance(job_id, str):
                logger.warning("%s without job_id payload: %s", envelope.event_type, envelope.payload)
                return
            event = self._resolution_events.get(job_id)
            if event is not None:
                event.set()
                logger.info("ws %s received for job_id=%s", envelope.event_type, job_id)
            else:
                logger.debug("%s for job_id=%s but no waiter registered", envelope.event_type, job_id)
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
        """Cancel the active pipeline if it owns this job, optionally wipe
        `/raw/<job_id>/`, then give the disc back. Runs synchronously from
        the WS handler; cancel + rmtree are both fast and don't need
        awaitable plumbing (eject spawns as a task).

        rmtree on Linux is safe even if makemkvcon still has file handles
        open: the directory entries are removed, existing fds keep working
        (writing to nowhere) until the cancelled subprocess dies.
        """
        active = self._active_task
        owns = self._active_job_id == job_id and active is not None and not active.done()
        if active is not None and owns:
            logger.info("job.abandoned: cancelling active task for job_id=%s", job_id)
            active.cancel()
        if delete_raw:
            target = RAW_ROOT / job_id
            try:
                shutil.rmtree(target)
                logger.info("wiped raw dir job_id=%s path=%s", job_id, target)
            except FileNotFoundError:
                logger.info("raw dir already absent job_id=%s path=%s", job_id, target)
            except OSError as exc:
                logger.warning("raw-dir cleanup failed job_id=%s path=%s: %s", job_id, target, exc)
        # Abandon means "done with this disc — give it back". The lifecycle's
        # post-rip eject (end of _run_rip) never runs on an abandon exit, so
        # eject here: when this job owns the drive's pipeline (ripping or
        # parked — _eject_with_retry's EBUSY retries absorb the cancelled
        # makemkvcon's teardown), or when the drive is idle with a disc still
        # seated (pipeline already exited, e.g. after a rip-start abort). A
        # stale abandon while a DIFFERENT job's rip owns the drive must not
        # pop the tray mid-rip.
        idle = active is None or active.done()
        if owns or (idle and self._disc_seated()):
            self._spawn_eject()

    def _disc_seated(self) -> bool:
        """True when the drive currently reports a seated disc (DISC_OK) —
        guards abandon-eject so abandoning an old job from history with an
        empty (or already-ejected) drive doesn't pop the tray."""
        if self._device_path is None or is_iso_source(self._device_path):
            return False
        try:
            return read_drive_status(self._device_path) == DriveState.DISC_OK
        except OSError:
            return False

    def _spawn_eject(self) -> None:
        """Fire-and-forget eject for the sync abandon handler; deduped so
        overlapping abandon signals don't stack umount/eject retries."""
        if self._device_path is None:
            return
        if self._eject_task is not None and not self._eject_task.done():
            return
        self._eject_task = asyncio.create_task(self._eject_with_retry(self._device_path))

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
                self._spawn_keydb_refresh(enabled=await self._community_keydb_enabled())
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
                        resolved = await self._await_resolution(job.id, _IDENTIFY_WAIT)
                        if resolved is None:
                            return
                        job.status = resolved.status

                    # Timed review gate: the backend parks an identified disc here
                    # when hold_for_review is on. Wait for Start (-> ripping) or the
                    # auto-start path (-> identified); either proceeds to the rip.
                    if job.status == JobStatus.AWAITING_REVIEW:
                        resolved = await self._await_resolution(job.id, _REVIEW_WAIT)
                        if resolved is None:
                            return
                        job.status = resolved.status

                    # Proceed for: identified (normal / operator Start landed),
                    # ripping (operator Start already transitioned), or
                    # awaiting_review (timed auto-start — rip-start transitions it).
                    if job.status not in (JobStatus.IDENTIFIED, JobStatus.RIPPING, JobStatus.AWAITING_REVIEW):
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

    async def _await_resolution(self, job_id: str, spec: _WaitSpec = _IDENTIFY_WAIT) -> JobView | None:
        """Park a held job on an Event and wait for it to leave the gate.

        Primary path: a WS command on `ripper.commands.{drive_id}`
        (`identify.resolved` for the identify gate, `rip.start` for the review
        gate) sets the per-job Event. Fallback path: if no WS event arrives within
        RESOLUTION_WS_FIRST_WAIT_SECONDS, do one REST get_job to cover the
        boot-race where the disc left the gate before WSClient finished its
        handshake; then slow-poll so a WS outage doesn't strand the job.

        `spec` selects which gate (parked status + success statuses). Defaults to
        the identify gate so existing callers are unchanged.
        """
        logger.info("job %s %s; waiting", job_id, spec.label)
        event = asyncio.Event()
        self._resolution_events[job_id] = event
        try:
            return await self._wait_for_resolution(job_id, event, spec)
        finally:
            self._resolution_events.pop(job_id, None)

    def _classify_wait(self, view: JobView | None, job_id: str, spec: _WaitSpec) -> tuple[str, JobView | None]:
        """Decide the wait outcome from a freshly-fetched job view.

        Returns ("proceed", view) on a success status, ("wait", None) while still
        parked (keep waiting), or ("abandon", None) when the job left the gate any
        other way (abandoned/failed/…). A None view (transient REST failure during
        the long poll) maps to "wait" so a blip doesn't abandon the job."""
        if view is None:
            return ("wait", None)
        if view.status in spec.success:
            logger.info("job %s left %s -> %s title=%s", job_id, spec.label, view.status.value, view.title)
            return ("proceed", view)
        if view.status == spec.parked:
            return ("wait", None)
        logger.info("job %s left %s with status=%s; abandoning", job_id, spec.label, view.status.value)
        return ("abandon", None)

    async def _wait_for_resolution(self, job_id: str, event: asyncio.Event, spec: _WaitSpec) -> JobView | None:
        # First-wait window: covers the boot race where we missed the
        # gate-leaving broadcast before subscribing.
        try:
            await asyncio.wait_for(event.wait(), timeout=RESOLUTION_WS_FIRST_WAIT_SECONDS)
        except asyncio.TimeoutError:
            outcome, view = self._classify_wait(await self._safe_get_job(job_id), job_id, spec)
            if outcome == "proceed":
                return view
            if outcome == "abandon":
                return None

        # Long wait: WS-driven, with periodic REST sanity polls so we
        # don't hang forever on a torn WS connection.
        deadline = asyncio.get_event_loop().time() + RESOLUTION_WAIT_TIMEOUT_SECONDS
        while asyncio.get_event_loop().time() < deadline:
            woke_via_ws = True
            try:
                await asyncio.wait_for(event.wait(), timeout=POLL_MAX_SECONDS)
            except asyncio.TimeoutError:
                woke_via_ws = False  # periodic sanity poll — handles torn WS connections
            view = await self._safe_get_job(job_id)
            outcome, proceed_view = self._classify_wait(view, job_id, spec)
            if outcome == "proceed":
                return proceed_view
            if outcome == "abandon":
                return None
            # Still parked. Timed review gate: if the countdown has elapsed and the
            # disc is not paused, auto-start — return the parked view so the
            # pipeline proceeds to _run_rip (rip-start transitions the status).
            if spec.timed and view is not None and await self._review_countdown_expired(view):
                logger.info("job %s review countdown elapsed; auto-starting rip", job_id)
                return view
            # If a WS wake was spurious, clear+re-arm the Event.
            if woke_via_ws:
                event.clear()

        logger.warning("job %s %s wait timed out after %.0fs", job_id, spec.label, RESOLUTION_WAIT_TIMEOUT_SECONDS)
        return None

    async def _review_countdown_expired(self, view: JobView) -> bool:
        """True when a held disc's auto-start countdown has elapsed AND it is not
        paused. Paused — global `ripping_paused` OR this disc's per-job
        `manual_pause` — keeps the countdown suspended, so it returns False and the
        wait continues. The job view + config are re-read each poll so a mid-wait
        pause / resume / duration change applies on the next cycle.
        """
        if view.manual_pause:
            return False
        cfg = await self._safe_get_ripper_config()
        if cfg is None or cfg.ripping_paused:
            return False
        if view.wait_start_time is None:
            return False
        elapsed = (datetime.now(timezone.utc) - view.wait_start_time).total_seconds()
        return elapsed >= cfg.manual_wait_seconds

    async def _safe_get_job(self, job_id: str) -> JobView | None:
        try:
            return await self._client.get_job(job_id)
        except httpx.HTTPError as e:
            logger.warning("get_job %s failed (%s); will retry on next signal", job_id, e)
            return None

    async def _safe_get_ripper_config(self) -> RipperConfigView | None:
        """Ripper config (ripping_paused + manual_wait_seconds) for the review
        countdown. None on transport error → the caller treats it as 'can't tell;
        keep waiting' (fail-safe: never auto-rip on a config blip)."""
        try:
            return await self._client.get_ripper_config()
        except httpx.HTTPError as e:
            logger.warning("get_ripper_config failed (%s); keeping countdown suspended", e)
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

    async def _community_keydb_enabled(self) -> bool:
        """Whether the operator has the community-keydb auto-fetch enabled.
        Fail-open to True (the default) so a flapping backend doesn't silently
        disable the feature."""
        try:
            cfg = await self._client.get_ripper_config()
        except httpx.HTTPError as e:
            logger.warning("community keydb toggle lookup failed (%s); defaulting enabled", e)
            return True
        return cfg.community_keydb_enabled

    def _spawn_keydb_refresh(self, *, enabled: bool) -> None:
        """Fire-and-forget community-keydb refresh. The rip proceeds immediately
        with the on-disk keydb; a fresh keydb benefits the next rip. Errors are
        swallowed — a keydb hiccup must never abort a rip."""
        task = asyncio.create_task(self._keydb_refresh_and_report(enabled=enabled))
        self._keydb_tasks.add(task)
        task.add_done_callback(self._keydb_tasks.discard)

    async def _keydb_refresh_and_report(self, *, enabled: bool) -> None:
        try:
            result = await refresh_community_keydb(enabled=enabled)
            if result is not None:
                await self._client.report_keydb_status(
                    state=result.state, vuk_count=result.vuk_count, age_days=result.age_days
                )
        except Exception as exc:  # noqa: BLE001 — fire-and-forget, never propagate
            logger.warning("community keydb refresh failed (non-fatal): %s", exc)

    async def _drain_keydb_tasks(self) -> None:
        """Await any outstanding keydb refreshes. Used by tests to synchronise
        on the fire-and-forget tasks. Not wired into production shutdown by
        design: a keydb refresh is best-effort, so on SIGTERM the tasks are
        abandoned (their bodies swallow Exception, and CancelledError —
        BaseException — propagates cleanly to the event loop)."""
        if self._keydb_tasks:
            await asyncio.gather(*self._keydb_tasks, return_exceptions=True)

    async def _run_rip(self, job: Job | JobView, device_path: str) -> None:
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

    async def recover_held_job(self, job: JobView, device_path: str) -> None:
        """Reboot recovery for a disc that was PAUSED in the review gate
        (timed review gate §6.3). Re-park the review wait so the operator can
        still Start it; on Start (-> ripping) or auto-start (-> identified), run
        the rip. Unlike resume_inflight_job this does NOT wipe /raw or re-rip —
        the disc never ripped. A re-parked disc waits for an explicit Start; it
        does not auto-rip on boot even if its countdown had expired.
        """
        async with self._active_lock:
            self._active_task = asyncio.current_task()
            self._active_job_id = job.id
            try:
                with with_log_context(job_id=job.id):
                    logger.info("reboot recovery: re-parking held job %s", job.id)
                    resolved = await self._await_resolution(job.id, _REVIEW_WAIT)
                    if resolved is None:
                        return
                    job = resolved
                    if job.status not in (JobStatus.IDENTIFIED, JobStatus.RIPPING):
                        logger.info("recovered job %s in status %s; not ripping", job.id, job.status.value)
                        return
                    await self._run_rip(job, device_path)
            finally:
                self._active_task = None
                self._active_job_id = None

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
            self._spawn_keydb_refresh(enabled=await self._community_keydb_enabled())
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
