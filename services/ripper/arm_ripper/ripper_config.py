"""Fail-open lookup of the Backend's ripper config, shared by the review countdown, auto-rip and MakeMKV prep."""

import logging

import httpx

from arm_common.schemas import RipperConfigView
from arm_ripper.backend_client import BackendClient

# The moved code keeps the job controller's logger name so existing log filters and log text stay the same.
logger = logging.getLogger("arm_ripper.job_controller")


async def ripper_config_or_none(client: BackendClient, what: str, fallback: str) -> RipperConfigView | None:
    """The ripper config, or None after a warning when the backend can't be reached."""
    try:
        return await client.get_ripper_config()
    except httpx.HTTPError as e:
        logger.warning("%s failed (%s); %s", what, e, fallback)
        return None
