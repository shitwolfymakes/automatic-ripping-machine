"""Background disk-usage refresher — keeps the disk_usage_cache warm.

A single asyncio task started in the FastAPI lifespan (mirrors log_tailer):
periodically refresh each registered root via run_in_executor so a stalled
NFS probe never blocks the event loop.
"""

from __future__ import annotations

import asyncio
import logging

from arm_backend.disk_usage_cache import REFRESH_INTERVAL, refresh_path

log = logging.getLogger("arm_backend")


class DiskRefresher:
    def __init__(self, paths: list[str]) -> None:
        self._paths = paths
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        while not self._stopped:
            for path in self._paths:
                if self._stopped:
                    break
                await loop.run_in_executor(None, refresh_path, path)
            # Sleep in small slices so stop() is responsive.
            slept = 0.0
            while slept < REFRESH_INTERVAL and not self._stopped:
                await asyncio.sleep(min(0.5, REFRESH_INTERVAL - slept))
                slept += 0.5
