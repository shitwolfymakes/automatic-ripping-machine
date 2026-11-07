"""Parking a held job at the identify or review gate until it leaves the gate."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from arm_common import JobStatus
from arm_common.schemas import JobView, RipperConfigView
from arm_ripper.backend_client import BackendClient
from arm_ripper.ripper_config import ripper_config_or_none

# The moved code keeps the job controller's logger name so existing log filters and log text stay the same.
logger = logging.getLogger("arm_ripper.job_controller")

POLL_MAX_SECONDS = 30.0
# Hard ceiling on awaiting_user_id wait; if no WS event arrives by then,
# fall back to one REST GET to handle a stale-WS edge case (boot race or
# extended outage). Beyond that, we assume the user abandoned the disc
# and return — the next disc-insert event re-triggers identify.
RESOLUTION_WAIT_TIMEOUT_SECONDS = 30 * 60.0
RESOLUTION_WS_FIRST_WAIT_SECONDS = 5.0


@dataclass(frozen=True)
class WaitSpec:
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
IDENTIFY_WAIT = WaitSpec(
    parked=JobStatus.AWAITING_USER_ID,
    success=frozenset({JobStatus.IDENTIFIED}),
    label="awaiting_user_id",
)
# Review gate (timed): disc identified but held for review; wait for Start (which
# transitions to ripping), the auto-start countdown (ripper self-starts → ripping),
# or the operator otherwise leaving the gate.
REVIEW_WAIT = WaitSpec(
    parked=JobStatus.AWAITING_REVIEW,
    success=frozenset({JobStatus.IDENTIFIED, JobStatus.RIPPING}),
    label="awaiting_review",
    timed=True,
)

# Sentinel distinguishing "resolution_timeout not passed" (defer to
# whatever RESOLUTION_WAIT_TIMEOUT_SECONDS currently is) from an explicit
# `resolution_timeout=None` (wait forever). A plain
# `resolution_timeout: float | None = RESOLUTION_WAIT_TIMEOUT_SECONDS`
# default would bind to that module constant's value once, at import time —
# invisible to a caller (or test) that reads/patches the live module
# attribute afterward, which is how every existing wait test already
# configures the timeout.
RESOLUTION_TIMEOUT_UNSET = object()


async def _woken_within(event: asyncio.Event, timeout: float) -> bool:
    """True when `event` is set within `timeout` seconds, False when the wait times out."""
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        return False
    return True


class ResolutionWaiter:
    """Parks a held job until it leaves its gate: WS wake, periodic REST poll, review countdown, timeout."""

    def __init__(
        self,
        client: BackendClient,
        resolution_timeout: float | None = RESOLUTION_TIMEOUT_UNSET,  # type: ignore[assignment]
    ) -> None:
        self._client = client
        # Ceiling on an AWAITING_USER_ID / AWAITING_REVIEW park, in seconds.
        # None means wait indefinitely — source mode's one-shot container must
        # not exit (and have the backend watchdog mark the job FAILED) while
        # the operator is still reviewing; see `_wait_for_resolution`.
        self._resolution_timeout: float | None = (
            RESOLUTION_WAIT_TIMEOUT_SECONDS if resolution_timeout is RESOLUTION_TIMEOUT_UNSET else resolution_timeout
        )
        # job_id → asyncio.Event signalled when an `identify.resolved`
        # arrives over WS. Populated by `await_resolution`, drained by
        # `wake`.
        self._resolution_events: dict[str, asyncio.Event] = {}
        # Jobs whose countdown hold for a guessed placement was already logged.
        self._held_for_guess: set[str] = set()

    def wake(self, job_id: str) -> bool:
        """Set the wait event of the pipeline parked on this job, if one is; True when there was one."""
        event = self._resolution_events.get(job_id)
        if event is None:
            return False
        event.set()
        return True

    async def await_resolution(self, job_id: str, spec: WaitSpec = IDENTIFY_WAIT) -> JobView | None:
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

    def _classify_wait(self, view: JobView | None, job_id: str, spec: WaitSpec) -> tuple[str, JobView | None]:
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

    async def _wait_for_resolution(self, job_id: str, event: asyncio.Event, spec: WaitSpec) -> JobView | None:
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

    async def _first_wait(self, job_id: str, event: asyncio.Event, spec: WaitSpec) -> tuple[str, JobView | None]:
        """The short first wait for a WS wake. On a timeout, one REST read covers a gate-leaving broadcast that went
        out before the subscription was up. Returns the `_classify_wait` outcome, or ("wait", None) after a wake."""
        if await _woken_within(event, RESOLUTION_WS_FIRST_WAIT_SECONDS):
            return ("wait", None)
        return self._classify_wait(await self._safe_get_job(job_id), job_id, spec)

    async def _wait_cycle(self, job_id: str, event: asyncio.Event, spec: WaitSpec) -> tuple[str, JobView | None]:
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

    async def _auto_start_due(self, view: JobView | None, spec: WaitSpec) -> bool:
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

    async def _safe_get_ripper_config(self) -> RipperConfigView | None:
        """Ripper config (ripping_paused + manual_wait_seconds) for the review
        countdown. None on transport error → the caller treats it as 'can't tell;
        keep waiting' (fail-safe: never auto-rip on a config blip)."""
        return await ripper_config_or_none(self._client, "get_ripper_config", "keeping countdown suspended")
