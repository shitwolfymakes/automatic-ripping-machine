import asyncio
import logging

import httpx

from arm_ripper.backend_client import BackendClient
from arm_ripper.config import settings
from arm_ripper.drive_poll import DriveState, read_drive_status
from arm_ripper.job_controller import JobController

RIPPER_VERSION = "0.0.0-skeleton"

logging.basicConfig(
    level=settings.ARM_LOG_LEVEL.upper(),
    format='{"ts":"%(asctime)s","level":"%(levelname)s","service":"arm-ripper","msg":%(message)r}',
)
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


async def amain() -> None:
    client = BackendClient(
        settings.ARM_BACKEND_URL,
        settings.ARM_SERVICE_TOKEN,
        hostname=settings.HOSTNAME,
    )
    try:
        drive_id = await register_with_retry(client)
        controller = JobController(client, drive_id)
        await poll_loop(controller)
    finally:
        await client.close()


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
