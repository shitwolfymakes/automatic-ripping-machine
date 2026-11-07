import asyncio
import contextlib
import functools
import logging
import shutil
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx

from arm_common import DiscType, Job, JobStatus, TrackKind, TrackStatus, with_log_context
from arm_common.schemas import JobView, RipStartResponse, ScanResult, TrackView, WSEnvelope
from arm_ripper.backend_client import BackendClient
from arm_ripper.background_tasks import spawn_tracked
from arm_ripper.backend_retry import BackendRetry
from arm_ripper.drive_handle import DriveHandle
from arm_ripper.eject import Ejector
from arm_ripper.makemkv_prep import MakeMKVPrep
from arm_ripper.ripper_config import ripper_config_or_none
from arm_ripper.resolution_wait import IDENTIFY_WAIT, RESOLUTION_TIMEOUT_UNSET, REVIEW_WAIT, ResolutionWaiter, WaitSpec
from arm_ripper.rip import RipResult, rip_all
from arm_ripper.rip.dispatcher import DEFAULT_MIN_LENGTH_SECONDS
from arm_ripper.rip.track_callbacks import TransferStats
from arm_ripper.disc_scan import scan_or_none
from arm_ripper.drive_poll import DriveErrorKind, DriveState, classify_drive_error, read_drive_status
from arm_ripper.source import is_file_source
from arm_ripper.ws_client import WSClient

logger = logging.getLogger("arm_ripper.job_controller")

EJECT_GRACE_SECONDS = 3.0
# A DVD/BD drive that drops off the bus mid-rip (a USB enclosure reset; it
# often re-enumerates under a new srN): how long the rip waits for it to come
# back with the disc readable before finishing the job as partial, how often
# it looks, and how many times one rip may resume.
DEVICE_RETURN_WAIT_SECONDS = 180.0
DEVICE_WATCH_INTERVAL_SECONDS = 1.0
MAX_DEVICE_RESUMES = 3
RAW_ROOT = Path("/raw")


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


def _resumable(disc_type: DiscType, device_path: str, tracks: list[TrackView]) -> bool:
    """Whether a rip can wait out its drive dropping off the bus and resume on the drive's new node: a DVD or BD read
    from a real drive, unless every track is a full-disc backup or dump."""
    # A DVD/BD rip whose drive drops off the bus mid-rip stops makemkvcon
    # and resumes on the drive's new node instead of failing every
    # remaining title (D-133). ISO and folder sources have no bus to drop.
    return (
        disc_type in (DiscType.DVD, DiscType.BLURAY)
        and not is_file_source(device_path)
        and not all(t.kind in (TrackKind.DISC_BACKUP, TrackKind.DATA_DUMP) for t in tracks)
    )


def _done_fields(result: RipResult) -> dict[str, object]:
    """The track patch for a finished title: DONE, plus each of its output path, size, checksum and duration that the
    rip reported."""
    fields: dict[str, object] = {"status": TrackStatus.DONE}
    if result.output_path is not None:
        fields["output_path"] = str(result.output_path)
    if result.size_bytes is not None:
        fields["size_bytes"] = result.size_bytes
    if result.sha256 is not None:
        fields["sha256"] = result.sha256
    if result.duration_seconds is not None:
        fields["duration_seconds"] = result.duration_seconds
    return fields


def _progress_payload(track_id: str, fraction: float, stats: TransferStats | None) -> dict[str, object]:
    """The WS progress payload for a track: its percentage, plus the byte detail, rounded rate and phase of a copy
    when the rip reports them."""
    payload: dict[str, object] = {
        "track_id": track_id,
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
    return payload


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
        resolution_timeout: float | None = RESOLUTION_TIMEOUT_UNSET,  # type: ignore[assignment]
    ) -> None:
        self._client = client
        # The retried backend calls a rip makes (rip-start, rip-complete, track PATCH, identify).
        self._backend = BackendRetry(client, drive_id)
        # Getting MakeMKV ready for a disc: key refresh plus the background KEYDB/SDF refreshes.
        self._makemkv = MakeMKVPrep(client)
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
        # Umount/eject is its own job; it reads the same shared handle.
        self._ejector = Ejector(self._device)
        # Host-side baseline `--minlength` for `makemkvcon mkv all`. The
        # backend can override per-rip via `RipStartResponse.min_length_seconds`
        # (resolved from the Session's `overrides_json["min_length_seconds"]`);
        # when no override is sent we fall back to this value. Injected by
        # `main.py` from `ARM_MIN_LENGTH_SECONDS`; tests get the dispatcher
        # default (600).
        self._default_min_length_seconds = default_min_length_seconds
        # Parks a held job until it leaves its gate. `resolution_timeout` is the ceiling on an
        # AWAITING_USER_ID / AWAITING_REVIEW park, in seconds; None means wait indefinitely — source
        # mode's one-shot container must not exit (and have the backend watchdog mark the job FAILED)
        # while the operator is still reviewing.
        self._waiter = ResolutionWaiter(client, resolution_timeout)
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
        if self._waiter.wake(job_id):
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
        # Also wake any `ResolutionWaiter.await_resolution` waiter — abandoning a parked
        # job needs to unstick the pipeline the same way `identify.resolved`
        # does. The waiter polls and decides based on the new job status.
        self._waiter.wake(job_id)

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
            spawn_tracked(self._wipe_raw(job_id), self._wipe_tasks)
        if self._abandon_ejects(owns):
            self._spawn_eject()

    def _abandon_ejects(self, owns: bool) -> bool:
        """Whether an abandon gives the disc back: "done with this disc, give it back".

        The lifecycle's post-rip eject (end of _run_rip) never runs on an abandon exit, so eject here: when this
        job owns the drive's pipeline (ripping or parked; Ejector.eject's EBUSY retries absorb the cancelled
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
        self._eject_task = asyncio.create_task(self._ejector.eject(self._device_path))

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
        # this is a no-op on standard deployments.
        if not await self._auto_rip_enabled():
            logger.info("disc-inserted ignored: auto_rip_on_insert=false; trigger via UI to start a rip")
            return
        await self._run_pipeline(device_path, pending_session_id=None)

    async def _auto_rip_enabled(self) -> bool:
        """Whether a disc insert should start a rip: the auto_rip_on_insert switch, or True when the config can't be
        read (fail-open, so a flapping backend never silently halts ripping)."""
        cfg = await ripper_config_or_none(self._client, "auto-rip config lookup", "proceeding fail-open")
        return cfg is None or cfg.auto_rip_on_insert

    async def _run_pipeline(self, device_path: str, *, pending_session_id: str | None) -> None:
        async with self._claim(None):
            # Refresh the MakeMKV key before makemkvcon first touches
            # the disc (the scan probe runs it for every disc), so a
            # container up across a beta-key rotation doesn't scan/rip
            # protected discs with a stale key.
            await self._makemkv.prepare()
            scan_result = await scan_or_none(device_path)
            if scan_result is None:
                return

            job = await self._identify_or_none(scan_result, device_path, pending_session_id=pending_session_id)
            if job is None:
                return
            self._active_job_id = job.id

            # Phase 12 — every log line below carries job_id once identify lands.
            with with_log_context(job_id=job.id):
                if not await self._pass_gate(job, IDENTIFY_WAIT):
                    return

                # Timed review gate: the backend parks an identified disc here
                # when hold_for_review is on. Wait for Start (-> ripping) or the
                # auto-start path (-> identified); either proceeds to the rip.
                if not await self._pass_gate(job, REVIEW_WAIT):
                    return

                # Proceed for: identified (normal / operator Start landed),
                # ripping (operator Start already transitioned), or
                # awaiting_review (timed auto-start — rip-start transitions it).
                if job.status not in (JobStatus.IDENTIFIED, JobStatus.RIPPING, JobStatus.AWAITING_REVIEW):
                    logger.info("job %s in unexpected status %s; not ripping", job.id, job.status.value)
                    return

                await self._run_rip_guarded(job, device_path)

    async def _pass_gate(self, job: Job, spec: WaitSpec) -> bool:
        """Wait a job parked at `spec`'s gate until it leaves, recording the status it left in; True unless it left
        the gate some other way (abandoned). A job not parked there passes straight through."""
        if job.status != spec.parked:
            return True
        resolved = await self._waiter.await_resolution(job.id, spec)
        if resolved is None:
            return False
        job.status = resolved.status
        return True

    async def _run_rip_guarded(self, job: Job, device_path: str) -> None:
        """Run the rip. A backend rejection of a state transition is logged and ends the pipeline; a cancel (abandon)
        is logged and propagates."""
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

    async def _identify_or_none(
        self, scan_result: ScanResult, device_path: str, *, pending_session_id: str | None
    ) -> Job | None:
        """Identify the scanned disc, or None when the backend refuses it: a disc ripped before is ejected, and any
        other rejection parks the pipeline."""
        try:
            return await self._backend.identify(scan_result, pending_session_id=pending_session_id)
        except httpx.HTTPStatusError as e:
            if _previously_ripped(e.response):
                # on_previously_ripped=reject: the backend made no job
                # and told the operator; give the disc back.
                logger.info("disc already ripped (on_previously_ripped=reject); ejecting %s", device_path)
                await self._ejector.eject(device_path)
                return None
            # Non-retriable identify rejection (e.g. 409 ripping-paused). Park
            # the pipeline quietly; the caller's claim releases the drive.
            logger.info(
                "rip pipeline not started: identify rejected (%s) for drive %s",
                e.response.status_code,
                self._drive_id,
            )
            return None

    async def _run_rip(self, job: Job | JobView, device_path: str) -> None:
        rip_start = await self._backend.rip_start(job.id)
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
                resolved = await self._waiter.await_resolution(job.id, REVIEW_WAIT)
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
                await self._makemkv.prepare()
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
        """Rip every title of the disc, report rip-complete and eject."""
        await _DiscRip(self, job_id=job_id, disc_type=disc_type, device_path=device_path, rip_start=rip_start).run()


class _DiscRip:
    """One disc's rip across its resumes: rip every title, leave the titles a lost drive cut short for one more pass
    on the drive's new node, then report rip-complete and eject."""

    def __init__(
        self,
        controller: "JobController",
        *,
        job_id: str,
        disc_type: DiscType,
        device_path: str,
        rip_start: RipStartResponse,
    ) -> None:
        self._controller = controller
        self._job_id = job_id
        self._disc_type = disc_type
        # The node at rip start; the controller's own `_device_path` is the live one.
        self._start_path = device_path
        self._output_dir = RAW_ROOT / job_id
        self._tracks = list(rip_start.tracks)
        self._resumable = _resumable(disc_type, device_path, self._tracks)
        self._lost = asyncio.Event()
        # Track ids whose title the lost drive left unfinished, and the files
        # of every title that finished (kept across a resume).
        self._unfinished: set[str] = set()
        self._kept: set[Path] = set()
        # IN_PROGRESS is sent once per track across every pass.
        self._started: set[str] = set()
        self._min_length_seconds = (
            rip_start.min_length_seconds
            if rip_start.min_length_seconds is not None
            else controller._default_min_length_seconds
        )
        self._rip_path = device_path
        self._rip_dir = self._output_dir
        self._skip: set[str] = set()
        self._resumes = 0

    async def _on_track_start(self, track: TrackView) -> None:
        """Mark a queued track IN_PROGRESS, once across every pass."""
        if track.status != TrackStatus.QUEUED or track.id in self._started:
            return
        self._started.add(track.id)
        with with_log_context(track_id=track.id):
            await self._controller._backend.patch_track(track.id, status=TrackStatus.IN_PROGRESS)

    async def _on_track_done(self, track: TrackView, result: RipResult) -> None:
        """Record a finished title as done, left for a resume, or failed."""
        with with_log_context(track_id=track.id):
            if result.ok:
                await self._record_ripped(track, result)
            elif self._drive_left_under_it():
                self._leave_for_resume(track, result)
            else:
                await self._record_failed(track, result)

    def _drive_left_under_it(self) -> bool:
        """Whether a failed title's drive went away under it (so it is left for a resume): only a resumable rip whose
        drive is already marked lost, or has left its node."""
        return self._resumable and (self._lost.is_set() or self._drive_gone(self._rip_path))

    async def _record_ripped(self, track: TrackView, result: RipResult) -> None:
        """Keep a ripped title's file and patch the track DONE."""
        if result.output_path is not None:
            self._kept.add(Path(result.output_path))
        await self._controller._backend.patch_track(track.id, **_done_fields(result))
        logger.info(
            "track %s done size=%s duration=%s",
            track.id,
            result.size_bytes,
            result.duration_seconds,
        )

    def _leave_for_resume(self, track: TrackView, result: RipResult) -> None:
        """Mark the drive lost and leave the title unfinished for the resume pass."""
        # Not this title's fault: the drive went away under it.
        # Leave it for the resume rather than failing it.
        self._lost.set()
        self._unfinished.add(track.id)
        logger.info("track %s left for a resume: the drive disconnected (%s)", track.id, result.error)

    async def _record_failed(self, track: TrackView, result: RipResult) -> None:
        """Patch the track FAILED with the rip's error."""
        await self._controller._backend.patch_track(
            track.id,
            status=TrackStatus.FAILED,
            last_error=result.error or "unknown error",
        )
        logger.warning("track %s failed err=%s", track.id, result.error)

    async def _on_track_progress(
        self, track: TrackView, fraction: float, stats: TransferStats | None = None, /
    ) -> None:
        """Publish a track's progress to the websocket hub, when one is connected."""
        with with_log_context(track_id=track.id):
            logger.debug("track %s progress=%.2f", track.id, fraction)
            if self._controller._ws is not None:
                await self._controller._ws.publish(
                    topic=f"ripper.progress.{self._job_id}",
                    event_type="ripper.progress",
                    payload=_progress_payload(track.id, fraction, stats),
                )

    def _drive_gone(self, path: str) -> bool:
        """The drive this rip runs on has left `path`: the poll loop moved the
        handle (absent, or a new node), or the node no longer answers."""
        if self._controller._device.current != path:
            return True
        try:
            read_drive_status(path)
        except OSError as exc:
            return classify_drive_error(exc) is DriveErrorKind.ABSENT
        return False

    async def _watch_drive(self, path: str) -> None:
        """Set the lost event (which stops makemkvcon) once the drive leaves `path`.
        The poll loop keeps the handle current; this only reads it."""
        while not self._lost.is_set():
            if self._controller._device.current != path:
                logger.warning("drive left %s mid-rip; stopping makemkvcon", path)
                self._lost.set()
                return
            await asyncio.sleep(DEVICE_WATCH_INTERVAL_SECONDS)

    async def _await_drive_return(self) -> str | None:
        """The node the drive came back on once it reports a readable disc,
        or None when it does not within DEVICE_RETURN_WAIT_SECONDS."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + DEVICE_RETURN_WAIT_SECONDS
        while True:
            path = self._controller._device.current
            if path is not None:
                try:
                    if read_drive_status(path) == DriveState.DISC_OK:
                        return path
                except OSError:
                    pass
            if loop.time() >= deadline:
                return None
            await asyncio.sleep(DEVICE_WATCH_INTERVAL_SECONDS)

    async def _fail_unfinished(self) -> None:
        """The drive did not come back: fail what it left, saying why."""
        reason = _disconnect_reason(self._resumes)
        logger.error("%s; %d title(s) not ripped", reason, len(self._unfinished))
        for track in self._tracks:
            if track.id not in self._unfinished:
                continue
            with with_log_context(track_id=track.id):
                if track.id not in self._started:
                    self._started.add(track.id)
                    await self._controller._backend.patch_track(track.id, status=TrackStatus.IN_PROGRESS)
                await self._controller._backend.patch_track(track.id, status=TrackStatus.FAILED, last_error=reason)

    async def run(self) -> None:
        """Rip the disc through its resumes, then finish it."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        while True:
            await self._run_pass()
            if not (self._lost.is_set() and self._unfinished):
                break
            # The drive dropped off the bus mid-rip. Keep the disc's finished
            # titles and, once it is back, rip the rest with one more
            # `mkv all` on its new node (never per-title invocations).
            logger.warning(
                "drive disconnected mid-rip on %s; %d title(s) unfinished; waiting up to %.0fs for it to return",
                self._rip_path,
                len(self._unfinished),
                DEVICE_RETURN_WAIT_SECONDS,
            )
            returned = await self._await_drive_return() if self._resumes < MAX_DEVICE_RESUMES else None
            if returned is None:
                await self._fail_unfinished()
                break
            self._prepare_resume(returned)

        await self._finish()

    async def _run_pass(self) -> None:
        """One `mkv all` pass over the disc on its current node, with a watcher that stops makemkvcon if the drive
        leaves that node (resumable rips only)."""
        watcher = asyncio.create_task(self._watch_drive(self._rip_path)) if self._resumable else None
        try:
            await rip_all(
                disc_type=self._disc_type,
                device_path=self._rip_path,
                tracks=self._tracks,
                output_dir=self._rip_dir,
                on_track_start=self._on_track_start,
                on_track_done=self._on_track_done,
                on_track_progress=self._on_track_progress,
                min_length_seconds=self._min_length_seconds,
                stop=self._lost if self._resumable else None,
                skip_track_ids=self._skip,
                drive_lost=(functools.partial(self._drive_gone, self._rip_path) if self._resumable else None),
            )
        finally:
            if watcher is not None:
                watcher.cancel()

    def _prepare_resume(self, returned: str) -> None:
        """Set up the next pass on the node the drive came back on: drop the partial files, skip every title already
        settled, and rip into a fresh resume folder."""
        self._resumes += 1
        _remove_partial_outputs(self._output_dir, self._kept)
        self._skip = {t.id for t in self._tracks} - self._unfinished
        self._unfinished.clear()
        self._lost.clear()
        self._rip_path = returned
        self._rip_dir = self._output_dir / f"resume-{self._resumes}"
        logger.info(
            "drive back at %s; resuming %d title(s) with one more mkv all (resume %d)",
            self._rip_path,
            len(self._tracks) - len(self._skip),
            self._resumes,
        )

    async def _finish(self) -> None:
        """Report rip-complete, then eject the drive at the node it is on now and give it a moment to settle."""
        completed = await self._controller._backend.rip_complete(self._job_id)
        logger.info("rip-complete job_id=%s status=%s", self._job_id, completed.status.value)

        # Eject the node the drive is at NOW — it may have renumbered during
        # the rip (USB replug); the path captured at rip start is a hint only.
        await self._controller._ejector.eject(self._controller._device_path or self._start_path)
        await asyncio.sleep(EJECT_GRACE_SECONDS)


def _remove_partial_outputs(output_dir: Path, kept: set[Path]) -> None:
    """Before a resume: delete every .mkv under the job's raw folder that no
    finished title owns (the title the drive dropped mid-write, and anything a
    stopped pass left behind)."""
    for f in output_dir.rglob("*.mkv"):
        if f not in kept:
            f.unlink(missing_ok=True)
