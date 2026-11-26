"""The per-drive poll loop: follow the drive's node across replugs, read its state, report transitions and start the
pipeline when a disc goes in."""

import asyncio
import logging
from pathlib import Path

import httpx

from arm_ripper.backend_client import BackendClient
from arm_ripper.config import settings
from arm_ripper.drive_handle import DriveHandle
from arm_ripper.drive_poll import DriveErrorKind, DriveState, InsertDetector, classify_drive_error, read_drive_status
from arm_ripper.drive_resolve import ResolvedDevice, node_port, resolve_drive_device
from arm_ripper.heartbeat import HEARTBEAT_INTERVAL_SECONDS
from arm_ripper.job_controller import JobController
from arm_ripper.recovery import boot_probe

logger = logging.getLogger("arm_ripper")


def resolve_paths() -> dict[str, Path]:
    """The filesystem roots drive resolution reads: the host disk root from settings, /dev and /sys."""
    return {
        "disk_root": Path(settings.ARM_HOST_DISK_ROOT),
        "dev_root": Path("/dev"),
        "sysfs_root": Path("/sys"),
    }


# While the drive is absent the backend is the only source of a fresher
# node for a port-identity drive, but the scanner only republishes on its
# own cadence — polling it every POLL_INTERVAL adds nothing. Refresh on the
# first absent tick, then once per this many ticks. Counted in ticks, not
# wall-clock, so the tests' patched sleep still drives it.
def _hint_refresh_every_n_ticks() -> int:
    return max(1, int(HEARTBEAT_INTERVAL_SECONDS / settings.POLL_INTERVAL_SECONDS))


async def _current_hint(
    client: BackendClient,
    drive_id: str,
    *,
    absent: bool,
    absent_ticks: int,
    last_resolved: str | None,
    last_port: str | None = None,
) -> str:
    """The node to try when there is no by-id link. Normally the last node that
    resolved (ARM_DRIVE_DEV until one has); while such a drive is absent, ask
    the backend — its scanner tracks the port -> node mapping and may have seen
    the drive come back renumbered.

    `last_resolved` keeps a backend-supplied node once it has resolved: going
    back to ARM_DRIVE_DEV on the next tick would lose a renumbered drive again
    and flap absent/present every other poll. Once the drive is absent,
    ARM_DRIVE_DEV is tried again on alternate ticks, but only when its node
    is on `last_port`, the port this drive was last seen on.

    `absent` is the PREVIOUS tick's state, not `handle.absent`: a node that
    resolves but answers ENXIO is absence too, and it leaves the
    handle populated, so keying off the handle would never refresh there.

    Only called from `poll_loop`, i.e. optical mode — `main.amain` has already
    required ARM_DRIVE_DEV to be set there, so the `or ""` fallbacks below
    are unreachable in practice; they exist to give mypy a plain `str`.
    """
    fallback = last_resolved or settings.ARM_DRIVE_DEV or ""
    if settings.ARM_DRIVE_BY_ID or not absent:
        return fallback
    if (
        last_resolved
        and settings.ARM_DRIVE_DEV
        and absent_ticks % 2
        and last_port is not None
        and node_port(settings.ARM_DRIVE_DEV, sysfs_root=resolve_paths()["sysfs_root"]) == last_port
    ):
        # While absent, every other tick also tries the configured node: a
        # drive replugged back onto it is found even when the backend cannot
        # be asked. Only when that node sits on this drive's port: on a
        # multi-drive host it may now be another drive's. Trying it while
        # present is what made the hint flap.
        fallback = settings.ARM_DRIVE_DEV
    if absent_ticks % _hint_refresh_every_n_ticks() != 0:
        return fallback
    try:
        drive = await client.get_drive(drive_id)
    except (httpx.HTTPError, OSError) as exc:
        logger.debug("hint refresh failed: %s", exc)
        return fallback
    return drive.device_path if drive is not None and drive.device_path else fallback


async def _on_reattached(client: BackendClient, drive_id: str, handle: DriveHandle, controller: JobController) -> None:
    """The drive came back after an ABSENT run. Whatever is seated now may be
    a different disc, and a rip may have been in flight when it left."""
    if not controller.is_idle():
        # A rip pipeline is still running: the drive dropped off the bus
        # mid-rip. boot_probe would resume the same job, wiping the raw dir
        # under it and starting a second rip. The running rip reads the new
        # node from the shared handle and resumes there itself.
        logger.info("reattach: the running rip resumes on %s; skipping boot probe", handle.current)
        return
    logger.info("boot probe after reattach on %s", handle.current)
    try:
        await boot_probe(client, drive_id, handle.current or "", controller)
    except Exception as exc:  # noqa: BLE001 — recovery is best-effort, never blocks polling
        logger.exception("boot probe after reattach failed: %s", exc)


async def _report_node(client: BackendClient, drive_id: str, path: str) -> None:
    try:
        await client.update_device_path(drive_id=drive_id, device_path=path)
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("device-path update failed: %s", exc)


class DrivePoller:
    """Polls one drive: follows its node, reads its state, reports transitions, starts the pipeline on insert."""

    def __init__(self, controller: JobController, handle: DriveHandle, *, client: BackendClient, drive_id: str) -> None:
        self._controller = controller
        self._handle = handle
        self._client = client
        self._drive_id = drive_id
        self._detector = InsertDetector(not_ready_rearm_polls=settings.ARM_NOT_READY_REARM_POLLS)
        self._last_state: DriveState | None = None
        self._active_task: asyncio.Task[None] | None = None
        self._last_error_kind: DriveErrorKind | None = None
        # Ticks that have run with the drive already known absent: 0 on the first
        # such tick, so it refreshes and later ones are throttled.
        self._absent_ticks = 0
        # The last node a hint resolved to (port-identity drives only).
        self._last_resolved: str | None = None
        self._last_port: str | None = None

    async def run(self) -> None:
        """Poll until cancelled."""
        while True:
            resolved = await self._resolve()
            moved = self._handle.set(resolved.path if resolved else None)

            state = self._read_state()

            # Transitions are keyed on state so a node that resolves but answers
            # ENXIO cannot flap between "present" and "absent" every poll. They run
            # BEFORE detector.update so a reset re-arms for this very reading.
            if self._went_absent(state):
                logger.warning("drive absent (by_id=%s) — polling until it returns", settings.ARM_DRIVE_BY_ID)
            elif self._came_back(state):
                # A None resolution empties the handle, which reads as ABSENT, so a present drive has a resolution.
                assert resolved is not None
                await self._reattach(resolved)
            elif moved and not self._handle.absent:
                assert resolved is not None  # same invariant as the reattach arm above
                await self._report_move(resolved)

            if state != self._last_state:
                logger.info("drive state %s -> %s", self._last_state, state)
                self._last_state = state

            self._start_rip_on_insert(state)

            await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)

    def _went_absent(self, state: DriveState) -> bool:
        """True on the first tick the drive reads ABSENT."""
        return state is DriveState.ABSENT and self._last_state is not DriveState.ABSENT

    def _came_back(self, state: DriveState) -> bool:
        """True on the first tick the drive reads present after an ABSENT run."""
        return self._last_state is DriveState.ABSENT and state is not DriveState.ABSENT

    async def _reattach(self, resolved: ResolvedDevice) -> None:
        """The drive is back: log where it was found, re-arm insert detection, report its node, then run the reattach
        recovery."""
        logger.info("drive present at %s via %s (reattached)", resolved.path, resolved.via)
        self._detector.reset()
        # Report the node BEFORE the probe: _on_reattached can run a whole
        # resumed rip, and the UI must not sit on the stale node for its
        # entire duration.
        await _report_node(self._client, self._drive_id, self._handle.current or "")
        await _on_reattached(self._client, self._drive_id, self._handle, self._controller)

    async def _report_move(self, resolved: ResolvedDevice) -> None:
        """The drive turned up on a new node: log it and report it to the backend."""
        logger.info("drive node moved to %s via %s", resolved.path, resolved.via)
        await _report_node(self._client, self._drive_id, self._handle.current or "")

    def _start_rip_on_insert(self, state: DriveState) -> None:
        """Feed this reading to the insert detector and start the pipeline on an insert while no earlier one is still
        running."""
        if self._active_task is not None and self._active_task.done():
            self._active_task = None

        # detector.update() must run every poll to track the NOT_READY
        # streak; only act on the True edge when no rip is already running.
        if self._detector.update(state) and self._active_task is None and self._handle.current is not None:
            self._active_task = asyncio.create_task(self._controller.handle_disc_inserted(self._handle.current))

    async def _resolve(self) -> ResolvedDevice | None:
        """Resolve this tick's node from the current hint, counting the ticks the drive has been absent."""
        # Re-resolve every poll: the node behind this drive can change while we
        # run (replug under a new srN). One readlink; cheap.
        was_absent = self._last_state is DriveState.ABSENT
        hint = await _current_hint(
            self._client,
            self._drive_id,
            absent=was_absent,
            absent_ticks=self._absent_ticks,
            last_resolved=self._last_resolved,
            last_port=self._last_port,
        )
        self._absent_ticks = self._absent_ticks + 1 if was_absent else 0
        resolved = resolve_drive_device(settings.ARM_DRIVE_BY_ID, hint, **resolve_paths())
        if resolved is not None and not settings.ARM_DRIVE_BY_ID:
            self._remember_node(resolved.path)
        return resolved

    def _remember_node(self, path: str) -> None:
        """Remember the node a port-identity drive resolved to, and the port that node is on when it is new."""
        if path != self._last_resolved or self._last_port is None:
            # The port is this drive's identity when it has no by-id link.
            self._last_port = node_port(path, sysfs_root=resolve_paths()["sysfs_root"])
        self._last_resolved = path

    def _read_state(self) -> DriveState:
        """Read the drive's state, treating an empty handle or a node the hardware refuses as ABSENT and
        other errors as NO_INFO."""
        if self._handle.absent:
            state = DriveState.ABSENT
            self._last_error_kind = None
        else:
            try:
                state = read_drive_status(self._handle.current or "")
                self._last_error_kind = None
            except OSError as exc:
                state = self._state_from_error(exc)
        return state

    def _state_from_error(self, exc: OSError) -> DriveState:
        """The state an ioctl failure stands for, logging a misconfiguration once per run of them and any other error
        on every poll."""
        kind = classify_drive_error(exc)
        if kind is DriveErrorKind.ABSENT:
            # The node resolved but the hardware said no (ENXIO/ENODEV,
            # or it vanished between resolve and open). Keep the handle —
            # the node is still the right one — and report absence.
            state = DriveState.ABSENT
        elif kind is DriveErrorKind.MISCONFIGURED:
            if self._last_error_kind is not kind:
                logger.warning(
                    "drive %s is present but misconfigured: %s — check the device cgroup rule and CDROM_GID",
                    self._handle.current,
                    exc.strerror or exc,
                )
            state = DriveState.NO_INFO
        else:
            logger.warning("ioctl failed: %s", exc)
            state = DriveState.NO_INFO
        self._last_error_kind = kind
        return state


async def poll_loop(controller: JobController, handle: DriveHandle, *, client: BackendClient, drive_id: str) -> None:
    """Poll one drive until cancelled."""
    await DrivePoller(controller, handle, client=client, drive_id=drive_id).run()
