"""The ripper's periodic makemkv key check: write the configured key to settings.conf when it changes, probe it
and report the result to the backend."""

import asyncio
import logging

import httpx

from arm_ripper.backend_client import BackendClient
from arm_ripper.config import settings
from arm_ripper.makemkv_key import refresh_makemkv_key
from arm_ripper.scan.makemkv_key_probe import probe_makemkv_key

logger = logging.getLogger("arm_ripper")


def makemkv_key_changed(*, prev: str | None, current: str | None) -> bool:
    """True when the effective makemkv key changed (treats blank as None)."""

    def _norm(v: str | None) -> str | None:
        return (v or "").strip() or None

    return _norm(prev) != _norm(current)


async def _check_makemkv_key(client: BackendClient, *, last_key: str | None, first: bool) -> str | None:
    """One key-validity pass: fetch the configured makemkv key, write it to settings.conf on the first pass or when it
    changed, probe it and report the result. Returns the key it checked.
    """
    cfg = await client.get_ripper_config()
    key = cfg.makemkv_key
    if first or makemkv_key_changed(prev=last_key, current=key):
        # Write settings.conf with the current key BEFORE probing, so the
        # probe checks the key actually on disk. (Single call — do not
        # double-invoke refresh_makemkv_key.)
        await refresh_makemkv_key(key=key)
    state, detail = await probe_makemkv_key(key)
    await client.report_makemkv_key_status(state=state, detail=detail)
    return key


async def makemkv_keycheck_loop(client: BackendClient) -> None:
    """Probe makemkv key-validity on key-change + daily, report to the backend.
    Best-effort: errors are logged + swallowed (mirrors heartbeat_loop)."""
    last_key: str | None = None
    first = True
    while True:
        try:
            last_key = await _check_makemkv_key(client, last_key=last_key, first=first)
            first = False
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("makemkv keycheck failed: %s", exc)
        except Exception:  # noqa: BLE001 — keycheck is best-effort; never let it kill the loop
            logger.exception("makemkv keycheck: unexpected error")
        await asyncio.sleep(settings.MAKEMKV_KEYCHECK_INTERVAL_SECONDS)
