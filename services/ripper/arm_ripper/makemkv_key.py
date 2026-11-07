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

Key precedence (highest first):

1. The operator key configured in the UI (`Config.makemkv_key`). The
   JobController fetches it and passes it as ``key`` here; we inject it as
   ``MAKEMKV_KEY`` in the script's environment so the configured value wins
   over any host-set env var.
2. The legacy ``MAKEMKV_KEY`` env var on the ripper container (inherited by
   the subprocess when ``key`` is ``None``).
3. The monthly free beta key scraped from the MakeMKV forum.
"""

import logging
import os

from arm_ripper.refresh_script import run_refresh_script

logger = logging.getLogger("arm_ripper.makemkv_key")

# Installed by the ripper Dockerfile (services/ripper/install/update_key.sh
# → here). The same script the shared entrypoint runs at boot.
UPDATE_KEY_SCRIPT = "/usr/local/bin/update_key.sh"
# Bounds the forum key-scrape in update_key.sh (curl has no --max-time of its
# own). The MakeMKV forum thread we scrape can respond slowly — latencies past
# 50s have been observed — and a refresh that times out leaves makemkvcon with
# no current beta key, which it reports as MSG:5021 and the scan then
# misclassifies the disc as `data`. 120s gives enough headroom that a
# slow-but-alive forum still yields a key before the scan runs.
REFRESH_TIMEOUT_SECONDS = 120.0


async def refresh_makemkv_key(script_path: str = UPDATE_KEY_SCRIPT, key: str | None = None) -> None:
    """Refresh `~/.MakeMKV/settings.conf` before makemkvcon runs.

    When ``key`` is supplied (the operator key from `Config.makemkv_key`),
    it is injected as ``MAKEMKV_KEY`` in the script's environment so it
    overrides any host-set env var. When ``None``, the subprocess inherits
    the parent environment unchanged, preserving the legacy env-var path and
    the forum-scrape fallback.

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
    # Inject the configured key (if any) so update_key.sh's MAKEMKV_KEY branch
    # picks it up ahead of any host-set value. A blank/whitespace key is
    # treated as unset so it doesn't shadow the env/scrape fallbacks.
    env = None
    if key and key.strip():
        env = {**os.environ, "MAKEMKV_KEY": key}

    # update_key.sh narrates which branch it took ("using MAKEMKV_KEY from
    # env" vs "scraping monthly beta key from forum"); the runner logs that
    # output so operators can confirm the per-rip refresh ran.
    await run_refresh_script(
        script_path, env=env, timeout=REFRESH_TIMEOUT_SECONDS, label="makemkv key refresh", logger=logger
    )
