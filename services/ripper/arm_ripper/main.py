import asyncio
import logging
import ssl
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from arm_common import DriveMediaStatus, JobStatus, configure_service_logging
from arm_ripper.backend_client import BackendClient, JobView, RegisterRefused
from arm_ripper.config import settings
from arm_ripper.drive_handle import DriveHandle
from arm_ripper.drive_poll import DriveErrorKind, DriveState, InsertDetector, classify_drive_error, read_drive_status
from arm_ripper.drive_resolve import resolve_drive_device
from arm_ripper.drive_status import probe_drive_media
from arm_ripper.job_controller import JobController
from arm_ripper.makemkv_key import refresh_makemkv_key
from arm_ripper.recovery import boot_probe
from arm_ripper.scan.makemkv import probe_makemkv_key
from arm_ripper.source import is_iso_source
from arm_ripper.ws_client import WSClient

CA_BUNDLE_PATH = "/etc/ssl/certs/ca-certificates.crt"

RIPPER_VERSION = "0.0.0-skeleton"

# Heartbeat carries the current CDROM_DRIVE_STATUS reading to the
# backend so the manual-trigger endpoint can refuse clicks made
# against an empty / open tray. 30s gives a click-time check that's
# at most ~30s stale; a stale heartbeat (older than the backend's
# freshness window) falls back to "unknown" and the request is
# allowed through to identify (which will fail visibly).
HEARTBEAT_INTERVAL_SECONDS = 30.0

# The backend spawns each ripper container for one Drive row and sets
# HOSTNAME to arm-ripper-<serial> (or the equivalent stable identity); srN
# is not stable across a renumbering replug, so the log file is named from
# the identity the manager assigned rather than the current device node.
configure_service_logging(settings.HOSTNAME, level=settings.ARM_LOG_LEVEL)
logger = logging.getLogger("arm_ripper")


async def register_with_retry(client: BackendClient, device_path: str) -> str:
    """Retry transport/5xx failures with backoff. A refusal (unknown drive,
    not enrolled, identity mismatch) is not retriable: log it and park the
    process so the container stays up for `docker logs` (spec §3)."""
    delay = 1.0
    while True:
        try:
            drive = await client.register(
                drive_id=settings.ARM_DRIVE_ID,
                hostname=settings.HOSTNAME,
                device_path=device_path,
                ripper_version=RIPPER_VERSION,
                by_id_name=settings.ARM_DRIVE_BY_ID,
            )
            logger.info("registered drive_id=%s device=%s", drive.id, device_path)
            return drive.id
        except RegisterRefused as exc:
            logger.error(
                "register refused for drive_id=%s: %s — container left running for diagnosis; "
                "fix the enrollment in the UI and restart this container",
                settings.ARM_DRIVE_ID,
                exc,
            )
            await asyncio.Event().wait()
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("register failed (%s); retrying in %.1fs", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)


# AWAITING_REVIEW is intentionally excluded: recovery for review-gated discs is
# owned by the boot probe + the review-countdown auto-start path. Picking up an
# AWAITING_REVIEW job here would call controller.pickup → _run_rip → rip_start,
# which transitions straight to RIPPING and bypasses the countdown, manual_pause,
# and global ripping_paused. Only re-acquire IDENTIFIED (the resolve-after-timeout
# seated disc — Defect-1's target) and RIPPING (harmless restart race).
_RIP_READY = frozenset({JobStatus.IDENTIFIED, JobStatus.RIPPING})


async def maybe_reacquire_current_job(
    controller: JobController,
    *,
    get_current_job: Callable[[str], Awaitable[JobView | None]],
    drive_id: str,
    device_path: str,
    seated: bool,
) -> None:
    """Idle re-probe: if the ripper is idle with a disc seated, ask the backend
    for the drive's current non-terminal job. If it's rip-ready (operator
    resolved it after our in-memory wait timed out), pick it up. Pull-based, so
    it survives a backend restart and the 30-min ceiling."""
    if not seated or not controller.is_idle():
        return
    try:
        job = await get_current_job(drive_id)
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("current-job reprobe failed: %s", exc)
        return
    if job is None or job.status not in _RIP_READY:
        return
    logger.info("reacquiring current job %s status=%s via heartbeat reprobe", job.id, job.status.value)
    await controller.pickup(job, device_path)


async def heartbeat_loop(client: BackendClient, drive_id: str, handle: DriveHandle, controller: JobController) -> None:
    """Post the current media status to the backend every
    HEARTBEAT_INTERVAL_SECONDS. Errors are logged + swallowed —
    the heartbeat is best-effort and stale rows fall back to
    "unknown" on the manual-trigger pre-check.

    Reads the shared DriveHandle every beat, so a drive that moved to a
    new srN is probed at its new node with no restart. While the drive is
    absent the beat carries DETACHED — and keeps going, so the backend can
    derive OFFLINE while the row stays visible.

    For ISO sources we skip the SCSI ioctl (it fails on regular files)
    and report `loaded` unconditionally — the source is always present
    by construction in manual-trigger mode.

    After each successful heartbeat, maybe_reacquire_current_job checks
    whether the idle ripper should re-acquire a rip-ready job from the
    backend (handles the case where the in-memory wait timed out or the
    backend restarted while a disc was seated).
    """
    while True:
        try:
            device_path = handle.current
            if device_path is None:
                status = DriveMediaStatus.DETACHED
            elif is_iso_source(device_path):
                status = DriveMediaStatus.LOADED
            else:
                status, _ = probe_drive_media(device_path)
            await client.heartbeat(drive_id=drive_id, media_status=status)
            if device_path is not None:
                await maybe_reacquire_current_job(
                    controller,
                    get_current_job=client.get_current_job,
                    drive_id=drive_id,
                    device_path=device_path,
                    seated=(status == DriveMediaStatus.LOADED),
                )
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("heartbeat failed: %s", exc)
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)


def makemkv_key_changed(*, prev: str | None, current: str | None) -> bool:
    """True when the effective makemkv key changed (treats blank as None)."""

    def _norm(v: str | None) -> str | None:
        return (v or "").strip() or None

    return _norm(prev) != _norm(current)


async def makemkv_keycheck_loop(client: BackendClient) -> None:
    """Probe makemkv key-validity on key-change + daily, report to the backend.
    Best-effort: errors are logged + swallowed (mirrors heartbeat_loop)."""
    last_key: str | None = None
    first = True
    while True:
        try:
            cfg = await client.get_ripper_config()
            key = cfg.makemkv_key
            if first or makemkv_key_changed(prev=last_key, current=key):
                # Write settings.conf with the current key BEFORE probing, so the
                # probe checks the key actually on disk. (Single call — do not
                # double-invoke refresh_makemkv_key.)
                await refresh_makemkv_key(key=key)
            state, detail = await probe_makemkv_key(key)
            await client.report_makemkv_key_status(state=state, detail=detail)
            last_key = key
            first = False
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("makemkv keycheck failed: %s", exc)
        except Exception:  # noqa: BLE001 — keycheck is best-effort; never let it kill the loop
            logger.exception("makemkv keycheck: unexpected error")
        await asyncio.sleep(settings.MAKEMKV_KEYCHECK_INTERVAL_SECONDS)


def _resolve_paths() -> dict[str, Path]:
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


async def _current_hint(client: BackendClient, drive_id: str, *, absent: bool, absent_ticks: int) -> str:
    """The node to try when there is no by-id link. Normally ARM_DRIVE_DEV;
    while such a drive is absent, ask the backend — its scanner tracks the
    port -> node mapping and may have seen the drive come back renumbered.

    `absent` is the PREVIOUS tick's state, not `handle.absent`: a node that
    resolves but answers ENXIO (Ruling C) is absence too, and it leaves the
    handle populated, so keying off the handle would never refresh there.
    """
    if settings.ARM_DRIVE_BY_ID or not absent:
        return settings.ARM_DRIVE_DEV
    if absent_ticks % _hint_refresh_every_n_ticks() != 0:
        return settings.ARM_DRIVE_DEV
    try:
        drive = await client.get_drive(drive_id)
    except (httpx.HTTPError, OSError) as exc:
        logger.debug("hint refresh failed: %s", exc)
        return settings.ARM_DRIVE_DEV
    return drive.device_path if drive is not None and drive.device_path else settings.ARM_DRIVE_DEV


async def _on_reattached(client: BackendClient, drive_id: str, handle: DriveHandle, controller: JobController) -> None:
    """The drive came back after an ABSENT run. Whatever is seated now may be
    a different disc, and a rip may have been in flight when it left."""
    if not controller.is_idle():
        # A rip pipeline is still running against the old node (the drive was
        # yanked mid-rip and makemkvcon has not given up yet). boot_probe would
        # resume the same job, wiping the raw dir under the live process and
        # starting a second rip. Leave it to the running pipeline to fail out.
        logger.info("reattach: previous rip pipeline still active on %s; skipping boot probe", handle.current)
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


async def poll_loop(controller: JobController, handle: DriveHandle, *, client: BackendClient, drive_id: str) -> None:
    detector = InsertDetector(not_ready_rearm_polls=settings.ARM_NOT_READY_REARM_POLLS)
    last_state: DriveState | None = None
    active_task: asyncio.Task[None] | None = None
    last_error_kind: DriveErrorKind | None = None
    # Ticks that have run with the drive already known absent: 0 on the first
    # such tick, so it refreshes and later ones are throttled.
    absent_ticks = 0
    while True:
        # Re-resolve every poll: the node behind this drive can change while we
        # run (replug under a new srN). One readlink; cheap.
        was_absent = last_state is DriveState.ABSENT
        hint = await _current_hint(client, drive_id, absent=was_absent, absent_ticks=absent_ticks)
        absent_ticks = absent_ticks + 1 if was_absent else 0
        resolved = resolve_drive_device(settings.ARM_DRIVE_BY_ID, hint, **_resolve_paths())
        moved = handle.set(resolved.path if resolved else None)

        if handle.absent:
            state = DriveState.ABSENT
            last_error_kind = None
        else:
            try:
                state = read_drive_status(handle.current or "")
                last_error_kind = None
            except OSError as exc:
                kind = classify_drive_error(exc)
                if kind is DriveErrorKind.ABSENT:
                    # The node resolved but the hardware said no (ENXIO/ENODEV,
                    # or it vanished between resolve and open). Keep the handle —
                    # the node is still the right one — and report absence.
                    state = DriveState.ABSENT
                elif kind is DriveErrorKind.MISCONFIGURED:
                    if last_error_kind is not kind:
                        logger.warning(
                            "drive %s is present but misconfigured: %s — check the device cgroup rule and CDROM_GID",
                            handle.current,
                            exc.strerror or exc,
                        )
                    state = DriveState.NO_INFO
                else:
                    logger.warning("ioctl failed: %s", exc)
                    state = DriveState.NO_INFO
                last_error_kind = kind

        # Transitions are keyed on state so a node that resolves but answers
        # ENXIO cannot flap between "present" and "absent" every poll. They run
        # BEFORE detector.update so a reset re-arms for this very reading.
        if state is DriveState.ABSENT and last_state is not DriveState.ABSENT:
            logger.warning("drive absent (by_id=%s) — polling until it returns", settings.ARM_DRIVE_BY_ID)
        elif last_state is DriveState.ABSENT and state is not DriveState.ABSENT:
            if resolved is not None:
                logger.info("drive present at %s via %s (reattached)", resolved.path, resolved.via)
            detector.reset()
            # Report the node BEFORE the probe: _on_reattached can run a whole
            # resumed rip, and the UI must not sit on the stale node for its
            # entire duration.
            await _report_node(client, drive_id, handle.current or "")
            await _on_reattached(client, drive_id, handle, controller)
        elif moved and not handle.absent:
            if resolved is not None:
                logger.info("drive node moved to %s via %s", resolved.path, resolved.via)
            await _report_node(client, drive_id, handle.current or "")

        if state != last_state:
            logger.info("drive state %s -> %s", last_state, state)
            last_state = state

        if active_task is not None and active_task.done():
            active_task = None

        # detector.update() must run every poll to track the NOT_READY
        # streak; only act on the True edge when no rip is already running.
        if detector.update(state) and active_task is None and handle.current is not None:
            active_task = asyncio.create_task(controller.handle_disc_inserted(handle.current))

        await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)


def _ws_url_from_backend_url(base: str) -> str:
    if base.startswith("https://"):
        return "wss://" + base[len("https://") :].rstrip("/") + "/ws"
    if base.startswith("http://"):
        return "ws://" + base[len("http://") :].rstrip("/") + "/ws"
    return base.rstrip("/") + "/ws"


async def amain() -> None:
    client = BackendClient(
        settings.ARM_BACKEND_URL,
        settings.ARM_SERVICE_TOKEN,
        hostname=settings.HOSTNAME,
    )
    ssl_ctx = ssl.create_default_context(cafile=CA_BUNDLE_PATH)
    ws_url = _ws_url_from_backend_url(settings.ARM_BACKEND_URL)
    # In ISO mode the device_path is the ISO file; everything downstream
    # (register, JobController, heartbeat) sees it as the bound device.
    # Boot probe is also skipped — there's no crashed rip to recover.
    iso_path = settings.ARM_MANUAL_TRIGGER_ISO
    iso_mode = iso_path is not None
    # Narrow on `iso_path` itself rather than the `iso_mode` alias, so mypy
    # can see the str inside the branch without an ignore.
    if iso_path is not None:
        handle = DriveHandle.fixed(iso_path)
    else:
        first = resolve_drive_device(settings.ARM_DRIVE_BY_ID, settings.ARM_DRIVE_DEV, **_resolve_paths())
        handle = DriveHandle(first.path if first else None)
        if first is not None:
            logger.info("drive present at %s via %s", first.path, first.via)
        if handle.absent:
            logger.warning("starting with the drive absent (by_id=%s); will poll for it", settings.ARM_DRIVE_BY_ID)
    # The backend's register payload needs a device path; the configured
    # node is the honest answer until the poll loop reports the real one.
    device_path: str = handle.current or settings.ARM_DRIVE_DEV
    try:
        drive_id = await register_with_retry(client, device_path)
        async with WSClient(
            ws_url,
            settings.ARM_SERVICE_TOKEN,
            hostname=settings.HOSTNAME,
            ssl_context=ssl_ctx,
        ) as ws:
            controller = JobController(
                client,
                drive_id,
                ws=ws,
                device_path=handle,
                default_min_length_seconds=settings.ARM_MIN_LENGTH_SECONDS,
            )
            await ws.subscribe(f"ripper.commands.{drive_id}", controller.on_ws_command)
            if not iso_mode and not handle.absent:
                # Phase 9 — recover a crashed in-flight rip on this drive, if any.
                # Logs + swallows all errors so a misbehaving probe never blocks boot.
                # (If the drive is absent now, the poll loop re-runs this on reattach.)
                try:
                    await boot_probe(client, drive_id, handle.current or "", controller)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("boot probe failed: %s", exc)
            heartbeat_task = asyncio.create_task(heartbeat_loop(client, drive_id, handle, controller))
            keycheck_task = asyncio.create_task(makemkv_keycheck_loop(client))
            try:
                if iso_mode:
                    logger.info("ARM_MANUAL_TRIGGER_ISO=%s; running one-shot pipeline", handle.current)
                    # handle_manual_trigger bypasses the auto_rip_on_insert
                    # config check; handle_disc_inserted would no-op when
                    # the operator has auto-rip disabled. The ISO env var
                    # IS the explicit trigger so we want the manual path.
                    await controller.handle_manual_trigger(session_id=None)
                    logger.info("manual-trigger ISO pipeline complete; idling for cancellation")
                    # Idle indefinitely so the WS stays subscribed and the
                    # container stays "up" for `docker compose ps` /
                    # `docker compose logs` observation. Operator kills the
                    # container when done inspecting.
                    await asyncio.Event().wait()
                else:
                    await poll_loop(controller, handle, client=client, drive_id=drive_id)
            finally:
                heartbeat_task.cancel()
                keycheck_task.cancel()
    finally:
        await client.close()


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
