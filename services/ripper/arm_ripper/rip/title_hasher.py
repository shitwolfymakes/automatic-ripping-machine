"""SHA-256 of each ripped title, computed while makemkvcon writes the next.

`mkv all` finishes titles one at a time, so a title's file is final as soon
as its done event arrives. Hashing it then, one file at a time in a single
worker, overlaps the read with the rest of the rip; only the last title (or
whatever the worker has not reached yet) is left when makemkvcon exits.
`finish` waits for that remainder and reports it as a "verifying" pass, so
the job page shows progress instead of a silent re-read.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from arm_ripper.rip.hashing import sha256_file

logger = logging.getLogger("arm_ripper.rip.title_hasher")

# (bytes_done, bytes_total, rate_bps) for the files still being hashed.
OnVerifyProgress = Callable[[int, int, float | None], Awaitable[None]]
# Receives the digest, or None when the file could not be read.
OnHashed = Callable[[str | None], Awaitable[None]]

VERIFY_PROGRESS_INTERVAL_SECONDS = 1.0


class TitleHasher:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._tasks: list[asyncio.Task[None]] = []
        self._bytes_total = 0
        self._bytes_done = 0

    def _on_bytes(self, n: int) -> None:
        # Called from the hashing thread; a lone int add is safe under the GIL
        # and the reader only needs an approximate figure.
        self._bytes_done += n

    def submit(self, path: Path, size: int, then: OnHashed) -> None:
        """Hash `path` in the background, then await `then(digest)`."""
        self._bytes_total += size
        self._tasks.append(asyncio.create_task(self._run(path, then)))

    async def _run(self, path: Path, then: OnHashed) -> None:
        async with self._lock:
            started = time.monotonic()
            try:
                digest: str | None = await sha256_file(path, self._on_bytes)
            except OSError as exc:
                logger.warning("sha256 of %s failed: %s", path.name, exc)
                digest = None
            else:
                logger.info("sha256 %s done in %.1fs", path.name, time.monotonic() - started)
        await then(digest)

    async def finish(self, on_progress: OnVerifyProgress | None = None) -> None:
        """Wait for every submitted file, reporting progress while any remain."""
        pending = [t for t in self._tasks if not t.done()]
        if pending:
            logger.info("verifying %d ripped file(s) still being hashed", len(pending))
            gathered = asyncio.gather(*pending)
            done_at_start = self._bytes_done
            started = time.monotonic()
            while not gathered.done():
                if on_progress is not None:
                    elapsed = time.monotonic() - started
                    moved = self._bytes_done - done_at_start
                    rate = moved / elapsed if elapsed > 0 and moved > 0 else None
                    await on_progress(self._bytes_done, self._bytes_total, rate)
                await asyncio.wait({gathered}, timeout=VERIFY_PROGRESS_INTERVAL_SECONDS)
        # Re-raise anything a `then` callback raised (a PATCH that gave up).
        await asyncio.gather(*self._tasks)

    def cancel(self) -> None:
        for task in self._tasks:
            task.cancel()
