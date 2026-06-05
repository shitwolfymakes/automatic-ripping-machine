"""TranscodeTool.NONE handler — copy or rename the raw file to /media.

Used by ISO and data-copy sessions where there's no transcoding to do.
Tries `os.rename` first (atomic, instant on the same filesystem); falls
back to `shutil.copy2` + remove when source and dest are on different
mount points (common when /raw is local and /media is a NAS share).

No live progress — the operation is either instantaneous (rename) or
limited by disk throughput (copy). The caller may still report a single
100% heartbeat after success for UI consistency.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger("arm_transcode.passthrough")


def transcode_none(input_path: Path, output_path: Path) -> int:
    """Move-or-copy `input_path` → `output_path`. Returns the final file size.

    Caller is responsible for using `atomic_output` if the destination
    needs the `.arm-inprogress` rename dance — but for passthrough the
    operation is itself atomic, so the caller can just write directly to
    the final path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(input_path, output_path)
    except OSError as exc:
        logger.info("passthrough rename failed (%s); falling back to copy+remove", exc)
        shutil.copy2(input_path, output_path)
        try:
            input_path.unlink()
        except OSError as cleanup_exc:
            logger.warning("post-copy unlink failed: %s (will leave source in /raw)", cleanup_exc)
    size = output_path.stat().st_size
    logger.info("passthrough wrote %s (%d bytes)", output_path, size)
    return size
