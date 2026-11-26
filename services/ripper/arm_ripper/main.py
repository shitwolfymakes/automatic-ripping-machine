import asyncio
import logging
import ssl
import sys

from arm_common import configure_service_logging
from arm_ripper.backend_client import BackendClient
from arm_ripper.config import settings
from arm_ripper.drive_handle import DriveHandle
from arm_ripper.drive_poller import poll_loop, resolve_paths
from arm_ripper.drive_resolve import resolve_drive_device
from arm_ripper.heartbeat import heartbeat_loop
from arm_ripper.job_controller import JobController
from arm_ripper.makemkv_keycheck import makemkv_keycheck_loop
from arm_ripper.recovery import boot_probe
from arm_ripper.registration import register_with_retry
from arm_ripper.source_mode import run_source_mode
from arm_ripper import prepare
from arm_ripper.ws_client import WSClient

CA_BUNDLE_PATH = "/etc/ssl/certs/ca-certificates.crt"

# The backend spawns each ripper container for one Drive row and sets
# HOSTNAME to arm-ripper-<serial>-<drive-id suffix> (a stable identity); srN
# is not stable across a renumbering replug, so the log file is named from
# the identity the manager assigned rather than the current device node.
configure_service_logging(settings.HOSTNAME, level=settings.ARM_LOG_LEVEL)
logger = logging.getLogger("arm_ripper")


def _ws_url_from_backend_url(base: str) -> str:
    if base.startswith("https://"):
        return "wss://" + base[len("https://") :].rstrip("/") + "/ws"
    if base.startswith("http://"):
        return "ws://" + base[len("http://") :].rstrip("/") + "/ws"
    return base.rstrip("/") + "/ws"


def _build_client() -> BackendClient:
    """The backend client for this ripper, authenticated with its service token and named by its hostname and drive."""
    return BackendClient(
        settings.ARM_BACKEND_URL,
        settings.ARM_SERVICE_TOKEN,
        hostname=settings.HOSTNAME,
        drive_id=settings.ARM_DRIVE_ID,
    )


def _initial_handle(source_path: str | None) -> DriveHandle:
    """The drive handle to start with: fixed on the bound ISO in source mode, otherwise the drive's current node
    (absent when it isn't plugged in yet; the poll loop keeps looking).
    """
    # Narrow on `source_path` itself rather than the `source_mode` alias, so
    # mypy can see the str inside the branch without an ignore.
    if source_path is not None:
        handle = DriveHandle.fixed(source_path)
    else:
        first = resolve_drive_device(settings.ARM_DRIVE_BY_ID, settings.ARM_DRIVE_DEV or "", **resolve_paths())
        handle = DriveHandle(first.path if first else None)
        if first is not None:
            logger.info("drive present at %s via %s", first.path, first.via)
        if handle.absent:
            logger.warning("starting with the drive absent (by_id=%s); will poll for it", settings.ARM_DRIVE_BY_ID)
    return handle


def _build_controller(
    client: BackendClient, drive_id: str, ws: WSClient, handle: DriveHandle, *, source_mode: bool
) -> JobController:
    """The job controller for this drive. In source mode it never times out a wait for the operator: the backend's
    watchdog retires the drive once this container exits, so it must not exit FAILED while the operator is still
    parked at AWAITING_USER_ID / AWAITING_REVIEW.
    """
    if source_mode:
        return JobController(
            client,
            drive_id,
            ws=ws,
            device_path=handle,
            default_min_length_seconds=settings.ARM_MIN_LENGTH_SECONDS,
            resolution_timeout=None,
        )
    return JobController(
        client,
        drive_id,
        ws=ws,
        device_path=handle,
        default_min_length_seconds=settings.ARM_MIN_LENGTH_SECONDS,
    )


async def _recover_crashed_rip(
    client: BackendClient, drive_id: str, handle: DriveHandle, controller: JobController
) -> None:
    """Recover a rip that crashed in flight on this drive, if any; logs and swallows every error so a
    misbehaving probe never blocks boot.
    """
    try:
        await boot_probe(client, drive_id, handle.current or "", controller)
    except Exception as exc:  # noqa: BLE001
        logger.exception("boot probe failed: %s", exc)


async def _run_mode(
    controller: JobController, handle: DriveHandle, *, client: BackendClient, drive_id: str, source_mode: bool
) -> None:
    """Run this container's job until it ends: the one-shot pipeline for the bound ISO in source mode, otherwise the
    drive poll loop (which runs until cancelled).
    """
    if source_mode:
        logger.info("ARM_SOURCE_PATH=%s; running one-shot pipeline", handle.current)
        await run_source_mode(controller, settings.ARM_SOURCE_SESSION_ID)
        logger.info("source pipeline complete; exiting")
    else:
        await poll_loop(controller, handle, client=client, drive_id=drive_id)


async def amain() -> None:
    client = _build_client()
    ssl_ctx = ssl.create_default_context(cafile=CA_BUNDLE_PATH)
    ws_url = _ws_url_from_backend_url(settings.ARM_BACKEND_URL)
    # In source mode the device_path is the bound ISO file; everything
    # downstream (register, JobController, heartbeat) sees it as the bound
    # device. Boot probe is also skipped — there's no crashed rip to
    # recover (the backend spawns a fresh container per ISO rip).
    source_path = settings.ARM_SOURCE_PATH
    source_mode = source_path is not None
    if source_path is None and settings.ARM_DRIVE_DEV is None:
        logger.error("neither ARM_SOURCE_PATH nor ARM_DRIVE_DEV is set; nothing to rip")
        sys.exit(2)
    handle = _initial_handle(source_path)
    # The backend's register payload needs a device path; the configured
    # node is the honest answer until the poll loop reports the real one.
    device_path: str = handle.current or settings.ARM_DRIVE_DEV or ""
    try:
        drive_id = await register_with_retry(client, device_path)
        async with WSClient(
            ws_url,
            settings.ARM_SERVICE_TOKEN,
            hostname=settings.HOSTNAME,
            ssl_context=ssl_ctx,
        ) as ws:
            if source_mode:
                # Until identify creates the job, the dashboard shows this rip
                # through its "preparing" reports (scanning / extracting).
                prepare.configure(client, drive_id)
            controller = _build_controller(client, drive_id, ws, handle, source_mode=source_mode)
            await ws.subscribe(f"ripper.commands.{drive_id}", controller.on_ws_command)
            if not source_mode and not handle.absent:
                # (If the drive is absent now, the poll loop re-runs this on reattach.)
                await _recover_crashed_rip(client, drive_id, handle, controller)
            heartbeat_task = asyncio.create_task(heartbeat_loop(client, drive_id, handle, controller))
            keycheck_task = asyncio.create_task(makemkv_keycheck_loop(client))
            try:
                await _run_mode(controller, handle, client=client, drive_id=drive_id, source_mode=source_mode)
            finally:
                heartbeat_task.cancel()
                keycheck_task.cancel()
    finally:
        await client.close()


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
