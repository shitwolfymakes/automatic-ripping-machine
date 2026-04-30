"""Phase 12 — structured JSONL logging shared by every v3 service.

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

JSONL shape pinned by `docs/arch/05-cross-cutting.md § Logging`:
`{ts, level, service, job_id, track_id, session_application_id, msg, extra}`.
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
# every LogRecord; anything matching is *not* an `extra=` arg the caller
# passed in. We strip these before dumping `record.__dict__` into the
# `extra` field of the JSON line.
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
        # Our own correlation keys — promoted to top-level fields, not in `extra`.
        "job_id",
        "track_id",
        "session_application_id",
    }
)


_job_id: ContextVar[str | None] = ContextVar("arm_log_job_id", default=None)
_track_id: ContextVar[str | None] = ContextVar("arm_log_track_id", default=None)
_session_application_id: ContextVar[str | None] = ContextVar("arm_log_session_application_id", default=None)


class JsonFormatter(logging.Formatter):
    """Serialise a `LogRecord` as one JSON line per the v3 logging schema."""

    def __init__(self, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        # `extra={"job_id": ...}` lands as `record.job_id`. Explicit overrides
        # the ambient contextvar — single call sites win against ambient state.
        job_id = getattr(record, "job_id", None) or _job_id.get()
        track_id = getattr(record, "track_id", None) or _track_id.get()
        sap_id = getattr(record, "session_application_id", None) or _session_application_id.get()

        extra: dict[str, Any] = {
            k: v for k, v in record.__dict__.items() if k not in _RESERVED_LOGRECORD_KEYS and not k.startswith("_")
        }
        # Stamp the source logger name so the LogTailer can self-filter records
        # emitted from the WS hub during fan-out (loop guard).
        extra.setdefault("logger", record.name)

        line: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "service": self._service,
            "job_id": job_id,
            "track_id": track_id,
            "session_application_id": sap_id,
            "msg": record.getMessage(),
            "extra": extra,
        }
        if record.exc_info:
            line["extra"]["exc"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str)


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
    for handler in list(root.handlers):
        root.removeHandler(handler)

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)

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
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        pass


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
