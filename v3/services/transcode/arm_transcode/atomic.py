"""Atomic-rename helper for transcode outputs.

The transcoder writes `<final>.arm-inprogress`, `fsync`s, then renames to
`<final>` on success. Same filesystem, so rename is atomic. Plex/Jellyfin
scanners ignore `.arm-inprogress`, so half-written files are invisible.
On failure (exception, SIGTERM, container kill), the partial file stays
on disk for the Backend startup sweep.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger("arm_transcode.atomic")

INPROGRESS_SUFFIX = ".arm-inprogress"


@contextmanager
def atomic_output(final_path: Path) -> Iterator[Path]:
    """Yield a temp `<final>.arm-inprogress` path; rename on clean exit.

    On exception inside the `with` body the temp file is left in place
    intentionally — the Backend startup sweep cleans orphans whose
    `transcode_tasks` row is not `in_progress`. Re-raising lets the
    caller mark the task `failed` via the REST API.
    """
    tmp_path = final_path.with_name(final_path.name + INPROGRESS_SUFFIX)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        yield tmp_path
    except Exception:
        logger.warning("atomic_output failed; leaving %s for sweeper", tmp_path)
        raise
    if not tmp_path.exists():
        raise FileNotFoundError(f"transcoder did not write expected output: {tmp_path}")
    # Best-effort fsync of the directory so the rename is durable on crash.
    fd = os.open(str(final_path.parent), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp_path, final_path)
    logger.info("atomic rename → %s", final_path)
