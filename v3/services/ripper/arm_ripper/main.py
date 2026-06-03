import asyncio
import logging
import ssl
from pathlib import Path

import httpx

from arm_common import DriveMediaStatus, configure_service_logging
from arm_ripper.backend_client import BackendClient
from arm_ripper.config import settings
from arm_ripper.drive_poll import DriveState, read_drive_status
from arm_ripper.drive_status import probe_drive_media
from arm_ripper.job_controller import JobController
from arm_ripper.recovery import boot_probe
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

# Each ripper container owns one optical drive — name the log file by the
# device basename so multiple ripper containers (sr0, sr1, ...) don't
# collide on the shared `./logs` host volume.
configure_service_logging(f"arm-ripper-{Path(settings.ARM_DRIVE_DEV).name}", level=settings.ARM_LOG_LEVEL)
logger = logging.getLogger("arm_ripper")


async def register_with_retry(client: BackendClient, device_path: str) -> str:
    delay = 1.0
    while True:
        try:
            drive = await client.register(
                hostname=settings.HOSTNAME,
                device_path=device_path,
                ripper_version=RIPPER_VERSION,
            )
            logger.info("registered drive_id=%s device=%s", drive.id, device_path)
            return drive.id
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("register failed (%s); retrying in %.1fs", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)


async def heartbeat_loop(client: BackendClient, drive_id: str, device_path: str) -> None:
    """Post the current media status to the backend every
    HEARTBEAT_INTERVAL_SECONDS. Errors are logged + swallowed —
    the heartbeat is best-effort and stale rows fall back to
    "unknown" on the manual-trigger pre-check.

    For ISO sources we skip the SCSI ioctl (it fails on regular files)
    and report `loaded` unconditionally — the source is always present
    by construction in manual-trigger mode.
    """
    while True:
        try:
            if is_iso_source(device_path):
                status = DriveMediaStatus.LOADED
            else:
                status, _ = probe_drive_media(device_path)
            await client.heartbeat(drive_id=drive_id, media_status=status)
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("heartbeat failed: %s", exc)
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)


async def poll_loop(controller: JobController) -> None:
    last_state: DriveState | None = None
    active_task: asyncio.Task[None] | None = None
    while True:
        try:
            state = read_drive_status(settings.ARM_DRIVE_DEV)
        except OSError as exc:
            logger.warning("ioctl failed: %s", exc)
            state = DriveState.NO_INFO

        if state != last_state:
            logger.info("drive state %s -> %s", last_state, state)

        if active_task is not None and active_task.done():
            active_task = None

        if (
            state == DriveState.DISC_OK
            and last_state not in (DriveState.DISC_OK, DriveState.NOT_READY)
            and active_task is None
        ):
            active_task = asyncio.create_task(controller.handle_disc_inserted(settings.ARM_DRIVE_DEV))

        last_state = state
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
    device_path: str = iso_path if iso_path is not None else settings.ARM_DRIVE_DEV
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
                device_path=device_path,
                default_min_length_seconds=settings.ARM_MIN_LENGTH_SECONDS,
            )
            await ws.subscribe(f"ripper.commands.{drive_id}", controller.on_ws_command)
            if not iso_mode:
                # Phase 9 — recover a crashed in-flight rip on this drive, if any.
                # Logs + swallows all errors so a misbehaving probe never blocks boot.
                try:
                    await boot_probe(client, drive_id, device_path, controller)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("boot probe failed: %s", exc)
            heartbeat_task = asyncio.create_task(heartbeat_loop(client, drive_id, device_path))
            try:
                if iso_mode:
                    logger.info("ARM_MANUAL_TRIGGER_ISO=%s; running one-shot pipeline", device_path)
                    await controller.handle_disc_inserted(device_path)
                    logger.info("manual-trigger ISO pipeline complete; idling for cancellation")
                    # Idle indefinitely so the WS stays subscribed and the
                    # container stays "up" for `docker compose ps` /
                    # `docker compose logs` observation. Operator kills the
                    # container when done inspecting.
                    await asyncio.Event().wait()
                else:
                    await poll_loop(controller)
            finally:
                heartbeat_task.cancel()
    finally:
        await client.close()


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
