"""Capture of the job-log lines a test emits, formatted at emit time as a real handler would."""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Iterator
from typing import Any

from arm_common.logging import QUIET_LOGGERS, JsonFormatter

# Loggers whose level service logging setup (and uvicorn's) changes.
_LEVELLED_LOGGERS = (*QUIET_LOGGERS, "uvicorn.asgi")


class LineCapture(logging.Handler):
    """Collects each record as its formatted job-log line, so the ambient job context is read at emit time."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.setFormatter(JsonFormatter("test"))
        self._lines: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self._lines.append(json.loads(self.format(record)))

    def lines(
        self, *, event: str | None = None, logger_prefix: str | None = None, level: str | None = None
    ) -> list[dict[str, Any]]:
        """The captured lines, narrowed to an event, a logger-name prefix and/or a level."""
        return [
            line
            for line in self._lines
            if (event is None or line["event"] == event)
            and (logger_prefix is None or line["logger"].startswith(logger_prefix))
            and (level is None or line["level"] == level)
        ]

    def events(self, *names: str) -> list[str]:
        """In order, the captured lines' events (a line without one counts by its message), kept to `names`."""
        return [name for line in self._lines if (name := line["event"] or line["msg"]) in names]


def log_commits(db: Any) -> None:
    """Make each successful commit on `db` emit a `commit` line, so a test can place log lines around it."""
    commit = db.commit

    async def _commit() -> None:
        await commit()
        logging.getLogger("tests.commit").info("commit")

    db.commit = _commit


@contextlib.contextmanager
def restored_logging_state() -> Iterator[None]:
    """Put back the root logger's level and handlers and the service-set logger levels on exit.

    Handlers added inside are closed and removed, so none outlives the test that added it.
    """
    root = logging.getLogger()
    level, handlers = root.level, list(root.handlers)
    levels = {name: logging.getLogger(name).level for name in _LEVELLED_LOGGERS}
    try:
        yield
    finally:
        for added in [h for h in root.handlers if h not in handlers]:
            _close_quietly(added)
        root.handlers[:] = handlers
        root.setLevel(level)
        for name, saved in levels.items():
            logging.getLogger(name).setLevel(saved)


def _close_quietly(handler: logging.Handler) -> None:
    with contextlib.suppress(Exception):
        handler.close()
