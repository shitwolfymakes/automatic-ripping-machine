import asyncio
import logging
import ssl
from pathlib import Path

import httpx

from arm_common import configure_service_logging
from arm_ripper.backend_client import BackendClient
from arm_ripper.config import settings
from arm_ripper.drive_poll import DriveState, read_drive_status
from arm_ripper.job_controller import JobController
from arm_ripper.recovery import boot_probe
from arm_ripper.ws_client import WSClient

CA_BUNDLE_PATH = "/etc/ssl/certs/ca-certificates.crt"

RIPPER_VERSION = "0.0.0-skeleton"

# Each ripper container owns one optical drive — name the log file by the
# device basename so multiple ripper containers (sr0, sr1, ...) don't
# collide on the shared `./logs` host volume.
configure_service_logging(f"arm-ripper-{Path(settings.ARM_DRIVE_DEV).name}", level=settings.ARM_LOG_LEVEL)
logger = logging.getLogger("arm_ripper")


async def register_with_retry(client: BackendClient) -> str:
    delay = 1.0
    while True:
        try:
            drive = await client.register(
                hostname=settings.HOSTNAME,
                device_path=settings.ARM_DRIVE_DEV,
                ripper_version=RIPPER_VERSION,
            )
            logger.info("registered drive_id=%s device=%s", drive.id, settings.ARM_DRIVE_DEV)
            return drive.id
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("register failed (%s); retrying in %.1fs", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)


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
    try:
        drive_id = await register_with_retry(client)
        async with WSClient(
            ws_url,
            settings.ARM_SERVICE_TOKEN,
            hostname=settings.HOSTNAME,
            ssl_context=ssl_ctx,
        ) as ws:
            controller = JobController(client, drive_id, ws=ws)
            await ws.subscribe(f"ripper.commands.{drive_id}", controller.on_ws_command)
            # Phase 9 — recover a crashed in-flight rip on this drive, if any.
            # Logs + swallows all errors so a misbehaving probe never blocks boot.
            try:
                await boot_probe(client, drive_id, settings.ARM_DRIVE_DEV, controller)
            except Exception as exc:  # noqa: BLE001
                logger.exception("boot probe failed: %s", exc)
            await poll_loop(controller)
    finally:
        await client.close()


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
