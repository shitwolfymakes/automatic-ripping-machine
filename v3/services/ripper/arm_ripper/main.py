import asyncio
import logging

import httpx

from arm_common import DiscType
from arm_ripper.backend_client import BackendClient
from arm_ripper.config import settings
from arm_ripper.drive_poll import DriveState, read_drive_status

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
            resp = await client.register(
                hostname=settings.HOSTNAME,
                device_path=settings.ARM_DRIVE_DEV,
                ripper_version=RIPPER_VERSION,
            )
            logger.info("registered drive_id=%s device=%s", resp.drive_id, settings.ARM_DRIVE_DEV)
            return resp.drive_id
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("register failed (%s); retrying in %.1fs", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)


async def poll_loop(client: BackendClient, drive_id: str) -> None:
    last_state: DriveState | None = None
    while True:
        try:
            state = read_drive_status(settings.ARM_DRIVE_DEV)
        except OSError as exc:
            logger.warning("ioctl failed: %s", exc)
            state = DriveState.NO_INFO

        if state != last_state:
            logger.info("drive state %s -> %s", last_state, state)

        if state == DriveState.DISC_OK and last_state not in (DriveState.DISC_OK, DriveState.NOT_READY):
            try:
                resp = await client.identify(
                    drive_id=drive_id,
                    disc_type=DiscType.UNKNOWN,
                    volume_label=None,
                    scan_result={},
                )
                logger.info("identify job_id=%s status=%s", resp.job_id, resp.status)
            except httpx.HTTPError as exc:
                logger.error("identify failed: %s", exc)

        last_state = state
        await asyncio.sleep(settings.POLL_INTERVAL_SECONDS)


async def amain() -> None:
    client = BackendClient(settings.ARM_BACKEND_URL, settings.ARM_SERVICE_TOKEN)
    try:
        drive_id = await register_with_retry(client)
        await poll_loop(client, drive_id)
    finally:
        await client.close()


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
