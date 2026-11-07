import asyncio
import contextlib
import functools
import logging
import shutil
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from arm_common import DiscType, Job, JobStatus, TrackKind, TrackStatus, with_log_context
from arm_common.schemas import JobView, RipperConfigView, RipStartResponse, ScanResult, TrackView, WSEnvelope
from arm_ripper.backend_client import BackendClient
from arm_ripper.community_keydb import refresh_community_keydb
from arm_ripper.drive_handle import DriveHandle
from arm_ripper.makemkv_sdf import refresh_makemkv_sdf
from arm_ripper.makemkv_key import refresh_makemkv_key
from arm_ripper.rip import RipResult, rip_all
from arm_ripper.rip.dispatcher import DEFAULT_MIN_LENGTH_SECONDS
from arm_ripper.rip.track_callbacks import TransferStats
from arm_ripper.drive_poll import _ABSENT_ERRNOS, DriveState, read_drive_status
from arm_ripper.scan import ScanError, scan as scan_disc
from arm_ripper.source import is_file_source
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
# A DVD/BD drive that drops off the bus mid-rip (a USB enclosure reset; it
# often re-enumerates under a new srN): how long the rip waits for it to come
# back with the disc readable before finishing the job as partial, how often
# it looks, and how many times one rip may resume.
DEVICE_RETURN_WAIT_SECONDS = 180.0
DEVICE_WATCH_INTERVAL_SECONDS = 1.0
MAX_DEVICE_RESUMES = 3
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
# A freshly-settled disc can report DISC_OK via the CDROM_DRIVE_STATUS ioctl
# before the medium is *data*-readable, so makemkvcon enumerates zero titles.
# The disc IS present (per ioctl), so a zero-title scan there means "not ready
# yet," not "genuinely empty" — retry, letting the drive finish spinning up /
# the TOC become readable. Generous budget (a quick 1-2s retry would miss a slow
# settle — the field report saw 4/4 discs fail); bounded so a genuinely
# unreadable disc resolves to a clear give-up in ~26s.
SCAN_NOT_READY_MAX_ATTEMPTS = 5
SCAN_NOT_READY_BACKOFFS = (2.0, 4.0, 8.0, 12.0)  # between attempts 1→2, 2→3, 3→4, 4→5

# Sentinel distinguishing "resolution_timeout not passed" (defer to
# whatever RESOLUTION_WAIT_TIMEOUT_SECONDS currently is) from an explicit
# `resolution_timeout=None` (wait forever). A plain
# `resolution_timeout: float | None = RESOLUTION_WAIT_TIMEOUT_SECONDS`
# default would bind to that module constant's value once, at import time —
# invisible to a caller (or test) that reads/patches the live module
# attribute afterward, which is how every existing wait test already
# configures the timeout.
_RESOLUTION_TIMEOUT_UNSET = object()


def _spawn_tracked(coro: Coroutine[Any, Any, None], tasks: set[asyncio.Task[None]]) -> None:
    """Run `coro` as a fire-and-forget task, held in `tasks` until it finishes so it is not garbage-collected
    mid-run."""
    task = asyncio.create_task(coro)
    tasks.add(task)
    task.add_done_callback(tasks.discard)


def _disconnect_reason(resumes: int) -> str:
    """Why the titles a lost drive left are failed: it did not come back in time, or it dropped more often than a
    rip may resume."""
    return (
        f"the drive disconnected mid-rip and did not come back within {DEVICE_RETURN_WAIT_SECONDS:.0f}s"
        if resumes < MAX_DEVICE_RESUMES
        else f"the drive disconnected mid-rip {resumes + 1} times; giving up"
    )


def _command_payload(envelope: WSEnvelope) -> dict[str, Any]:
    """A WS command's payload, or an empty dict when it isn't one."""
    return envelope.payload if isinstance(envelope.payload, dict) else {}


async def _woken_within(event: asyncio.Event, timeout: float) -> bool:
    """True when `event` is set within `timeout` seconds, False when the wait times out."""
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        return False
    return True


def _previously_ripped(response: httpx.Response) -> bool:
    """identify's 409 for a disc the backend refused because it was ripped
    before (on_previously_ripped=reject)."""
    if response.status_code != 409:
        return False
    try:
        detail = response.json().get("detail")
    except ValueError:
        return False
    return isinstance(detail, dict) and detail.get("reason") == "previously_ripped"


class JobController:
    """Drives one disc through scan → identify → rip → eject."""

    def __init__(
        self,
        client: BackendClient,
        drive_id: str,
        *,
        ws: WSClient | None = None,
        device_path: str | DriveHandle | None = None,
        default_min_length_seconds: int = DEFAULT_MIN_LENGTH_SECONDS,
        resolution_timeout: float | None = _RESOLUTION_TIMEOUT_UNSET,  # type: ignore[assignment]
    ) -> None:
        self._client = client
        # Jobs whose countdown hold for a guessed placement was already logged.
        self._held_for_guess: set[str] = set()
        self._keydb_tasks: set[asyncio.Task[None]] = set()
        self._sdf_tasks: set[asyncio.Task[None]] = set()
        self._wipe_tasks: set[asyncio.Task[None]] = set()
        self._drive_id = drive_id
        self._ws = ws
        # Each ripper container owns exactly one optical drive. The node it
        # occupies can change while we run (replug under a new srN), so we
        # hold the shared DriveHandle rather than a copy of the path — the
        # poll loop keeps it current and every read here sees the move. A
        # plain str (ISO source, tests) is wrapped as a fixed handle.
        if isinstance(device_path, DriveHandle):
            self._device = device_path
        elif device_path is None:
            self._device = DriveHandle()
        else:
            self._device = DriveHandle.fixed(device_path)
        # Host-side baseline `--minlength` for `makemkvcon mkv all`. The
        # backend can override per-rip via `RipStartResponse.min_length_seconds`
        # (resolved from the Session's `overrides_json["min_length_seconds"]`);
        # when no override is sent we fall back to this value. Injected by
        # `main.py` from `ARM_MIN_LENGTH_SECONDS`; tests get the dispatcher
        # default (600).
        self._default_min_length_seconds = default_min_length_seconds
        # Ceiling on an AWAITING_USER_ID / AWAITING_REVIEW park, in seconds.
        # None means wait indefinitely — source mode's one-shot container must
        # not exit (and have the backend watchdog mark the job FAILED) while
        # the operator is still reviewing; see `_wait_for_resolution`.
        self._resolution_timeout: float | None = (
            RESOLUTION_WAIT_TIMEOUT_SECONDS if resolution_timeout is _RESOLUTION_TIMEOUT_UNSET else resolution_timeout
        )
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
    def _device_path(self) -> str | None:
        """Read-only view of the shared DriveHandle. Only the poll loop writes
        the handle (spec §4) — a controller-side write would let a stale
        pickup path override the node the loop just resolved."""
        return self._device.current

    @property
    def is_active(self) -> bool:
        return self._active_lock.locked()

    def is_idle(self) -> bool:
        """True when no rip pipeline is running (no active task claimed the lock).

        Used by the heartbeat idle re-probe to decide whether to attempt pickup.
        """
        return self._active_task is None

    @contextlib.asynccontextmanager
    async def _claim(self, job_id: str | None) -> AsyncIterator[None]:
        """Hold the single-flight gate for this task and job: is_idle() is False, and job.abandoned can cancel the
        task, until the block exits. A pipeline claims with None, before identify has made the job, and records the
        id itself once it has one."""
        async with self._active_lock:
            self._active_task = asyncio.current_task()
            self._active_job_id = job_id
            try:
                yield
            finally:
                self._active_task = None
                self._active_job_id = None

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
        async with self._claim(job.id):
            with with_log_context(job_id=job.id):
                logger.info("pickup: re-acquiring job %s status=%s", job.id, job.status.value)
                await self._run_rip(job, device_path)

    async def on_ws_command(self, envelope: WSEnvelope) -> None:
        """Handler registered for `ripper.commands.{drive_id}` topic: runs the handler for the command's event
        type and ignores any other type."""
        handlers: dict[str, Callable[[WSEnvelope], None]] = {
            "identify.resolved": self._on_wake_command,
            "rip.start": self._on_wake_command,
            "review.pause": self._on_wake_command,
            "manual.trigger": self._on_manual_trigger,
            "job.abandoned": self._on_job_abandoned,
        }
        handler = handlers.get(envelope.event_type)
        if handler is None:
            logger.debug("ws command ignored: type=%s", envelope.event_type)
            return
        handler(envelope)

    def _on_wake_command(self, envelope: WSEnvelope) -> None:
        """Wake the pipeline parked on the payload's job so it re-fetches the job and re-evaluates:
        identify.resolved -> identified, rip.start -> ripping, review.pause -> re-read
        manual_pause / wait_start_time so a per-job pause or resume applies promptly instead of
        on the next periodic poll."""
        job_id = _command_payload(envelope).get("job_id")
        if not isinstance(job_id, str):
            logger.warning("%s without job_id payload: %s", envelope.event_type, envelope.payload)
            return
        if self._wake_waiter(job_id):
            logger.info("ws %s received for job_id=%s", envelope.event_type, job_id)
        else:
            logger.debug("%s for job_id=%s but no waiter registered", envelope.event_type, job_id)

    def _on_manual_trigger(self, envelope: WSEnvelope) -> None:
        """Start a manual rip for the payload's session, or with no session when it doesn't name one as a string."""
        payload = _command_payload(envelope)
        session_id = payload.get("session_id")
        if session_id is not None and not isinstance(session_id, str):
            logger.warning("manual.trigger with non-string session_id: %r", session_id)
            session_id = None
        asyncio.create_task(self.handle_manual_trigger(session_id))

    def _on_job_abandoned(self, envelope: WSEnvelope) -> None:
        """Abandon the payload's job, then wake a pipeline parked on it so it sees the new status."""
        payload = _command_payload(envelope)
        job_id = payload.get("job_id")
        delete_raw = bool(payload.get("delete_raw"))
        if not isinstance(job_id, str):
            logger.warning("job.abandoned without job_id payload: %s", payload)
            return
        self._handle_abandon(job_id, delete_raw=delete_raw)
        # Also wake any `_await_resolution` waiter — abandoning a parked
        # job needs to unstick the pipeline the same way `identify.resolved`
        # does. The waiter polls and decides based on the new job status.
        self._wake_waiter(job_id)

    def _wake_waiter(self, job_id: str) -> bool:
        """Set the wait event of the pipeline parked on this job, if one is; True when there was one."""
        event = self._resolution_events.get(job_id)
        if event is None:
            return False
        event.set()
        return True

    def _handle_abandon(self, job_id: str, *, delete_raw: bool) -> None:
        """Cancel the active pipeline if it owns this job, optionally wipe
        `/raw/<job_id>/`, then give the disc back. Runs synchronously from
        the WS handler, so the slow parts (the raw-dir wipe and the eject)
        are spawned as tasks: deleting a 50-100 GB rip can take seconds on
        NFS, and the WS receive loop must not stall behind it.

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
            _spawn_tracked(self._wipe_raw(job_id), self._wipe_tasks)
        if self._abandon_ejects(owns):
            self._spawn_eject()

    def _abandon_ejects(self, owns: bool) -> bool:
        """Whether an abandon gives the disc back: "done with this disc, give it back".

        The lifecycle's post-rip eject (end of _run_rip) never runs on an abandon exit, so eject here: when this
        job owns the drive's pipeline (ripping or parked; _eject_with_retry's EBUSY retries absorb the cancelled
        makemkvcon's teardown), or when the drive is idle with a disc still seated (pipeline already exited, e.g.
        after a rip-start abort). A stale abandon while a DIFFERENT job's rip owns the drive must not pop the
        tray mid-rip.
        """
        active = self._active_task
        idle = active is None or active.done()
        return owns or (idle and self._disc_seated())

    async def _wipe_raw(self, job_id: str) -> None:
        """Delete `/raw/<job_id>/` off the event loop."""
        target = RAW_ROOT / job_id
        try:
            await asyncio.to_thread(shutil.rmtree, target)
            logger.info("wiped raw dir job_id=%s path=%s", job_id, target)
        except FileNotFoundError:
            logger.info("raw dir already absent job_id=%s path=%s", job_id, target)
        except OSError as exc:
            logger.warning("raw-dir cleanup failed job_id=%s path=%s: %s", job_id, target, exc)

    def _disc_seated(self) -> bool:
        """True when the drive currently reports a seated disc (DISC_OK) —
        guards abandon-eject so abandoning an old job from history with an
        empty (or already-ejected) drive doesn't pop the tray."""
        if self._device_path is None or is_file_source(self._device_path):
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
        async with self._claim(None):
            # Refresh the MakeMKV key before makemkvcon first touches
            # the disc (the scan probe runs it for every disc), so a
            # container up across a beta-key rotation doesn't scan/rip
            # protected discs with a stale key.
            await self._prepare_makemkv()
            scan_result = await self._scan_or_none(device_path)
            if scan_result is None:
                return

            try:
                job = await self._identify_with_retry(scan_result, pending_session_id=pending_session_id)
            except httpx.HTTPStatusError as e:
                if _previously_ripped(e.response):
                    # on_previously_ripped=reject: the backend made no job
                    # and told the operator; give the disc back.
                    logger.info("disc already ripped (on_previously_ripped=reject); ejecting %s", device_path)
                    await self._eject_with_retry(device_path)
                    return
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

    async def _scan_or_none(self, device_path: str) -> ScanResult | None:
        """Scan the disc, or None after a log line when the scan fails or the drive goes absent mid-scan (which ends
        the pipeline). Any other OSError propagates."""
        try:
            return await self._scan_with_ready_retry(device_path)
        except ScanError as e:
            logger.error("scan failed device=%s err=%s", device_path, e)
            return None
        except OSError as e:
            if e.errno not in _ABSENT_ERRNOS:
                raise
            logger.warning("drive went absent during scan device=%s — pipeline abandoned", device_path)
            return None

    async def _scan_with_ready_retry(self, device_path: str) -> ScanResult:
        """Scan the disc, retrying when a DISC_OK drive yields zero titles.

        A `DISC_OK` drive that scans to zero titles is almost certainly not
        data-ready yet (the medium reports present via ioctl before the first
        SCSI read succeeds). Retry with backoff to wait out the settle. If the
        drive leaves DISC_OK (tray opened / disc pulled), stop. On exhaustion,
        return the last (empty) result — the caller handles the give-up.

        Note: `read_drive_status` (os.open + ioctl) may raise OSError if the
        device node vanishes mid-retry (USB autosuspend / passthrough teardown);
        that propagates to the pipeline task boundary by design — the task ends
        and the drive poller re-arms on the next disc-insert event.
        """
        last: ScanResult | None = None
        for attempt in range(1, SCAN_NOT_READY_MAX_ATTEMPTS + 1):
            result = await scan_disc(device_path)
            last = result
            if result.titles:
                return result

            # An ISO file has no drive to settle: the CDROM_DRIVE_STATUS ioctl
            # below is invalid on a regular file (ENOTTY) and would crash the
            # one-shot source pipeline. Zero titles from a file is final.
            if self._zero_titles_are_final(device_path):
                return result

            if attempt < SCAN_NOT_READY_MAX_ATTEMPTS and not await self._back_off_before_rescan(device_path, attempt):
                return result

        logger.error(
            "DISC_UNREADABLE_AFTER_RETRIES device=%s drive_state=DISC_OK attempts=%d — "
            "disc present per ioctl but no readable titles after retries; check disc/drive "
            "readiness (dirty/damaged disc, drive spin-up, or container device passthrough)",
            device_path,
            SCAN_NOT_READY_MAX_ATTEMPTS,
        )
        assert last is not None
        return last

    @staticmethod
    def _zero_titles_are_final(device_path: str) -> bool:
        """Whether a zero-title scan is the answer rather than a drive still settling: an ISO source has nothing to
        settle, and a drive no longer DISC_OK has lost its disc."""
        if is_file_source(device_path):
            logger.warning("scan: 0 titles from ISO source %s — nothing to retry", device_path)
            return True
        state = read_drive_status(device_path)
        if state != DriveState.DISC_OK:
            logger.info(
                "scan: 0 titles and drive no longer DISC_OK (state=%s) device=%s — stopping",
                state.name,
                device_path,
            )
            return True
        return False

    @staticmethod
    async def _back_off_before_rescan(device_path: str, attempt: int) -> bool:
        """Wait out this attempt's back-off, then report whether the drive still holds its disc and is worth
        scanning again."""
        backoff = SCAN_NOT_READY_BACKOFFS[attempt - 1]
        logger.warning(
            "scan returned 0 titles while drive=DISC_OK (data not ready?) device=%s titles=0 retry=%d/%d backoff=%.0fs",
            device_path,
            attempt,
            SCAN_NOT_READY_MAX_ATTEMPTS,
            backoff,
        )
        await asyncio.sleep(backoff)
        # Re-check status after the sleep — disc may have been pulled
        # while we were waiting; stop before wasting another scan probe.
        post_sleep_state = read_drive_status(device_path)
        if post_sleep_state != DriveState.DISC_OK:
            logger.info(
                "scan: drive left DISC_OK during backoff (state=%s) device=%s — stopping",
                post_sleep_state.name,
                device_path,
            )
            return False
        return True

    async def _identify_with_retry(
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
        """Wait out the first window, then run long-wait cycles until one settles or the deadline passes; None on
        abandon or timeout."""
        outcome, view = await self._first_wait(job_id, event, spec)
        if outcome != "wait":
            return view

        # Long wait: WS-driven, with periodic REST sanity polls so we
        # don't hang forever on a torn WS connection.
        deadline = self._resolution_deadline()
        while deadline is None or asyncio.get_event_loop().time() < deadline:
            outcome, view = await self._wait_cycle(job_id, event, spec)
            if outcome != "wait":
                return view

        logger.warning("job %s %s wait timed out after %.0fs", job_id, spec.label, self._resolution_timeout)
        return None

    def _resolution_deadline(self) -> float | None:
        """The event-loop time at which a resolution wait gives up, or None to wait indefinitely (source mode). With
        no deadline the periodic POLL_MAX_SECONDS sanity poll still runs, just with no ceiling on it."""
        timeout = self._resolution_timeout
        return None if timeout is None else asyncio.get_event_loop().time() + timeout

    async def _first_wait(self, job_id: str, event: asyncio.Event, spec: _WaitSpec) -> tuple[str, JobView | None]:
        """The short first wait for a WS wake. On a timeout, one REST read covers a gate-leaving broadcast that went
        out before the subscription was up. Returns the `_classify_wait` outcome, or ("wait", None) after a wake."""
        if await _woken_within(event, RESOLUTION_WS_FIRST_WAIT_SECONDS):
            return ("wait", None)
        return self._classify_wait(await self._safe_get_job(job_id), job_id, spec)

    async def _wait_cycle(self, job_id: str, event: asyncio.Event, spec: _WaitSpec) -> tuple[str, JobView | None]:
        """One long-wait cycle: wait up to POLL_MAX_SECONDS for a wake, re-read the job and decide. Returns ("proceed",
        view), ("abandon", None) or ("wait", None); a wake that finds the job still parked re-arms the Event."""
        # A timeout is the periodic sanity poll that handles torn WS connections.
        woke_via_ws = await _woken_within(event, POLL_MAX_SECONDS)
        view = await self._safe_get_job(job_id)
        outcome, proceed_view = self._classify_wait(view, job_id, spec)
        if outcome != "wait":
            return (outcome, proceed_view)
        # Still parked. At a timed review gate whose countdown ran out, auto-start: return
        # the parked view so the pipeline proceeds to _run_rip (rip-start transitions the status).
        if await self._auto_start_due(view, spec):
            logger.info("job %s review countdown elapsed; auto-starting rip", job_id)
            return ("proceed", view)
        # If a WS wake was spurious, clear+re-arm the Event.
        if woke_via_ws:
            event.clear()
        return ("wait", None)

    async def _auto_start_due(self, view: JobView | None, spec: _WaitSpec) -> bool:
        """True when a still-parked job sits at a timed review gate whose countdown has run out (and is not paused)."""
        return spec.timed and view is not None and await self._review_countdown_expired(view)

    async def _review_countdown_expired(self, view: JobView) -> bool:
        """True when a held disc's auto-start countdown has elapsed AND it is not
        paused. Paused — global `ripping_paused` OR this disc's per-job
        `manual_pause` — keeps the countdown suspended, so it returns False and the
        wait continues. The job view + config are re-read each poll so a mid-wait
        pause / resume / duration change applies on the next cycle.
        """
        if view.manual_pause:
            return False
        if view.episodes_unsure:
            # The episode placement is a guess: never auto-start on it. Start
            # rip by hand still works; the hold lifts when a Fix match or a
            # re-run leaves a confident placement.
            self._note_guess_hold(view.id)
            return False
        cfg = await self._safe_get_ripper_config()
        if cfg is None or cfg.ripping_paused:
            return False
        if view.wait_start_time is None:
            return False
        elapsed = (datetime.now(timezone.utc) - view.wait_start_time).total_seconds()
        return elapsed >= cfg.manual_wait_seconds

    def _note_guess_hold(self, job_id: str) -> None:
        """Log, once per job, that its countdown is held because its episode placement is a guess."""
        if job_id not in self._held_for_guess:
            self._held_for_guess.add(job_id)
            logger.info("job %s: countdown held, its episode placement is a guess", job_id)

    async def _safe_get_job(self, job_id: str) -> JobView | None:
        try:
            return await self._client.get_job(job_id)
        except httpx.HTTPError as e:
            logger.warning("get_job %s failed (%s); will retry on next signal", job_id, e)
            return None

    async def _ripper_config_or_none(self, what: str, fallback: str) -> RipperConfigView | None:
        """The ripper config, or None after a warning when the backend can't be reached."""
        try:
            return await self._client.get_ripper_config()
        except httpx.HTTPError as e:
            logger.warning("%s failed (%s); %s", what, e, fallback)
            return None

    async def _safe_get_ripper_config(self) -> RipperConfigView | None:
        """Ripper config (ripping_paused + manual_wait_seconds) for the review
        countdown. None on transport error → the caller treats it as 'can't tell;
        keep waiting' (fail-safe: never auto-rip on a config blip)."""
        return await self._ripper_config_or_none("get_ripper_config", "keeping countdown suspended")

    async def _configured_makemkv_key(self) -> str | None:
        """The operator's UI-set MakeMKV key, or None to fall back to the
        MAKEMKV_KEY env var / forum scrape.

        Fail-open: a flapping backend must not block ripping. On any lookup
        error we return None, which leaves the legacy env/scrape behaviour
        intact rather than wiping a key the operator already configured.
        """
        cfg = await self._ripper_config_or_none("makemkv key lookup", "using env/scrape fallback")
        return None if cfg is None else cfg.makemkv_key

    async def _community_keydb_enabled(self) -> bool:
        """Whether the operator has the community-keydb auto-fetch enabled.
        Fail-open to True (the default) so a flapping backend doesn't silently
        disable the feature."""
        cfg = await self._ripper_config_or_none("community keydb toggle lookup", "defaulting enabled")
        return True if cfg is None else cfg.community_keydb_enabled

    async def _prepare_makemkv(self) -> None:
        """Get MakeMKV ready for a disc: refresh its key now, and start the KEYDB and SDF
        refreshes in the background."""
        await refresh_makemkv_key(key=await self._configured_makemkv_key())
        self._spawn_keydb_refresh(enabled=await self._community_keydb_enabled())
        self._spawn_sdf_refresh(enabled=await self._makemkv_sdf_enabled())

    def _spawn_keydb_refresh(self, *, enabled: bool) -> None:
        """Fire-and-forget community-keydb refresh. The rip proceeds immediately
        with the on-disk keydb; a fresh keydb benefits the next rip. Errors are
        swallowed — a keydb hiccup must never abort a rip."""
        _spawn_tracked(self._keydb_refresh_and_report(enabled=enabled), self._keydb_tasks)

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

    async def _makemkv_sdf_enabled(self) -> bool:
        """Whether the operator has the MakeMKV SDF auto-refresh enabled.
        Fail-open to True so a flapping backend doesn't silently disable it."""
        cfg = await self._ripper_config_or_none("makemkv sdf toggle lookup", "defaulting enabled")
        return True if cfg is None else cfg.makemkv_sdf_enabled

    def _spawn_sdf_refresh(self, *, enabled: bool) -> None:
        """Fire-and-forget MakeMKV SDF refresh. The rip proceeds immediately
        with the on-disk SDF; a fresh SDF benefits the next rip. Errors are
        swallowed — an SDF hiccup must never abort a rip."""
        _spawn_tracked(self._sdf_refresh_and_report(enabled=enabled), self._sdf_tasks)

    async def _sdf_refresh_and_report(self, *, enabled: bool) -> None:
        try:
            result = await refresh_makemkv_sdf(enabled=enabled)
            if result is not None:
                await self._client.report_sdf_status(state=result.state, age_days=result.age_days)
        except Exception as exc:  # noqa: BLE001 — fire-and-forget, never propagate
            logger.warning("makemkv sdf refresh failed (non-fatal): %s", exc)

    async def _drain_sdf_tasks(self) -> None:
        """Await any outstanding SDF refreshes. Test-only synchronisation."""
        while self._sdf_tasks:
            await asyncio.gather(*list(self._sdf_tasks), return_exceptions=True)

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
        async with self._claim(job.id):
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

    async def resume_inflight_job(self, job: JobView, device_path: str) -> None:
        """Phase 9 — drive a crash-recovered rip from the boot probe.

        The backend's `/resume` endpoint resets tracks to QUEUED and
        sets `resumed_from_crash=True`; we then run the same rip-loop
        as a fresh disc would.

        Claims the single-flight gate exactly like `recover_held_job`, so a
        crash-resumed rip is abandonable via `job.abandoned` and makes
        `is_idle()` False (no double-rip from the heartbeat re-probe or from
        a reattach boot probe).
        """
        async with self._claim(job.id):
            with with_log_context(job_id=job.id):
                # Crash-resume skips the scan path, so refresh the key here too —
                # a rip resumed days after a crash must not run on a stale key.
                await self._prepare_makemkv()
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
        tracks = list(rip_start.tracks)
        # A DVD/BD rip whose drive drops off the bus mid-rip stops makemkvcon
        # and resumes on the drive's new node instead of failing every
        # remaining title (D-133). ISO and folder sources have no bus to drop.
        resumable = (
            disc_type in (DiscType.DVD, DiscType.BLURAY)
            and not is_file_source(device_path)
            and not all(t.kind in (TrackKind.DISC_BACKUP, TrackKind.DATA_DUMP) for t in tracks)
        )
        lost = asyncio.Event()
        # Track ids whose title the lost drive left unfinished, and the files
        # of every title that finished (kept across a resume).
        unfinished: set[str] = set()
        kept: set[Path] = set()
        # IN_PROGRESS is sent once per track across every pass.
        started: set[str] = set()

        async def on_track_start(track: TrackView) -> None:
            if track.status != TrackStatus.QUEUED or track.id in started:
                return
            started.add(track.id)
            with with_log_context(track_id=track.id):
                await self._patch_track_with_retry(track.id, status=TrackStatus.IN_PROGRESS)

        async def on_track_done(track: TrackView, result: RipResult) -> None:
            with with_log_context(track_id=track.id):
                if result.ok:
                    if result.output_path is not None:
                        kept.add(Path(result.output_path))
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
                elif resumable and (lost.is_set() or self._drive_gone(rip_path)):
                    # Not this title's fault: the drive went away under it.
                    # Leave it for the resume rather than failing it.
                    lost.set()
                    unfinished.add(track.id)
                    logger.info("track %s left for a resume: the drive disconnected (%s)", track.id, result.error)
                else:
                    await self._patch_track_with_retry(
                        track.id,
                        status=TrackStatus.FAILED,
                        last_error=result.error or "unknown error",
                    )
                    logger.warning("track %s failed err=%s", track.id, result.error)

        async def on_track_progress(track: TrackView, fraction: float, stats: TransferStats | None = None, /) -> None:
            with with_log_context(track_id=track.id):
                logger.debug("track %s progress=%.2f", track.id, fraction)
                if self._ws is not None:
                    payload: dict[str, object] = {
                        "track_id": track.id,
                        "progress_pct": round(fraction * 100, 1),
                    }
                    if stats is not None:
                        # Byte detail for a copy (the full-disc dump): the UI shows
                        # "X of Y GB at R MB/s" and derives the ETA from the rate.
                        payload["bytes_done"] = stats["bytes_done"]
                        payload["bytes_total"] = stats["bytes_total"]
                        payload["rate_bps"] = round(stats["rate_bps"]) if stats["rate_bps"] is not None else None
                        if "phase" in stats:
                            payload["phase"] = stats["phase"]
                    await self._ws.publish(
                        topic=f"ripper.progress.{job_id}",
                        event_type="ripper.progress",
                        payload=payload,
                    )

        min_length_seconds = (
            rip_start.min_length_seconds
            if rip_start.min_length_seconds is not None
            else self._default_min_length_seconds
        )
        rip_path = device_path
        rip_dir = output_dir
        skip: set[str] = set()
        resumes = 0
        while True:
            watcher = asyncio.create_task(self._watch_drive(rip_path, lost)) if resumable else None
            try:
                await rip_all(
                    disc_type=disc_type,
                    device_path=rip_path,
                    tracks=tracks,
                    output_dir=rip_dir,
                    on_track_start=on_track_start,
                    on_track_done=on_track_done,
                    on_track_progress=on_track_progress,
                    min_length_seconds=min_length_seconds,
                    stop=lost if resumable else None,
                    skip_track_ids=skip,
                    drive_lost=functools.partial(self._drive_gone, rip_path) if resumable else None,
                )
            finally:
                if watcher is not None:
                    watcher.cancel()
            if not (lost.is_set() and unfinished):
                break
            # The drive dropped off the bus mid-rip. Keep the disc's finished
            # titles and, once it is back, rip the rest with one more
            # `mkv all` on its new node (never per-title invocations).
            logger.warning(
                "drive disconnected mid-rip on %s; %d title(s) unfinished; waiting up to %.0fs for it to return",
                rip_path,
                len(unfinished),
                DEVICE_RETURN_WAIT_SECONDS,
            )
            returned = await self._await_drive_return() if resumes < MAX_DEVICE_RESUMES else None
            if returned is None:
                await self._fail_unfinished(tracks, unfinished, started, resumes)
                break
            resumes += 1
            _remove_partial_outputs(output_dir, kept)
            skip = {t.id for t in tracks} - unfinished
            unfinished.clear()
            lost.clear()
            rip_path = returned
            rip_dir = output_dir / f"resume-{resumes}"
            logger.info(
                "drive back at %s; resuming %d title(s) with one more mkv all (resume %d)",
                rip_path,
                len(tracks) - len(skip),
                resumes,
            )

        completed = await self._rip_complete_with_retry(job_id)
        logger.info("rip-complete job_id=%s status=%s", job_id, completed.status.value)

        # Eject the node the drive is at NOW — it may have renumbered during
        # the rip (USB replug); the path captured at rip start is a hint only.
        await self._eject_with_retry(self._device_path or device_path)
        await asyncio.sleep(EJECT_GRACE_SECONDS)

    def _drive_gone(self, path: str) -> bool:
        """The drive this rip runs on has left `path`: the poll loop moved the
        handle (absent, or a new node), or the node no longer answers."""
        if self._device.current != path:
            return True
        try:
            read_drive_status(path)
        except OSError as exc:
            return exc.errno in _ABSENT_ERRNOS
        return False

    async def _watch_drive(self, path: str, lost: asyncio.Event) -> None:
        """Set `lost` (which stops makemkvcon) once the drive leaves `path`.
        The poll loop keeps the handle current; this only reads it."""
        while not lost.is_set():
            if self._device.current != path:
                logger.warning("drive left %s mid-rip; stopping makemkvcon", path)
                lost.set()
                return
            await asyncio.sleep(DEVICE_WATCH_INTERVAL_SECONDS)

    async def _await_drive_return(self) -> str | None:
        """The node the drive came back on once it reports a readable disc,
        or None when it does not within DEVICE_RETURN_WAIT_SECONDS."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + DEVICE_RETURN_WAIT_SECONDS
        while True:
            path = self._device.current
            if path is not None:
                try:
                    if read_drive_status(path) == DriveState.DISC_OK:
                        return path
                except OSError:
                    pass
            if loop.time() >= deadline:
                return None
            await asyncio.sleep(DEVICE_WATCH_INTERVAL_SECONDS)

    async def _fail_unfinished(
        self, tracks: list[TrackView], unfinished: set[str], started: set[str], resumes: int
    ) -> None:
        """The drive did not come back: fail what it left, saying why."""
        reason = _disconnect_reason(resumes)
        logger.error("%s; %d title(s) not ripped", reason, len(unfinished))
        for track in tracks:
            if track.id not in unfinished:
                continue
            with with_log_context(track_id=track.id):
                if track.id not in started:
                    started.add(track.id)
                    await self._patch_track_with_retry(track.id, status=TrackStatus.IN_PROGRESS)
                await self._patch_track_with_retry(track.id, status=TrackStatus.FAILED, last_error=reason)

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
        # The drive vanished (unplugged / powered off) between rip-complete
        # and here — there's no live node to umount/eject, and retrying just
        # produces a misleading "failed after N attempts" for a drive that
        # was never coming back. The poll loop's absence handling owns
        # recovery once it reattaches.
        if self._device_path is None:
            logger.info("eject skipped: drive is absent")
            return
        # ISO sources have no tray to eject. probe_disc reads the file
        # directly via PyCdlib and makemkvcon opens it read-only; nothing
        # mounts it, so there's nothing to umount or eject.
        if is_file_source(device_path):
            logger.info("eject skipped: source is ISO file %s", device_path)
            return
        await self._run_command("umount", device_path, log_failure=False)
        if not await self._try_eject(device_path):
            logger.error(
                "eject %s failed after %d attempts; check host auto-mount config",
                device_path,
                len(EJECT_RETRY_DELAYS),
            )

    async def _try_eject(self, device_path: str) -> bool:
        """Run eject once per EJECT_RETRY_DELAYS entry, waiting that long first, until one succeeds; True if one
        did."""
        for attempt, delay in enumerate(EJECT_RETRY_DELAYS, start=1):
            if delay > 0:
                await asyncio.sleep(delay)
            rc, stderr = await self._run_command("eject", "-sv", device_path)
            if rc == 0:
                logger.info("ejected %s on attempt %d", device_path, attempt)
                return True
            logger.warning(
                "eject %s attempt %d failed (rc=%s): %s",
                device_path,
                attempt,
                rc,
                stderr or "<no stderr>",
            )
        return False

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
            with contextlib.suppress(ProcessLookupError):
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

    async def _retry_backend_call[T](self, call: Callable[[], Awaitable[T]], what: str) -> T:
        """Run one backend call, retrying a transient failure with doubling backoff up to PATCH_RETRY_MAX_SECONDS and
        re-raising a rejection."""
        delay = PATCH_RETRY_INITIAL_SECONDS
        while True:
            try:
                return await call()
            except httpx.HTTPError as e:
                if not self._is_retryable(e):
                    logger.error("%s rejected by backend (%s); giving up", what, e)
                    raise
                logger.warning("%s failed (%s); retrying in %.1fs", what, e, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, PATCH_RETRY_MAX_SECONDS)

    async def _rip_start_with_retry(self, job_id: str) -> RipStartResponse:
        """Mark the job ripping on the backend, retrying a transient failure."""
        return await self._retry_backend_call(lambda: self._client.rip_start(job_id), f"rip-start {job_id}")

    async def _rip_complete_with_retry(self, job_id: str) -> JobView:
        """Mark the job's rip complete on the backend, retrying a transient failure."""
        return await self._retry_backend_call(lambda: self._client.rip_complete(job_id), f"rip-complete {job_id}")

    async def _patch_track_with_retry(self, track_id: str, **fields: object) -> None:
        """PATCH one track's fields on the backend, retrying a transient failure."""
        await self._retry_backend_call(lambda: self._client.update_track(track_id, **fields), f"PATCH track {track_id}")


def _remove_partial_outputs(output_dir: Path, kept: set[Path]) -> None:
    """Before a resume: delete every .mkv under the job's raw folder that no
    finished title owns (the title the drive dropped mid-write, and anything a
    stopped pass left behind)."""
    for f in output_dir.rglob("*.mkv"):
        if f not in kept:
            f.unlink(missing_ok=True)
