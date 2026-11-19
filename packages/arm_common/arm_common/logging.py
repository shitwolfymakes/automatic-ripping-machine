"""Structured JSONL logging shared by every v3 service.

`configure_service_logging(service_name)` is what each service's `main.py`
calls in place of `logging.basicConfig`. It installs a single
`JsonFormatter` on two handlers — `StreamHandler(stdout)` (so `docker logs`
keeps working) and `RotatingFileHandler(/logs/<service>.log, 10 MB × 5)`
which is what the backend's `LogTailer` and zip endpoint read from.

`with_log_context(job_id=..., track_id=..., session_application_id=...)`
pushes correlation IDs onto contextvars; the formatter reads them back on
every emitted record. asyncio + contextvars propagate across `await` and
`asyncio.create_task` automatically. **Caveat:** `loop.run_in_executor`
does NOT copy the current context — wrap with
`contextvars.copy_context().run(...)` at the executor boundary.

Explicit `extra={"job_id": ...}` on a single call site overrides the
ambient contextvar (record `__dict__` wins).

Every line carries exactly `{ts, level, service, logger, job_id, track_id,
session_application_id, event, msg, fields, exc}`. `event` is a stable dotted
name set by `log_event` (null on plain lines), `fields` holds the structured
values of that event plus any other caller `extra=`, and `exc` is the
formatted traceback or null.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from collections.abc import Iterator

# `_RESERVED_LOGRECORD_KEYS` are the names `logging` already populates on
# every LogRecord, plus the keys the line schema owns; anything matching is
# *not* a free-form `extra=` value. Everything else goes into `fields`.
_RESERVED_LOGRECORD_KEYS: frozenset[str] = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
        "message",
        # Schema keys carried on the record, promoted to top-level line keys.
        "event",
        "fields",
        "job_id",
        "track_id",
        "session_application_id",
    }
)


# Chatty third-party loggers held at WARNING while the root level is INFO or above.
QUIET_LOGGERS: tuple[str, ...] = ("httpx", "httpcore", "uvicorn.access")

_job_id: ContextVar[str | None] = ContextVar("arm_log_job_id", default=None)
_track_id: ContextVar[str | None] = ContextVar("arm_log_track_id", default=None)
_session_application_id: ContextVar[str | None] = ContextVar("arm_log_session_application_id", default=None)


def _correlation_ids(record: logging.LogRecord) -> dict[str, str | None]:
    """The job/track/session-application ids for this record.

    An explicit `extra=` value wins over the ambient context.
    """
    # `extra={"job_id": ...}` lands as `record.job_id`. Explicit overrides
    # the ambient contextvar — single call sites win against ambient state.
    return {
        "job_id": getattr(record, "job_id", None) or _job_id.get(),
        "track_id": getattr(record, "track_id", None) or _track_id.get(),
        "session_application_id": getattr(record, "session_application_id", None) or _session_application_id.get(),
    }


def _fields(record: logging.LogRecord) -> dict[str, Any]:
    """The structured fields of this record: caller `extra=` values merged with `log_event`'s `fields`."""
    fields: dict[str, Any] = {
        k: v for k, v in record.__dict__.items() if k not in _RESERVED_LOGRECORD_KEYS and not k.startswith("_")
    }
    fields.update(getattr(record, "fields", None) or {})
    return fields


class JsonFormatter(logging.Formatter):
    """Serialise a `LogRecord` as one JSON line per the v3 logging schema."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "service": self._service,
            "logger": record.name,
            **_correlation_ids(record),
            "event": getattr(record, "event", None),
            "msg": record.getMessage(),
            "fields": _fields(record),
            "exc": self.formatException(record.exc_info) if record.exc_info else None,
        }
        return json.dumps(line, default=str)


def log_event(
    logger: logging.Logger, event: str, message: str, /, *, level: int = logging.INFO, **fields: object
) -> None:
    """Log `message` as the named `event`, carrying `fields` as the line's structured values."""
    logger.log(level, message, extra={"event": event, "fields": fields})


def _build_file_handler(log_dir: str, service_name: str, formatter: logging.Formatter) -> logging.Handler | None:
    """The rotating `<service>.log` handler under `log_dir`, or None when the directory can't be created or opened."""
    # File handler is best-effort. Inside a container `/logs` is the
    # bind-mounted shared volume; outside (CI / dev shell / openapi
    # snapshot regen) it may not exist or not be writable. Drop the
    # file handler in that case rather than failing import — stdout
    # still carries every line.
    log_path = Path(log_dir)
    try:
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path / f"{service_name}.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
    except OSError:
        return None
    file_handler.setFormatter(formatter)
    return file_handler


def _apply_quiet_loggers(root_level: int) -> None:
    """Hold `QUIET_LOGGERS` at WARNING while the root level is INFO or above; otherwise inherit the root level."""
    quiet_level = logging.WARNING if root_level >= logging.INFO else logging.NOTSET
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(quiet_level)


def configure_service_logging(service_name: str, log_dir: str = "/logs", level: str = "info") -> None:
    """Install JSONL logging on the root logger for one service.

    Replaces any handlers a previous `logging.basicConfig` might have left
    behind (some libraries call it on import). Idempotent.

    `log_dir` is created if missing — defaults to `/logs`, the bind-mount
    every container has. Tests pass a `tmp_path` here.
    """
    formatter = JsonFormatter(service_name)
    root = logging.getLogger()
    root.setLevel(level.upper())
    _apply_quiet_loggers(root.level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)

    file_handler = _build_file_handler(log_dir, service_name, formatter)
    if file_handler is not None:
        root.addHandler(file_handler)


@contextmanager
def with_log_context(
    *,
    job_id: str | None = None,
    track_id: str | None = None,
    session_application_id: str | None = None,
) -> Iterator[None]:
    """Push job/track/session correlation IDs for the duration of the block.

    Each kwarg, when not None, is set on its ContextVar; on exit, the
    ContextVar is `.reset()` to its prior token. Nesting restores the
    outer value correctly. Passing `None` for a key leaves the existing
    value (ambient or prior nested) untouched.
    """
    tokens: list[tuple[ContextVar[str | None], Token[str | None]]] = []
    if job_id is not None:
        tokens.append((_job_id, _job_id.set(job_id)))
    if track_id is not None:
        tokens.append((_track_id, _track_id.set(track_id)))
    if session_application_id is not None:
        tokens.append((_session_application_id, _session_application_id.set(session_application_id)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)
