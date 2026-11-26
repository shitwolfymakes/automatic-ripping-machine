"""Registering this ripper with the backend, retrying until it is accepted."""

import asyncio
import logging

import httpx

from arm_ripper.backend_client import BackendClient, RegisterRefused
from arm_ripper.config import settings

logger = logging.getLogger("arm_ripper")

RIPPER_VERSION = "0.0.0-skeleton"

# A register refusal (unknown drive, not enrolled, identity mismatch) is not
# retriable in the sense of "try again right now" — but it IS self-healing:
# the operator can fix the enrollment (re-enroll to rebind identity, etc.)
# without restarting the container. Poll slowly instead of parking forever.
REGISTER_REFUSED_RETRY_SECONDS = 60.0


def _log_refusal(exc: RegisterRefused, last_refusal: str | None) -> str:
    """Log a register refusal at ERROR the first time its text appears (or when it changes) and at DEBUG on an
    unchanged repeat; returns the refusal text to compare the next one against.
    """
    message = str(exc)
    # Log at ERROR the first time this refusal is seen and again
    # whenever its text changes (a new/different problem); an
    # unchanged repeat is downgraded to DEBUG so a stuck enrollment
    # doesn't spam the log once a minute forever.
    level = logging.ERROR if message != last_refusal else logging.DEBUG
    logger.log(
        level,
        "register refused for drive_id=%s: %s — container left running for diagnosis; "
        "fix the enrollment in the UI; retrying in %.0fs",
        settings.ARM_DRIVE_ID,
        exc,
        REGISTER_REFUSED_RETRY_SECONDS,
    )
    return message


async def register_with_retry(client: BackendClient, device_path: str) -> str:
    """Retry transport/5xx failures with backoff. A refusal (unknown drive,
    not enrolled, identity mismatch) is self-healing rather than fatal: the
    operator can fix the enrollment from the UI (e.g. unenroll/re-enroll to
    rebind identity) without restarting this container, so we log it and
    keep polling slowly instead of parking forever."""
    delay = 1.0
    last_refusal: str | None = None
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
            last_refusal = _log_refusal(exc, last_refusal)
            await asyncio.sleep(REGISTER_REFUSED_RETRY_SECONDS)
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("register failed (%s); retrying in %.1fs", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)
