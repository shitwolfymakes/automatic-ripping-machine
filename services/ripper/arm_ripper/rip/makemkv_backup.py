"""Decrypted Blu-ray folder backup: one `makemkvcon backup --decrypt` per disc.

MakeMKV writes the disc's `BDMV/` and `CERTIFICATE/` tree, decrypted, under
`<output_dir>/backup`. There are no titles and no `.mkv` files, so only the
mode-independent half of the `mkv all` stream handling is shared
(`makemkv_rip._run_makemkvcon`): PRGV progress, MSG diagnostics, the MSG:5021
kill switch, the timeout and cancel-safe cleanup. Progress is the disc-level
PRGV `total/max` from the first line, since backup mode's phase markers are
not the `mkv all` save marker (PRGT:5024).
"""

import asyncio
import logging
import shutil
from pathlib import Path

from arm_common.fileops import tree_size

from arm_ripper.rip.makemkv_rip import OnDiscProgress, RipResult, _compose_error, _ParserState, _run_makemkvcon
from arm_ripper.source import makemkv_source_url

logger = logging.getLogger("arm_ripper.rip.makemkv_backup")

BACKUP_DIRNAME = "backup"


async def rip_backup(device_path: str, output_dir: Path, on_progress: OnDiscProgress | None = None) -> RipResult:
    """Back up the disc in `device_path` to `output_dir/backup`, decrypted.

    Success needs a clean exit and `backup/BDMV/index.bdmv`. The result's
    `size_bytes` is the tree's file total; there is no sha256 (MakeMKV checks
    the content as it decrypts, and re-reading up to 100 GB to hash it would
    double the time).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / BACKUP_DIRNAME
    # A backup left by an earlier run must never pass this run's success check.
    shutil.rmtree(target, ignore_errors=True)
    cmd = [
        "makemkvcon",
        "backup",
        "--decrypt",
        "--robot",
        "--progress=-stdout",
        makemkv_source_url(device_path),
        str(target),
    ]
    logger.info("makemkvcon backup device=%s outdir=%s", device_path, target)

    state = _ParserState()
    error = await _run_makemkvcon(cmd, state, on_disc_progress=on_progress, gate_disc_progress=False)
    if error is not None:
        return RipResult(ok=False, error=error)
    if not (target / "BDMV" / "index.bdmv").is_file():
        return RipResult(ok=False, error=_compose_error("makemkvcon backup produced no BDMV", state.diagnostics))
    size = await asyncio.to_thread(tree_size, target)
    return RipResult(ok=True, output_path=target, size_bytes=size)
