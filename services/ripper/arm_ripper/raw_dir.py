"""The jobs' raw rip folders under /raw, and their removal."""

import asyncio
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

RAW_ROOT = Path("/raw")


async def wipe_raw_dir(job_id: str) -> None:
    """Remove /raw/<job_id>/ and its contents. No-op if the directory
    does not exist. Safe to call repeatedly. Runs in a thread so a large
    raw dir does not block the event loop.
    """
    target = RAW_ROOT / job_id
    await asyncio.to_thread(shutil.rmtree, target, ignore_errors=True)
    logger.info("wiped raw dir job_id=%s path=%s", job_id, target)
