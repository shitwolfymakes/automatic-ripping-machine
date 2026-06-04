"""Per-rip MakeMKV key refresh.

The ripper refreshes `~/.MakeMKV/settings.conf` once per disc, before
makemkvcon first touches it — see the two call sites in
`job_controller.py`. Without this, a container left up across a beta-key
rotation drifts onto a stale key and starts refusing protected discs
until the next restart.

The heavy lifting lives in `update_key.sh`: it reads `MAKEMKV_KEY` from
the environment and, when set, writes that operator key into
`~/.MakeMKV/settings.conf`; otherwise it scrapes the current month's free
beta key from the MakeMKV forum.
"""

import asyncio
import logging
import os

logger = logging.getLogger("arm_ripper.makemkv_key")

# Installed by the ripper Dockerfile (services/ripper/install/update_key.sh
# → here). The same script the shared entrypoint runs at boot.
UPDATE_KEY_SCRIPT = "/usr/local/bin/update_key.sh"
REFRESH_TIMEOUT_SECONDS = 30.0


async def refresh_makemkv_key(script_path: str = UPDATE_KEY_SCRIPT) -> None:
    """Refresh `~/.MakeMKV/settings.conf` before makemkvcon runs.

    Non-fatal by design. Two reasons it's safe to swallow errors:

    - `update_key.sh` already exits 0 and leaves the existing key in
      place on a transient forum-scrape failure, so a non-zero exit only
      signals a genuinely broken invocation, not "this month's scrape
      blipped".
    - A truly dead key surfaces precisely *downstream*: `scan_disc` and
      `rip_disc` report the makemkvcon error ("App key incorrect") or the
      MSG:5021 binary-expiry distinctly. Aborting the whole pipeline on a
      key-refresh hiccup would be strictly worse than letting makemkvcon
      try the key that's already on disk.
    """
    if not os.access(script_path, os.X_OK):
        # Mirrors the entrypoint's `[[ -x … ]]` guard: no scraper present
        # (non-makemkv image, unit-test host) means nothing to refresh.
        logger.debug("makemkv key refresh skipped: %s not executable", script_path)
        return

    try:
        proc = await asyncio.create_subprocess_exec(
            script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as exc:
        logger.warning("makemkv key refresh could not start (%s): %s", script_path, exc)
        return

    try:
        stdout_b, _ = await asyncio.wait_for(proc.communicate(), timeout=REFRESH_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        logger.warning("makemkv key refresh timed out after %.0fs", REFRESH_TIMEOUT_SECONDS)
        return

    # update_key.sh narrates which branch it took ("using MAKEMKV_KEY from
    # env" vs "scraping monthly beta key from forum"); surface it so
    # operators can confirm the per-rip refresh ran.
    text = stdout_b.decode(errors="replace").strip()
    if proc.returncode == 0:
        if text:
            logger.info("makemkv key refresh: %s", text.replace("\n", " | "))
    else:
        logger.warning("makemkv key refresh exited %s: %s", proc.returncode, text or "<no output>")
