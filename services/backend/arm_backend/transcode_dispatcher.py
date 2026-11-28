"""Background dispatcher: spawn transcoder containers, sweep stale claims.

The dispatcher is a single asyncio task started in `main.py` lifespan. Every
`ARM_TRANSCODE_DISPATCH_INTERVAL_SECONDS` ticks it:

1. Sweeps stale claims (every tick — cheap; just one UPDATE).
2. Counts `transcode_tasks WHERE status='in_progress'` and, if below
   `MAX_PARALLEL_TRANSCODES`, dequeues queued tasks via
   `SELECT ... FOR UPDATE SKIP LOCKED LIMIT N` and spawns one container per
   row via the docker socket.
3. The `.arm-inprogress` orphan sweep runs once at lifespan startup (called
   directly by `main.py` before the dispatcher loop kicks off).

Cancel-running flow lives here too: emit `task.cancel` on
`transcoder.commands.{task_id}`, wait 10 s for the transcoder to call
/fail, then docker-stop any survivor by label scan.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

import docker.errors  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import col, select

from arm_backend.config import Settings
from arm_backend.container_logging import log_config
from arm_backend.docker_client import HealingDockerClient
from arm_backend.docker_probe import (
    TtlProbe,
    certs_dir_difference,
    probe_backend_url,
    probe_docker,
    probe_transcode_ca,
)
from arm_backend.gpu_claim import (
    GpuAssignment,
    assignment_before_device_lookup,
    assignment_when_only_family_invalid,
    assignment_with_no_candidate,
    exclude_ffmpeg_engine,
    exclude_invalid_families,
    invalid_families_or_failure,
    issue_messages,
    pick_free_gpu,
    release_gpu_for_task,
)
from arm_backend.log_safely import log_safely
from arm_backend.transcode_container_spec import (
    backend_url_for_spawn,
    container_identity_env,
    gpu_env,
    gpu_run_kwargs,
    spawn_network,
    task_env,
    task_volumes,
)
from arm_backend.transcode_image_pool import TranscodeImagePool
from arm_backend.transcode_images import image_for
from arm_backend.staging import stage_for_track
from arm_backend.transcode_sweeps import TranscodeSweeps
from arm_backend.transcode_task_events import GpuWaitLog, announce_failed
from arm_backend.transcode_queue import max_parallel_transcodes, resolve_preset_for_task
from arm_common import (
    Gpu,
    GpuStatus,
    GpuVendor,
    SessionApplication,
    StageStatus,
    TrackStage,
    TranscodePreset,
    TranscodeTask,
    TranscodeTaskStatus,
    with_log_context,
)
from arm_common.encoders import (
    gpu_encoder_for,
    gpu_is_eligible,
    vendor_supports_container,
)

if TYPE_CHECKING:
    from arm_backend.handbrake_schema_store import SchemaStore
    from arm_backend.ws.hub import WSHub
    from arm_common.encoders import EncoderSpec
    from arm_common.handbrake_schema.types import HandbrakeSchema
    from arm_common.schemas import SettingIssue

logger = logging.getLogger("arm_backend.transcode_dispatcher")


# How long after `task.cancel` we wait for the transcoder to call /fail
# gracefully before falling back to `docker stop`.
_CANCEL_GRACE_SECONDS = 10
_DOCKER_LABEL_KEY = "arm.task_id"

# Log lines read from a container before it is discarded, and how many of its
# error lines go into the task's last_error.
_LOG_TAIL_LINES = 50
_ERROR_TAIL_LINES = 2
_ERROR_LINE = re.compile(r"error|fail|exception|refused|denied|traceback", re.IGNORECASE)


def _is_name_conflict(exc: docker.errors.APIError) -> bool:
    return exc.status_code == 409 and "already in use" in str(exc)


def _error_tail(raw: bytes | str) -> str:
    """The last distinct error-looking lines of a container log, joined; the
    last plain lines when none look like errors."""
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    errors = [ln for ln in lines if _ERROR_LINE.search(ln)] or lines
    distinct = list(dict.fromkeys(errors))[-_ERROR_TAIL_LINES:]
    return " | ".join(distinct)[:200]


# Why a deployment cannot run encode work (or a GPU probe) at all: shared by
# `probe()` and the GPU probe endpoints so both report the same reason.
NO_DOCKER_CLIENT_DETAIL = "no docker client (ripper-only deployment or docker unavailable)"

# Per-tick cap on how many ENCODE rows spawn_pending examines (spawn
# attempts, GPU claim checks, etc). Passthrough tasks are exempt from this
# cap entirely and the queued scan itself is unbounded, so a run of 50+
# held/queued encode rows at the head of the FIFO queue can never crowd a
# passthrough task further back out of the scan window.
_QUEUE_SCAN_LIMIT = 50
# While `probe()` says the transcode image or docker host is unusable, encode
# spawns are skipped and one line says why, repeated at most this often.
_PROBE_HOLD_LOG_SECONDS = 600


def _enabled_vendors(gpus: Sequence[Gpu]) -> set[GpuVendor]:
    """The vendors that have at least one enabled device in `gpus`."""
    return {g.vendor for g in gpus if g.enabled}


# The running backend's dispatcher, for code paths with no app handle (the
# apply-time encoder gate). None outside a running backend.
_active_dispatcher: TranscodeDispatcher | None = None


def set_active_dispatcher(dispatcher: TranscodeDispatcher | None) -> None:
    global _active_dispatcher  # noqa: PLW0603 - one dispatcher per backend process
    _active_dispatcher = dispatcher


def gpu_awaiting_probe(gpu: Gpu) -> bool:
    """`TranscodeDispatcher.awaiting_probe` on the running dispatcher; False
    when none is running."""
    return _active_dispatcher is not None and _active_dispatcher.awaiting_probe(gpu)


_ACTIVE_STAGE = (StageStatus.PENDING, StageStatus.COPYING, StageStatus.STALLED)


def held_for_staging(stage: TrackStage | None, preset: TranscodePreset | None) -> bool:
    """Whether a queued task must wait for its source track's stage.

    An encode task needs the staged copy, so it waits unless the stage is STAGED. A passthrough task moves
    raw, so it only waits while a stage is still reading it."""
    from arm_backend.transcode_apply import is_passthrough_preset

    if is_passthrough_preset(preset):
        return stage is not None and stage.status in _ACTIVE_STAGE
    return stage is None or stage.status != StageStatus.STAGED


class _SpawnPass:
    """One `TranscodeDispatcher.spawn_pending` pass over the queued tasks, holding the pass's counters and its
    cached host probe."""

    def __init__(self, dispatcher: TranscodeDispatcher, db: AsyncSession) -> None:
        self._dispatcher = dispatcher
        self._db = db
        self.enabled: bool = False
        self.host_probe: tuple[bool, str | None] | None = None
        self.encode_slots: int = 0
        self.spawned: int = 0
        self.held_encode: int = 0
        self.held_staging: int = 0
        self.encode_examined: int = 0

    async def run(self) -> int:
        from arm_backend.transcode_apply import transcode_enabled_now

        self.enabled = await transcode_enabled_now(self._db)
        # `probe()` (cached, blocking) is consulted once per tick, and only
        # when an encode task is actually ready to spawn.
        self.host_probe = None

        queued_ids = await self._queued_task_ids()
        awaiting = self._dispatcher._awaiting_checkin
        for gone in [tid for tid in awaiting if tid not in queued_ids]:
            del awaiting[gone]  # claimed (or cancelled): it checked in
        # A container still starting up holds its slot until it claims.
        self.encode_slots = await self._free_encode_slots() - len(awaiting)
        for task_id in queued_ids:
            await self._handle_queued(task_id)
        if self.held_encode:
            logger.debug(
                "%d encode task(s) held (enabled=%s docker=%s)",
                self.held_encode,
                self.enabled,
                self._dispatcher._docker is not None,
            )
        if self.held_staging:
            logger.debug("%d task(s) held waiting for staged files", self.held_staging)
        await self._db.commit()
        await log_safely("transcode.waiting", self._dispatcher.gpu_waits.settle(self._db))
        return self.spawned

    async def _free_encode_slots(self) -> int:
        in_progress = (
            (
                await self._db.execute(
                    select(TranscodeTask).where(col(TranscodeTask.status) == TranscodeTaskStatus.IN_PROGRESS)
                )
            )
            .scalars()
            .all()
        )
        return await max_parallel_transcodes(
            self._db, default=self._dispatcher._settings.MAX_PARALLEL_TRANSCODES
        ) - len(in_progress)

    async def _queued_task_ids(self) -> list[str]:
        queued_rows = (
            (
                await self._db.execute(
                    select(TranscodeTask)
                    .where(col(TranscodeTask.status) == TranscodeTaskStatus.QUEUED)
                    .order_by(col(TranscodeTask.created_at).asc())
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        return [row.id for row in queued_rows]

    async def _reload_locked(self, task_id: str) -> TranscodeTask | None:
        # Fresh, locked, forcibly-repopulated load of this row's CURRENT
        # state -- never the batch-select object in `_queued_task_ids` (see
        # the `TranscodeDispatcher.spawn_pending` docstring).
        # `populate_existing=True` is required even though the row is
        # also `with_for_update()`-locked here: an identity-map hit that
        # ISN'T expired would otherwise silently keep serving whatever
        # attributes it already had cached, ignoring this query's result.
        task = (
            await self._db.execute(
                select(TranscodeTask)
                .where(col(TranscodeTask.id) == task_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if task is None or task.status != TranscodeTaskStatus.QUEUED:
            logger.debug("task_id=%s no longer claimable (gone or status changed); skipping", task_id)
            return None
        return task

    async def _job_id_for(self, task: TranscodeTask) -> str | None:
        # Load the owning application once so the spawn log lines carry
        # job_id for the per-job log view.
        application = (
            await self._db.execute(
                select(SessionApplication).where(col(SessionApplication.id) == task.session_application_id)
            )
        ).scalar_one_or_none()
        return application.job_id if application is not None else None

    async def _run_passthrough_isolated(self, task: TranscodeTask, task_id: str) -> None:
        from arm_backend.passthrough_executor import execute_passthrough_task

        # Never counted against encode_slots/encode_examined and
        # never held by the disabled/docker-less gates in `_admit_encode`: a
        # file move needs neither a container nor an encode slot.
        # Isolated per-task try/except: a raise here (hub.emit,
        # aggregate, or an unexpected DB error) must never abort
        # the tick and roll back other tasks' already-committed
        # work or in-flight GPU claims (see execute_passthrough_task
        # for the commit-per-task structure that makes this safe).
        # `db.rollback()` on the way out is required, not optional:
        # a raise from inside a flush/commit leaves the session in
        # "pending rollback" state, and the NEXT statement this
        # function issues (for the next queued task) would raise
        # PendingRollbackError outside any try/except and abort the
        # whole tick. The log line uses the loop variable
        # `task_id`, never `task.id`: after a failed flush/commit
        # every identity-mapped object is unreadable until the
        # rollback, so an ORM attribute read here would raise
        # PendingRollbackError out of this except block.
        try:
            await execute_passthrough_task(self._db, task, self._dispatcher._hub, self._dispatcher._settings)
        except Exception as exc:
            logger.exception("passthrough execution failed task_id=%s: %s", task_id, exc)
            await self._db.rollback()

    async def _admit_encode(self) -> bool:
        if self.encode_examined >= _QUEUE_SCAN_LIMIT:
            # Encode-only cap; passthrough tasks further back in the
            # queue are still scanned and still run.
            return False
        self.encode_examined += 1
        if not self.enabled:
            self.held_encode += 1
            return False
        if self._dispatcher._docker is None or not self._dispatcher.host_paths_set():
            self.held_encode += 1
            return False
        if self.encode_slots - self.spawned <= 0:
            # No free slot this tick; later passthrough tasks in the
            # queue must still run, so skip (not `break`).
            return False
        if self.host_probe is None:
            self.host_probe = await asyncio.to_thread(self._dispatcher._probe_pulling_base_image)
            self._dispatcher._log_probe_hold(self.host_probe)
        if not self.host_probe[0]:
            # A missing image or unreachable host fails every spawn
            # the same way; hold the task instead of looping a
            # traceback per tick or burning its attempts.
            self.held_encode += 1
            return False
        return True

    async def _handle_queued(self, task_id: str) -> None:
        from arm_backend.transcode_apply import is_passthrough_preset

        task = await self._reload_locked(task_id)
        if task is None:
            return
        job_id = await self._job_id_for(task)
        with with_log_context(job_id=job_id, session_application_id=task.session_application_id):
            preset = await resolve_preset_for_task(self._db, task)
            stage = await stage_for_track(self._db, task.source_track_id)
            if held_for_staging(stage, preset):
                self._note_held_for_staging(task, stage)
                return
            if is_passthrough_preset(preset):
                await self._run_passthrough_isolated(task, task_id)
                return
            if await self._awaiting_checkin(task_id):
                return
            if not await self._admit_encode():
                return
            await self._claim_and_spawn(task, task_id, preset)

    async def _awaiting_checkin(self, task_id: str) -> bool:
        """True while a container spawned for this still-queued task has not
        claimed it: respawning would collide with its container name. Past
        `ARM_TRANSCODE_CHECKIN_TIMEOUT_SECONDS` the container is discarded
        and an attempt counted; the next tick then spawns afresh."""
        entry = self._dispatcher._awaiting_checkin.get(task_id)
        if entry is None:
            return False
        name, spawned_at = entry
        limit = self._dispatcher._settings.ARM_TRANSCODE_CHECKIN_TIMEOUT_SECONDS
        if time.monotonic() - spawned_at >= limit:
            await self._expire_checkin(task_id, name, limit)
        return True

    async def _expire_checkin(self, task_id: str, name: str, limit: int) -> None:
        dispatcher = self._dispatcher
        tail = await asyncio.to_thread(dispatcher._discard_container, name, task_id)
        del dispatcher._awaiting_checkin[task_id]
        if not await self._still_queued(task_id):
            # The removal takes seconds; a /claim that committed meanwhile owns the task and its GPU. The
            # stale-claim sweep recovers it if its transcoder went with the container.
            logger.warning("transcode task_id=%s claimed while its container %s was being removed", task_id, name)
            return
        reason = f"transcoder did not check in within {limit} s"
        if tail:
            reason += f": {tail}"
        dispatcher.last_spawn_error = reason[:300]
        logger.error("transcode container %s for task_id=%s removed: %s", name, task_id, reason)
        try:
            await release_gpu_for_task(self._db, task_id)
            await dispatcher._count_failed_spawn(self._db, task_id, reason, spawned=True)
        except Exception:
            logger.exception("could not count the check-in timeout task_id=%s", task_id)
            await self._db.rollback()

    async def _still_queued(self, task_id: str) -> bool:
        """Whether `task_id` is still QUEUED, read fresh (no transcoder has claimed it)."""
        task = (
            await self._db.execute(
                select(TranscodeTask).where(col(TranscodeTask.id) == task_id).execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        return task is not None and task.status == TranscodeTaskStatus.QUEUED

    def _note_held_for_staging(self, task: TranscodeTask, stage: TrackStage | None) -> None:
        """Count a task held for its stage; a task with no stage row at all is logged once."""
        self.held_staging += 1
        if stage is None and task.id not in self._dispatcher._unstaged_logged:
            self._dispatcher._unstaged_logged.add(task.id)
            logger.debug("task_id=%s has no stage row (predates staging); held", task.id)

    async def _claim_and_spawn(self, task: TranscodeTask, task_id: str, preset: TranscodePreset | None) -> None:
        # No separate re-verify needed here: the fresh,
        # `populate_existing`-forced, FOR UPDATE-locked load at the
        # top of this iteration (`_reload_locked`) already confirmed `task` is
        # current and still QUEUED, right before we act on it.
        assignment = await self._dispatcher._claim_gpu_for_task(self._db, task, preset)
        if assignment.action == "queue":
            await self._log_waiting(task, assignment)
            return
        self._dispatcher.gpu_waits.resumed(task_id)
        if assignment.action == "fail":
            await self._fail_isolated(task, task_id, str(assignment.reason))
            return
        await self._spawn_claimed_task(task, task_id, assignment)

    async def _log_waiting(self, task: TranscodeTask, assignment: GpuAssignment) -> None:
        """Log the task's GPU wait the first time it queues for one (see `GpuWaitLog`)."""
        encoder = assignment.encoder.id if assignment.encoder is not None else None
        await log_safely(
            "transcode.waiting", self._dispatcher.gpu_waits.waiting(self._db, task, encoder, assignment.reason)
        )

    async def _fail_isolated(self, task: TranscodeTask, task_id: str, reason: str) -> None:
        # Same isolation as `_run_passthrough_isolated`: a raise while
        # failing this task (hub.emit, aggregate, commit) rolls
        # back and moves on, never aborting the tick; `task_id`
        # (loop variable) is logged, never an ORM attribute.
        try:
            await self._dispatcher._fail_queued_task(self._db, task, reason)
        except Exception as exc:
            logger.exception("failing unrunnable transcode task failed task_id=%s: %s", task_id, exc)
            await self._db.rollback()

    async def _spawn_claimed_task(self, task: TranscodeTask, task_id: str, assignment: GpuAssignment) -> None:
        # Read before the try: after a failed flush/commit no ORM
        # attribute is readable until the rollback (see `_revert_failed_claim`).
        claimed_gpu_id = assignment.gpu.id if assignment.gpu is not None else None
        started = False
        try:
            # `_spawn_container` is a blocking call: a plain docker
            # socket round-trip normally, but on the SSH-transport-
            # rebuild path (see arm_backend.docker_client) it also does a
            # blocking TCP+SSH handshake that can take tens of
            # seconds against a black-holed remote host. Run it off
            # the event loop so a stuck spawn doesn't freeze
            # HTTP/WS/ripper callbacks for the whole tick.
            # `_spawn_container` touches only the docker client,
            # `self._settings`, and its own
            # locals/args (never the AsyncSession), so moving it to a
            # thread doesn't put any DB access off the loop.
            await asyncio.to_thread(self._dispatcher._spawn_container, task, assignment=assignment)
            started = True
            self.spawned += 1
            self._dispatcher.gpu_waits.spawned(task_id)
            self._dispatcher.last_spawn_error = None
            # Commit this task's GPU claim promptly, per-task, right
            # after its container is confirmed running: a later
            # task's exception (and rollback, see
            # `_run_passthrough_isolated`) must never be able to revert a GPU claim
            # whose container already exists.
            await self._db.commit()
        except Exception as exc:
            self._dispatcher.last_spawn_error = f"{type(exc).__name__}: {exc}"[:300]
            # `task_id` (loop variable), never `task.id`: see
            # `_run_passthrough_isolated` for why no ORM
            # attribute may be read before the rollback in `_revert_failed_claim`.
            logger.exception("transcode spawn failed task_id=%s: %s", task_id, exc)
            await self._revert_failed_claim(task_id, assignment, started)
        finally:
            # Committed (other sessions now read BUSY) or rolled back
            # and released: either way the in-process marker is done.
            if claimed_gpu_id is not None:
                self._dispatcher.claimed_gpu_ids.discard(claimed_gpu_id)

    async def _revert_failed_claim(self, task_id: str, assignment: GpuAssignment, started: bool) -> None:
        # The raise that brought us here can come from `_spawn_container`
        # itself (the container never started) OR from the commit at the
        # end of `_spawn_claimed_task`'s try (the container IS running but
        # the GPU-claim commit failed) -- either way, mirroring
        # `_run_passthrough_isolated`, roll back first: a raise from inside a
        # flush/commit leaves the session in "pending rollback"
        # state, and the NEXT statement issued for the NEXT
        # queued task would raise PendingRollbackError outside
        # any try/except and abort the whole tick.
        await self._db.rollback()
        # Release the GPU claim so the task can retry claiming a
        # GPU on a later tick. A real SQLAlchemy session's
        # rollback (expire_on_rollback=True by default) already
        # discards whatever uncommitted BUSY assignment
        # `_claim_gpu_for_task` made and expires the gpu object
        # back to its last-committed value, but relying on that
        # implicit expire-on-rollback behavior for correctness is
        # fragile (and the in-memory test fake doesn't model it
        # at all), so the revert is re-applied explicitly here,
        # AFTER the rollback -- applying it before would just
        # have the rollback above discard it again. It's
        # committed immediately rather than deferred to the
        # trailing end-of-loop commit: an uncommitted revert
        # sitting in the shared session for the rest of the loop
        # would be discarded again by a LATER task's own rollback
        # (the same hazard `_run_passthrough_isolated`'s per-task
        # commits guard against).
        if assignment.gpu is not None:
            assignment.gpu.status = GpuStatus.AVAILABLE
            assignment.gpu.claimed_by_task_id = None
            await self._db.commit()
        # Only a container that never started counts as an
        # attempt: when just the commit failed, the transcoder
        # is running and will claim the task.
        if not started:
            try:
                await self._dispatcher._count_failed_spawn(self._db, task_id)
            except Exception:
                logger.exception("could not count the failed spawn task_id=%s", task_id)
                await self._db.rollback()


class TranscodeDispatcher:
    def __init__(
        self,
        settings: Settings,
        db_factory: async_sessionmaker[AsyncSession],
        docker_client: Any,
        hub: WSHub,
        docker_client_factory: Callable[[], Any] | None = None,
        *,
        schema_store: SchemaStore | None = None,
    ) -> None:
        self._settings = settings
        self._db_factory = db_factory
        # The loaded HandBrake schema the claim checks a preset's settings
        # against; with none (or none loaded) settings are not checked.
        self._schema_store = schema_store
        # Every docker call goes through this wrapper, which reopens a dead
        # docker-over-SSH transport (see arm_backend.docker_client) and then
        # drops every cached probe answer made against the dead client.
        self._docker_client: HealingDockerClient | None = (
            HealingDockerClient(docker_client, docker_client_factory, on_rebuild=self._invalidate_docker_probes)
            if docker_client is not None
            else None
        )
        self.images = TranscodeImagePool(settings, self._docker_client)
        self._hub = hub
        self.sweeps = TranscodeSweeps(settings, hub, db_factory)
        self._stop = asyncio.Event()
        self._tick_interval = settings.ARM_TRANSCODE_DISPATCH_INTERVAL_SECONDS
        # Surfaced by /api/system/diagnostics so a crash-looping or
        # un-pullable transcoder is visible in the UI, not only in the log.
        self.last_spawn_error: str | None = None
        # task id -> (container name, monotonic spawn time) for containers
        # spawned for a task that is still queued, i.e. has not checked in.
        self._awaiting_checkin: dict[str, tuple[str, float]] = {}
        # (detail, monotonic time) of the last "spawns held" log line.
        self._probe_hold_logged: tuple[str | None, float] | None = None
        # Task ids already logged as held for having no stage row at all.
        self._unstaged_logged: set[str] = set()
        self._probe = TtlProbe(lambda: probe_docker(self._docker_client, self._settings.ARM_TRANSCODE_IMAGE))
        # Local transcoders mount ARM_HOST_CERTS_PATH/arm-ca.crt; it must be
        # the CA this backend serves under (see `probe_transcode_ca`).
        self._ca_probe = TtlProbe(lambda: probe_transcode_ca(self._docker_client, self._settings))
        # Set by `probe`: rippers and local transcoders use different certs dirs.
        self.certs_dir_warning: str | None = None
        # The URL a remote-spawned transcoder calls home on; only checked
        # when spawning remotely (see `probe`).
        self._backend_url_probe = TtlProbe(lambda: probe_backend_url(self._settings.ARM_TRANSCODE_BACKEND_URL))
        # The URL check's failure while ARM_TRANSCODE_BACKEND_URL_CHECK=warn
        # lets spawns through; diagnostics still reports it. Set by `probe`.
        self.backend_url_warning: str | None = None
        # GPU rows currently running a device probe; the claim never hands
        # one of these to a task.
        self.probing_gpu_ids: set[str] = set()
        # GPU rows a probe pass has reserved but not yet finished (queued
        # behind other rows of the boot pass), and whether the boot pass is
        # still listing its rows. Together with `probing_gpu_ids` they say
        # whether an unprobed row is about to be verified (`awaiting_probe`),
        # so work waits for it instead of falling back to the CPU or failing.
        self.pending_probe_gpu_ids: set[str] = set()
        self.boot_probe_listing = False
        # GPU rows this process has claimed (BUSY in the claim's session) but
        # not yet committed or rolled back. Other sessions still read those
        # rows as AVAILABLE until the per-task commit, which only happens
        # after the container spawn (an image pull or ssh rebuild can take
        # minutes), so the probe runner and the re-probe endpoints treat an
        # id in this set exactly like a BUSY row. Kept in-process: the claim
        # and the probes share one event loop.
        self.claimed_gpu_ids: set[str] = set()
        # Vendors seen holding an enabled GPU row. Refreshed once per tick
        # (see `_refresh_enabled_gpu_vendors`, called from `_tick`) so it
        # reflects the current inventory even with an idle queue or a
        # freshly-started process, and again whenever `_claim_gpu_for_task`
        # loads the gpus table for a GPU-eligible encoder. `probe()` is
        # synchronous (no DB access), so it reads this cache rather than
        # querying live; it is only ever stale for the window between a GPU
        # being enabled and the next tick or claim.
        self._enabled_gpu_vendors: set[GpuVendor] = set()
        # Tasks logged as waiting for a GPU: each wait logs once on entry and
        # once when the task spawns, fails or leaves the queue.
        self.gpu_waits = GpuWaitLog()

    @property
    def docker_client(self) -> HealingDockerClient | None:
        """The docker client every transcode-host caller shares (None for a
        ripper-only deployment). Calls through it reopen a dead ssh
        transport, so holding it across a rebuild is safe."""
        return self._docker_client

    @property
    def _docker(self) -> Any:
        """The docker-py client the shared wrapper currently forwards to."""
        return self._docker_client.current if self._docker_client is not None else None

    def _invalidate_docker_probes(self) -> None:
        """Forget every cached probe answer: they were made against the client
        a rebuild just replaced."""
        self._probe.invalidate()
        self.images.invalidate()

    def stop(self) -> None:
        self._stop.set()

    async def startup_checks(self) -> None:
        """Log, once at startup, what `probe` finds wrong with the transcode
        host (a CA mismatch above all), so it is not first met as failed
        spawns. Never raises."""
        if self._docker_client is None:
            return
        try:
            ok, detail = await asyncio.to_thread(self.probe)
        except Exception:
            logger.exception("transcode startup check failed")
            return
        if not ok:
            logger.error("transcode startup check failed; encode spawns held: %s", detail)
        if self.certs_dir_warning:
            logger.warning("transcode startup check: %s", self.certs_dir_warning)

    async def run(self) -> None:
        await self.startup_checks()
        logger.info(
            "transcode dispatcher starting: max_parallel=db-config (env seed %d) image=%s tick=%ds",
            self._settings.MAX_PARALLEL_TRANSCODES,
            self._settings.ARM_TRANSCODE_IMAGE,
            self._tick_interval,
        )
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as exc:  # never crash the loop
                logger.exception("transcode dispatcher tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick_interval)
            except asyncio.TimeoutError:
                pass
        logger.info("transcode dispatcher stopped")

    async def _tick(self) -> None:
        async with self._db_factory() as db:
            await self._refresh_enabled_gpu_vendors(db)
            await self.sweeps.sweep_stale_claims(db)
            await self.sweeps.sweep_orphaned_applications(db)
            await db.commit()
            await self.spawn_pending(db)

    async def _refresh_enabled_gpu_vendors(self, db: AsyncSession) -> None:
        """Refresh `self._enabled_gpu_vendors` once per tick, independent of
        queue state (the gpus table is tiny -- 1-4 rows on real hosts -- so
        one extra unconditional select is trivial). Without this, a fresh
        process or an idle queue never populates the set at all (only a
        GPU-eligible claim in `_claim_gpu_for_task` did), which meant
        `probe()`'s missing-variant note could never appear until a job
        actually queued -- defeating its purpose of catching a forgotten
        variant build before jobs fail over to base. Read-only and
        best-effort: it never raises past this method's own select (a DB
        error here surfaces the same as any other tick-body exception, via
        `run()`'s per-tick catch-all) and never affects `ok`."""
        all_gpus = (await db.execute(select(Gpu))).scalars().all()
        self._enabled_gpu_vendors = _enabled_vendors(all_gpus)

    # --- spawn loop ---------------------------------------------------------

    async def spawn_pending(self, db: AsyncSession) -> int:
        """Execute queued passthrough tasks in-process and spawn transcoder
        containers for encode tasks up to `config.max_parallel_transcodes`.

        Passthrough (no preset, or TranscodeTool.NONE) never spawns a
        container and is not counted against encode slots; it always runs
        when queued, FIFO. Encode tasks are additionally gated by
        `config.transcode_enabled` (held in QUEUED when off) and by having a
        docker client + host paths at all (a ripper-only deployment has
        neither); held tasks stay queued for a later tick, never dropped.

        The queued scan is unbounded (no LIMIT) so a run of held encode
        tasks at the head of the FIFO queue can never crowd passthrough
        tasks further back out of this tick entirely; `_QUEUE_SCAN_LIMIT`
        instead caps how many ENCODE tasks are examined per tick (a
        passthrough task never counts against that cap either). Each
        passthrough task commits its own claim + terminal state internally
        (see `execute_passthrough_task`), so the `FOR UPDATE SKIP LOCKED`
        row locks from the initial select are released well before any
        (possibly slow, cross-mount) file move runs.

        Only task ids are kept from that initial batch select. Every task's
        SQLAlchemy identity-map object is expired by ANY commit or rollback
        that happens earlier in this same loop (the session's
        `expire_on_commit=False` only suppresses expiry after OUR OWN
        commits above the ORM layer; `Session.rollback()` always expires
        the whole identity map, and a plain `db.commit()` for a DIFFERENT
        row still ends the transaction those FOR UPDATE locks were taken
        under). A plain attribute read on an expired object triggers an
        async lazy load outside any `await` we control, raising
        `sqlalchemy.exc.MissingGreenlet` -- unprotected, aborting the whole
        tick (FakeSession's no-op rollback hides this entirely; it only
        reproduces against a real session). Worse, even a NOT-expired but
        stale object (this session's identity map hasn't been told about a
        concurrent writer's committed change) would silently reuse
        out-of-date state without `populate_existing`. So every iteration
        re-loads its own row fresh, locked, and forced to repopulate from
        the current row before touching a single attribute of it.
        """
        return await _SpawnPass(self, db).run()

    def _log_probe_hold(self, host_probe: tuple[bool, str | None]) -> None:
        ok, detail = host_probe
        if ok:
            if self._probe_hold_logged is not None:
                logger.info("transcode docker host and image ok again; encode spawns resume")
                self._probe_hold_logged = None
            return
        now = time.monotonic()
        last = self._probe_hold_logged
        if last is None or last[0] != detail or now - last[1] >= _PROBE_HOLD_LOG_SECONDS:
            logger.warning("transcode spawns held: %s", detail)
            self._probe_hold_logged = (detail, now)

    async def _count_failed_spawn(
        self, db: AsyncSession, task_id: str, reason: str | None = None, *, spawned: bool = False
    ) -> None:
        """A spawn that failed although the host probe passed is likely
        task-specific (a bad mount, a preset the image rejects, a transcoder
        that never checked in): count it toward ARM_TRANSCODE_MAX_ATTEMPTS so
        it ends instead of looping. `reason` defaults to the last spawn error;
        `spawned` marks a container that did start (wording only)."""
        task = (
            await db.execute(
                select(TranscodeTask).where(col(TranscodeTask.id) == task_id).execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if task is None or task.status != TranscodeTaskStatus.QUEUED:
            return
        detail = reason or self.last_spawn_error
        task.attempts = (task.attempts or 0) + 1
        task.last_error = detail
        if task.attempts >= self._settings.ARM_TRANSCODE_MAX_ATTEMPTS:
            final = (
                f"{detail} (attempts={task.attempts})"
                if spawned
                else f"transcode container could not start (attempts={task.attempts}): {detail}"
            )
            await self._fail_queued_task(db, task, final, spawned=spawned)
            return
        await db.commit()

    def awaiting_probe(self, gpu: Gpu) -> bool:
        """A never-probed row whose probe is reserved, running, or about to be
        listed by the boot pass."""
        return gpu.probed_at is None and (
            self.boot_probe_listing or gpu.id in self.pending_probe_gpu_ids or gpu.id in self.probing_gpu_ids
        )

    async def _claim_gpu_for_task(
        self, db: AsyncSession, task: TranscodeTask, preset: TranscodePreset | None
    ) -> GpuAssignment:
        """Encoder-first claim: map the preset's catalog encoder onto the
        devices whose probe verified its codec.

        - no preset, or the `preset` encoder -> spawn, no GPU, no encoder.
        - a `cpu_<codec>` encoder -> spawn on CPU with that encoder.
        - eligible device free -> claim the best-ranked one (vendor rank,
          then device path) and spawn with the resolved GPU encoder.
        - eligible devices all busy, or the only eligible ones are being
          probed right now -> queue (retry next tick).
        - no eligible device, but a never-probed device that could serve the
          encoder is awaiting its probe (`awaiting_probe`) -> queue.
        - otherwise no eligible device: `any_<codec>` falls back to
          `cpu_<codec>`; a vendor-pinned encoder fails the task.
        - an encoder id missing from the catalog fails the task.
        - with a schema loaded and a preset carrying HandBrake settings, the
          families those settings make invalid are skipped under `any_<codec>`
          (other devices, then CPU; the task fails only when none is valid)
          and fail a single-family encoder; an unknown base preset fails the
          task. A preset carrying HandBrake settings never claims a VAAPI
          device (ffmpeg engine), schema or not.

        Eligibility (enabled, probed, codec verified) is `gpu_is_eligible`;
        a device in `probing_gpu_ids` is never claimed.
        """
        decided = assignment_before_device_lookup(preset)
        if isinstance(decided, GpuAssignment) and (preset is None or decided.action == "fail"):
            return decided
        assert preset is not None  # a no-preset claim is always decided above
        invalid = invalid_families_or_failure(self._current_schema(), preset)
        if isinstance(invalid, GpuAssignment):
            return invalid
        blocked = assignment_when_only_family_invalid(decided, invalid)
        if blocked is not None:
            return blocked
        if isinstance(decided, GpuAssignment):
            return decided
        assignment = await self._claim_device(db, task, preset, decided, invalid)
        self._log_skipped_families(task, invalid, assignment)
        return assignment

    def _current_schema(self) -> HandbrakeSchema | None:
        return self._schema_store.current() if self._schema_store is not None else None

    async def _claim_device(
        self,
        db: AsyncSession,
        task: TranscodeTask,
        preset: TranscodePreset,
        spec: EncoderSpec,
        invalid: dict[str, list[SettingIssue]],
    ) -> GpuAssignment:
        """Claim the best free device that can run `spec` for this preset,
        or decide what to do when none can (`assignment_with_no_candidate`)."""
        codec = str(spec.codec)
        # Filter in Python: `text[]` ANY predicates are awkward to express in
        # SQLAlchemy ORM and the in-memory test fake doesn't grok them. The
        # gpus table is small (1-4 rows on real hosts) so the cost is trivial.
        all_gpus = (await db.execute(select(Gpu))).scalars().all()
        self._enabled_gpu_vendors = _enabled_vendors(all_gpus)
        # An `any_*` WebM preset must not land on a VAAPI device, whose
        # ffmpeg engine cannot write WebM (a pinned vaapi_* + WebM preset is
        # refused at create time).
        all_gpus = [g for g in all_gpus if vendor_supports_container(g.vendor, preset.container)]
        all_gpus = self._exclude_for_settings(all_gpus, preset, codec, invalid)
        eligible = [
            g for g in all_gpus if gpu_is_eligible(g, codec) and (spec.kind == "any" or g.vendor == spec.vendor)
        ]
        candidates = [g for g in eligible if g.id not in self.probing_gpu_ids]
        if not candidates:
            return assignment_with_no_candidate(spec, codec, eligible, all_gpus, self.awaiting_probe, invalid)
        gpu = pick_free_gpu(candidates)
        if gpu is None:
            return GpuAssignment(gpu=None, encoder=spec, action="queue")
        gpu.status = GpuStatus.BUSY
        gpu.claimed_by_task_id = task.id
        self.claimed_gpu_ids.add(gpu.id)
        resolved = spec if spec.kind == "gpu" else gpu_encoder_for(gpu.vendor, codec)
        return GpuAssignment(gpu=gpu, encoder=resolved, action="spawn")

    def _exclude_for_settings(
        self, gpus: list[Gpu], preset: TranscodePreset, codec: str, invalid: dict[str, list[SettingIssue]]
    ) -> list[Gpu]:
        """Drop the devices the preset's HandBrake settings rule out: the
        ffmpeg VAAPI engine whenever it has settings, schema or not, and
        the families the claim-time check found invalid (`invalid` is
        empty without a loaded schema)."""
        return exclude_invalid_families(exclude_ffmpeg_engine(gpus, preset), codec, invalid)

    def _log_skipped_families(
        self, task: TranscodeTask, invalid: dict[str, list[SettingIssue]], assignment: GpuAssignment
    ) -> None:
        """Log each family the preset's settings ruled out, once for the
        claim that spawns the task (a queued claim repeats every tick; a
        failed one carries every family in its reason)."""
        if assignment.action != "spawn":
            return
        for family, issues in invalid.items():
            logger.info("skipping %s for task %s: %s", family, task.id, issue_messages(issues))

    async def _fail_queued_task(
        self, db: AsyncSession, task: TranscodeTask, reason: str, *, spawned: bool = False
    ) -> None:
        """Terminal-fail a queued task that can never run as configured, emit
        `task.failed`, settle its session application, commit, then log
        `transcode.failed` and any `session.completed` to the job log."""
        from arm_backend.transcode_apply import emit_task_failed, log_session_settled, settle_session_application

        task.status = TranscodeTaskStatus.FAILED
        task.last_error = reason
        logger.debug("transcode task failed %s spawn task_id=%s: %s", "after" if spawned else "before", task.id, reason)
        await emit_task_failed(self._hub, db, task)
        application = (
            await db.execute(
                select(SessionApplication).where(col(SessionApplication.id) == task.session_application_id)
            )
        ).scalar_one()
        outcome = await settle_session_application(db, self._hub, application)
        await db.commit()
        await log_safely("transcode.failed", announce_failed(db, task, reason))
        await log_session_settled(db, application, outcome)

    def host_paths_set(self) -> bool:
        return bool(
            (self._settings.ARM_HOST_RAW_PATH or self._settings.ARM_HOST_STAGING_PATH)
            and self._settings.ARM_HOST_MEDIA_PATH
            and self._settings.ARM_HOST_LOGS_PATH
            and self._settings.ARM_HOST_CERTS_PATH
        )

    def probe(self) -> tuple[bool, str | None]:
        """Can this dispatcher actually run a transcode right now? Pings the
        docker host and checks the BASE image exists there; when spawning on
        a remote host (`ARM_TRANSCODE_DOCKER_HOST` + `ARM_TRANSCODE_BACKEND_URL`),
        also that the backend URL the transcoder dials home on answers over
        TLS with the ARM CA (`probe_backend_url`). Never raises;
        cached for docker_probe.PROBE_TTL_SECONDS (see there for why). A
        ripper-only deployment (no docker client at all) can't run encode
        tasks; that's not a probe failure to retry, just a fixed fact, so
        short-circuit before touching `self._probe`.

        The base image is the gate for `ok`; a missing per-vendor variant
        never fails the probe, since `image_for` falls back to the base
        image automatically. When `ok` and a vendor with an enabled GPU row
        (per `self._enabled_gpu_vendors`, see its docstring for how that's
        kept current) lacks its derived variant image, that's noted in the
        detail so an operator who built the split images can see a stale
        vendor build without it ever showing up as a failure.
        """
        if self._docker is None:
            return (False, NO_DOCKER_CLIENT_DETAIL)
        ok, detail = self._probe()
        if not ok:
            return ok, detail
        self.certs_dir_warning = certs_dir_difference(self._settings)
        ca_ok, ca_detail = self._ca_probe()
        if not ca_ok:
            return ca_ok, ca_detail
        if self._settings.ARM_TRANSCODE_DOCKER_HOST and self._settings.ARM_TRANSCODE_BACKEND_URL:
            # A remote transcoder that cannot reach this URL (moved address,
            # a certificate without that SAN) spawns fine and then never
            # claims; catch it here instead.
            url_ok, url_detail = self._backend_url_probe()
            warn_only = self._settings.ARM_TRANSCODE_BACKEND_URL_CHECK == "warn"
            # With warn, the operator said this backend cannot judge the URL
            # (no hairpin, split DNS): report the failure, spawn anyway.
            self.backend_url_warning = url_detail if not url_ok and warn_only else None
            if not url_ok and not warn_only:
                return url_ok, url_detail
        notes = self.images.missing_variant_notes(self._enabled_gpu_vendors)
        return ok, "; ".join(notes) if notes else detail

    def _probe_pulling_base_image(self) -> tuple[bool, str | None]:
        """`probe()`, but when it fails because the base image is missing, try
        to pull it first, as docker's own `containers.run` would have before
        the probe gated spawning. Blocking."""
        result = self.probe()
        image = self._settings.ARM_TRANSCODE_IMAGE
        if result[0] or self._docker is None or self.images.image_exists(image):
            return result
        if not self.images.pull_image(image, kind="base", fallback="encode tasks stay held"):
            return result
        self._probe.invalidate()
        return self.probe()

    def _spawn_container(self, task: TranscodeTask, *, assignment: GpuAssignment) -> Any:
        backend_url = backend_url_for_spawn(self._settings)
        gpu = assignment.gpu
        gpu_vendor = gpu.vendor if gpu is not None else None
        env = {
            **task_env(self._settings, task, backend_url),
            **container_identity_env(self._settings, gpu_vendor),
            **gpu_env(gpu, assignment.encoder),
        }
        volumes = task_volumes(self._settings)
        extra_run_kwargs = gpu_run_kwargs(gpu) if gpu is not None else {}
        # Container hostname is the last 12 chars of the ULID — short enough
        # for `docker ps` and unique enough that two simultaneous transcoders
        # never collide.
        hostname = f"arm-transcode-{task.id[-12:]}"
        image = image_for(self._settings, gpu_vendor, exists=self.images.variant_available)
        run_kwargs: dict[str, Any] = dict(
            image=image,
            name=hostname,
            hostname=hostname,
            labels={_DOCKER_LABEL_KEY: task.id},
            environment=env,
            volumes=volumes,
            network=spawn_network(self._settings),
            detach=True,
            auto_remove=True,
            log_config=log_config(),
            **extra_run_kwargs,
        )
        assert self._docker_client is not None
        container = self._run_container(run_kwargs, task.id)
        self._awaiting_checkin[task.id] = (hostname, time.monotonic())
        logger.debug(
            "transcode spawned task_id=%s container=%s image=%s gpu=%s",
            task.id,
            hostname,
            image,
            assignment.gpu.device_path if assignment and assignment.gpu else "cpu",
        )
        return container

    def _run_container(self, run_kwargs: dict[str, Any], task_id: str) -> Any:
        """`containers.run`, never leaving a container of ours behind.

        A dead ssh transport is rebuilt and the run retried once by the
        client. A name conflict with a container labelled for THIS task (left
        by a crashed backend) is removed and the run repeated once; a failure
        after docker created the container (a start error) removes it, so a
        retry never meets its own leftover."""
        assert self._docker_client is not None
        name = run_kwargs["name"]
        try:
            return self._docker_client.containers.run(**run_kwargs)
        except Exception as exc:
            conflict = isinstance(exc, docker.errors.APIError) and _is_name_conflict(exc)
            removed = self._discard_container(name, task_id, only_ours=True) is not None
            if not (conflict and removed):
                raise
        logger.warning("removed leftover container %s of task_id=%s; recreating", name, task_id)
        return self._docker_client.containers.run(**run_kwargs)

    def _discard_container(self, name: str, task_id: str, *, only_ours: bool = False) -> str | None:
        """Stop and remove the container `name`, returning the last error
        lines of its logs ("" if none). None means nothing was removed: it
        does not exist, or (`only_ours`) it is labelled for another task.
        Best-effort: never raises."""
        assert self._docker_client is not None
        try:
            container = self._docker_client.containers.get(name)
            if only_ours and (container.labels or {}).get(_DOCKER_LABEL_KEY) != task_id:
                return None
            tail = _error_tail(container.logs(tail=_LOG_TAIL_LINES))
        except docker.errors.NotFound:
            return None
        except Exception as exc:  # noqa: BLE001 - best-effort cleanup
            logger.warning("could not inspect container %s: %s", name, exc)
            return None
        try:
            container.stop(timeout=2)
        except Exception as exc:  # noqa: BLE001 - it may already have exited
            logger.debug("stop of container %s: %s", name, exc)
        try:
            container.remove(force=True)
        except docker.errors.NotFound:
            pass  # auto_remove beat us to it
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not remove container %s: %s", name, exc)
        return tail

    # --- cancel running -----------------------------------------------------

    async def cancel_running(self, task_id: str) -> None:
        """Send `task.cancel` over WS (and stop an in-process passthrough
        copy directly), wait `_CANCEL_GRACE_SECONDS`, then docker-stop any
        survivor and delete the row.

        Cancel = delete: the row vanishes from the DB and `task.deleted`
        fires over WS. If the transcoder honoured the cancel cleanly by
        calling `/fail` during the grace window the row was already
        marked FAILED — we delete it anyway, since the user's intent was
        to remove it entirely.
        """
        # An in-process passthrough has no container and no WS listener;
        # stop its copy directly (it then fails itself as "cancelled").
        from arm_backend.passthrough_executor import request_cancel

        request_cancel(task_id)
        async with self._db_factory() as db:
            await self._hub.emit(
                topic=f"transcoder.commands.{task_id}",
                event_type="task.cancel",
                payload={"task_id": task_id},
                job_id=None,
                session=db,
            )
            await db.commit()

        await asyncio.sleep(_CANCEL_GRACE_SECONDS)

        # Fetch once to decide whether docker-stop is still needed and to
        # capture the metadata we need for the task.deleted emit.
        async with self._db_factory() as db:
            row = (await db.execute(select(TranscodeTask).where(col(TranscodeTask.id) == task_id))).scalar_one_or_none()
            if row is None:
                return  # already gone (race with another delete or rollback)
            still_running = row.status == TranscodeTaskStatus.IN_PROGRESS
            application_id = row.session_application_id
            track_id = row.source_track_id

        # Force-stop the container if the transcoder didn't honour the WS
        # cancel inside the grace window. No docker client (ripper-only
        # deployment) means there's no container to stop; the row delete
        # below still runs.
        if still_running and self._docker_client is not None:
            try:
                survivors = self._docker_client.containers.list(filters={"label": f"{_DOCKER_LABEL_KEY}={task_id}"})
                for container in survivors:
                    logger.warning(
                        "force-stopping unresponsive transcoder task_id=%s container=%s",
                        task_id,
                        container.id,
                    )
                    container.stop(timeout=5)
            except Exception as exc:
                logger.exception("docker-stop fallback failed for task_id=%s: %s", task_id, exc)

        # Delete the row + emit task.deleted. Re-select fresh in case the
        # transcoder /fail call mutated the row between our fetch and now.
        async with self._db_factory() as db:
            row = (await db.execute(select(TranscodeTask).where(col(TranscodeTask.id) == task_id))).scalar_one_or_none()
            # Race guard: row deleted between the post-grace fetch and here.
            if row is None:  # pragma: no cover
                return
            application = (
                await db.execute(select(SessionApplication).where(col(SessionApplication.id) == application_id))
            ).scalar_one_or_none()
            job_id = application.job_id if application is not None else None
            # A docker-stopped transcoder never calls /fail, and the FK only
            # nulls the claim; release here or the GPU stays BUSY for good.
            await release_gpu_for_task(db, task_id)
            await db.delete(row)
            await self._hub.emit(
                topic="transcode.events",
                event_type="task.deleted",
                payload={"task_id": task_id, "session_application_id": application_id},
                job_id=job_id,
                track_id=track_id,
                session=db,
            )
            await db.commit()
