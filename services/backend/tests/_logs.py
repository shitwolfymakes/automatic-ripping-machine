"""Capture of the job-log lines a test emits, formatted at emit time as a real handler would."""

from __future__ import annotations

import json
import logging
from typing import Any

from arm_common.logging import JsonFormatter


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
