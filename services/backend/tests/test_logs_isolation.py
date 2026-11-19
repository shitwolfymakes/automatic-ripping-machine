"""Every backend test starts from the logging state the one before it found."""

from __future__ import annotations

import logging

from arm_common.logging import QUIET_LOGGERS
from tests._logs import restored_logging_state


class _Tracked(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - never emits here
        pass

    def close(self) -> None:
        self.closed = True
        super().close()


def test_root_level_handlers_and_quiet_levels_are_restored() -> None:
    root = logging.getLogger()
    level, handlers = root.level, list(root.handlers)
    quiet = {name: logging.getLogger(name).level for name in QUIET_LOGGERS}
    added = _Tracked()

    with restored_logging_state():
        root.setLevel(logging.DEBUG)
        root.addHandler(added)
        for kept in handlers:
            root.removeHandler(kept)
        for name in QUIET_LOGGERS:
            logging.getLogger(name).setLevel(logging.CRITICAL)

    assert root.level == level and root.handlers == handlers
    assert {name: logging.getLogger(name).level for name in QUIET_LOGGERS} == quiet
    assert added.closed


def test_a_handler_that_fails_to_close_is_still_removed() -> None:
    class _Stuck(_Tracked):
        def close(self) -> None:
            raise OSError("stream gone")

    root = logging.getLogger()
    stuck = _Stuck()
    with restored_logging_state():
        root.addHandler(stuck)
    assert stuck not in root.handlers
