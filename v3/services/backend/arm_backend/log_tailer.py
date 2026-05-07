"""Phase 12 — singleton tail of `/logs/*.log` → `logs.{job_id}` WS topic.

A single asyncio task started in the FastAPI lifespan, mirroring the shape
of `NotificationDispatcher`. Each tick:

1. Rescan `/logs` for new `*.log` files; open any not yet tracked.
2. Drain new lines from each tracked file via `run_in_executor(readline)`
   so blocking I/O does not pin the event loop.
3. Detect rotation by comparing `os.stat(path).st_ino` to the cached
   inode. On a flip, drain remaining bytes from the old fd, close it,
   and reopen by path.
4. For each parsed JSON line carrying a `job_id`, append the raw line
   to `/logs/jobs/{job_id}.log` — the per-job aggregated log used by
   the zip / stream endpoints and removed on job-delete.
5. For each line whose `job_id` has at least one subscriber on
   `logs.{job_id}` (`hub.subscriber_count`), emit the line as a
   `log.line` event with `persist=False`.

Loop guard: records emitted by the WS hub itself (`extra.logger`
starting with `arm_backend.ws.hub`) are skipped before WS emit only —
they're still appended to the per-job file (file writes have no
feedback risk; the hub-emit-failure log is genuinely diagnostic).

Subscriber sees only future lines after subscribing. Earlier lines are
available via the `/api/logs/{job_id}` (NDJSON stream) and
`/api/logs/{job_id}.zip` endpoints, both backed by the per-job file.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arm_backend.ws.hub import WSHub

logger = logging.getLogger("arm_backend.log_tailer")


# 250 ms idle wait between drain rounds. Trade-off: shorter = less latency
# from line-write to WS push; longer = less CPU for an idle stack. At 4 Hz
# the worst-case live-tail delay is ~250 ms which is invisible to a human
# watching a log pane.
_TICK_INTERVAL_SECONDS = 0.25
# Hub topic the tailer publishes on. `{job_id}` is filled per-line.
_LOG_TOPIC_PREFIX = "logs."
# Loop-guard: records whose `extra.logger` starts with this prefix are
# emitted from the hub's own broadcast path. If the hub fails to send a
# log line and logs the failure, that failure record would otherwise
# feed back into the tailer.
_HUB_LOGGER_PREFIX = "arm_backend.ws.hub"


@dataclass
class _FileState:
    path: Path
    fd: IO[str]
    inode: int


class LogTailer:
    def __init__(self, hub: WSHub, log_dir: str = "/logs") -> None:
        self._hub = hub
        self._log_dir = Path(log_dir)
        # Per-job aggregated logs live under `<log_dir>/jobs/<job_id>.log`.
        # The dir itself is omitted from `_discover_files` because that
        # only globs `<log_dir>/*.log` (non-recursive); `os.scandir`
        # returns entries without descending.
        self._per_job_dir = self._log_dir / "jobs"
        self._stop = asyncio.Event()
        self._files: dict[Path, _FileState] = {}
        self._tick_interval = _TICK_INTERVAL_SECONDS

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        logger.info("log tailer starting: dir=%s", self._log_dir)
        try:
            while not self._stop.is_set():
                try:
                    await self.tick()
                except Exception as exc:  # never crash the loop
                    logger.exception("log tailer tick failed: %s", exc)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self._tick_interval)
                except asyncio.TimeoutError:
                    pass
        finally:
            self._close_all()
            logger.info("log tailer stopped")

    def _close_all(self) -> None:
        for state in self._files.values():
            try:
                state.fd.close()
            except Exception:
                pass
        self._files.clear()

    async def tick(self) -> None:
        """One drain round. Public for tests."""
        await self._discover_files()
        for path in list(self._files.keys()):
            await self._drain_file(path)

    async def _discover_files(self) -> None:
        if not self._log_dir.exists():
            return
        for entry in os.scandir(self._log_dir):
            if not entry.is_file():
                continue
            if not entry.name.endswith(".log"):
                continue
            path = Path(entry.path)
            if path in self._files:
                continue
            try:
                fd = open(path, "r", encoding="utf-8", errors="replace")
                # Start at end-of-file — only future lines are tailed. Past
                # lines are available via the grep + zip endpoints.
                fd.seek(0, os.SEEK_END)
                inode = os.fstat(fd.fileno()).st_ino
                self._files[path] = _FileState(path=path, fd=fd, inode=inode)
                logger.debug("tail opened path=%s inode=%d", path, inode)
            except OSError as exc:
                logger.warning("tail open failed path=%s err=%s", path, exc)

    async def _drain_file(self, path: Path) -> None:
        state = self._files.get(path)
        if state is None:
            return
        loop = asyncio.get_event_loop()
        # Drain until EOF (readline returns "").
        while True:
            line = await loop.run_in_executor(None, state.fd.readline)
            if not line:
                break
            await self._emit_line(line)

        # Detect rotation: stat the path; if inode changed the
        # RotatingFileHandler renamed the file and opened a new one.
        try:
            new_inode = os.stat(path).st_ino
        except FileNotFoundError:
            # File temporarily gone (rotation in progress). Keep old fd;
            # next tick will retry the stat.
            return
        if new_inode != state.inode:
            logger.debug("tail rotation detected path=%s old_inode=%d new_inode=%d", path, state.inode, new_inode)
            try:
                state.fd.close()
            except Exception:
                pass
            try:
                fd = open(path, "r", encoding="utf-8", errors="replace")
                # On a fresh post-rotation file, read from the start —
                # `RotatingFileHandler` opened the new file empty, so any
                # bytes already there are unread by us.
                inode = os.fstat(fd.fileno()).st_ino
                self._files[path] = _FileState(path=path, fd=fd, inode=inode)
            except OSError as exc:
                logger.warning("tail reopen failed path=%s err=%s", path, exc)
                self._files.pop(path, None)
                return
            # Drain the freshly-opened file in this same tick so a rotation
            # mid-burst doesn't lose a tick of latency on subscribers.
            new_state = self._files[path]
            while True:
                line = await loop.run_in_executor(None, new_state.fd.readline)
                if not line:
                    break
                await self._emit_line(line)

    async def _emit_line(self, raw: str) -> None:
        line = raw.strip()
        if not line:
            return
        try:
            record: dict[str, Any] = json.loads(line)
        except ValueError:
            return  # not our JSONL, ignore

        job_id = record.get("job_id")
        if not isinstance(job_id, str):
            return  # out-of-job-context line; nothing to fan out to

        # Per-job aggregated log — append before WS emit so the file is
        # the source of truth even if the hub fan-out fails.
        self._append_per_job_log(job_id, line)

        # Loop guard: don't re-emit hub's own emit-failure logs.
        extra = record.get("extra")
        if isinstance(extra, dict):
            src_logger = extra.get("logger")
            if isinstance(src_logger, str) and src_logger.startswith(_HUB_LOGGER_PREFIX):
                return

        topic = f"{_LOG_TOPIC_PREFIX}{job_id}"
        if self._hub.subscriber_count(topic) == 0:
            return

        track_id = record.get("track_id") if isinstance(record.get("track_id"), str) else None
        await self._hub.emit(
            topic=topic,
            event_type="log.line",
            payload=record,
            persist=False,
            job_id=job_id,
            track_id=track_id,
        )

    def _append_per_job_log(self, job_id: str, line: str) -> None:
        """Append `line` (without trailing newline) to the per-job file.

        Best-effort: a write failure logs a warning and drops the line.
        Open-append-close per call avoids fd pressure across many active
        jobs and survives file deletion (e.g. user deletes the job —
        next line opens a fresh empty file rather than racing the unlink).
        """
        try:
            self._per_job_dir.mkdir(parents=True, exist_ok=True)
            target = self._per_job_dir / f"{job_id}.log"
            with target.open("a", encoding="utf-8") as fh:
                fh.write(line)
                fh.write("\n")
        except OSError as exc:
            logger.warning("per-job log append failed job_id=%s err=%s", job_id, exc)
