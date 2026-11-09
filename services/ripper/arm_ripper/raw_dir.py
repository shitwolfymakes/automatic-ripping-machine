"""The jobs' raw rip folders under /raw, and their removal."""

import asyncio
import logging
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RAW_ROOT = Path("/raw")


async def wipe_raw_dir(job_id: str) -> None:
    """Remove /raw/<job_id>/ and everything in it, best-effort: an entry that
    cannot be removed is skipped and the rest still goes. Logs what happened:
    wiped, already absent, or a warning naming what could not be removed.
    Safe to call repeatedly. Runs in a thread so a large raw dir does not
    block the event loop.
    """
    target = RAW_ROOT / job_id
    failures: list[BaseException] = []

    def _skip(_function: Callable[..., Any], _path: str, exc: BaseException) -> None:
        failures.append(exc)

    await asyncio.to_thread(shutil.rmtree, target, onexc=_skip)
    _log_wipe(job_id, target, failures)


def _log_wipe(job_id: str, target: Path, failures: list[BaseException]) -> None:
    """Log what a best-effort wipe did: wiped, already absent, or what could not be removed."""
    errors = [exc for exc in failures if not isinstance(exc, FileNotFoundError)]
    if errors:
        logger.warning(
            "raw-dir cleanup failed job_id=%s path=%s: %s (%d error(s))", job_id, target, errors[0], len(errors)
        )
    elif _was_absent(target, failures):
        logger.info("raw dir already absent job_id=%s path=%s", job_id, target)
    else:
        logger.info("wiped raw dir job_id=%s path=%s", job_id, target)


def _was_absent(target: Path, failures: list[BaseException]) -> bool:
    """Whether the wipe found no folder at all: rmtree reports the missing root itself as a FileNotFoundError."""
    return any(
        isinstance(exc, FileNotFoundError) and exc.filename is not None and os.fspath(exc.filename) == os.fspath(target)
        for exc in failures
    )
