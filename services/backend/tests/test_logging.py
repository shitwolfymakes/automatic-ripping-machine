"""Phase 12 — `arm_common.logging` shape, contextvar propagation, override semantics.

The helper lives in `arm_common`; tests for it live here because the
arm_common workspace package has no `tests/` directory and pytest's
`testpaths` only picks up `services/*/tests/`.

Each test calls `configure_service_logging(name, log_dir=tmp_path)` so
the rotating file handler writes into a pytest-managed directory; we
then read the file back and `json.loads` every line.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
from pathlib import Path

import pytest

from arm_common import configure_service_logging, with_log_context
from arm_common.logging import QUIET_LOGGERS, JsonFormatter, log_event

REQUIRED_KEYS = {
    "ts",
    "level",
    "service",
    "logger",
    "job_id",
    "track_id",
    "session_application_id",
    "event",
    "msg",
    "fields",
    "exc",
}


def _read_log_file(tmp_path: Path, service: str) -> list[dict[str, object]]:
    text = (tmp_path / f"{service}.log").read_text(encoding="utf-8")
    out: list[dict[str, object]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        out.append(json.loads(line))
    return out


def test_emitted_lines_are_valid_json_with_required_fields(tmp_path: Path) -> None:
    configure_service_logging("test-svc", log_dir=str(tmp_path))
    logger = logging.getLogger("arm_common.tests.shape")
    logger.info("hello %s", "world")
    logger.warning("uhoh")

    rows = _read_log_file(tmp_path, "test-svc")
    assert len(rows) >= 2
    for row in rows:
        assert set(row) == REQUIRED_KEYS
        assert isinstance(row["fields"], dict)
        assert row["service"] == "test-svc"


def test_with_log_context_populates_then_restores(tmp_path: Path) -> None:
    configure_service_logging("test-svc", log_dir=str(tmp_path))
    logger = logging.getLogger("arm_common.tests.ctx")

    logger.info("outside")
    with with_log_context(job_id="job_01JZXR7K3M5Q8N4VWA00000001"):
        logger.info("inside")
    logger.info("after")

    rows = _read_log_file(tmp_path, "test-svc")
    msgs = {row["msg"]: row for row in rows}
    assert msgs["outside"]["job_id"] is None
    assert msgs["inside"]["job_id"] == "job_01JZXR7K3M5Q8N4VWA00000001"
    assert msgs["after"]["job_id"] is None


def test_nested_context_restores_outer(tmp_path: Path) -> None:
    configure_service_logging("test-svc", log_dir=str(tmp_path))
    logger = logging.getLogger("arm_common.tests.nested")

    with with_log_context(job_id="outer"):
        logger.info("a")
        with with_log_context(job_id="inner"):
            logger.info("b")
        logger.info("c")

    rows = _read_log_file(tmp_path, "test-svc")
    msgs = {row["msg"]: row for row in rows}
    assert msgs["a"]["job_id"] == "outer"
    assert msgs["b"]["job_id"] == "inner"
    assert msgs["c"]["job_id"] == "outer"


def test_explicit_extra_overrides_contextvar(tmp_path: Path) -> None:
    configure_service_logging("test-svc", log_dir=str(tmp_path))
    logger = logging.getLogger("arm_common.tests.override")

    with with_log_context(job_id="ambient"):
        logger.info("via-extra", extra={"job_id": "explicit"})

    rows = _read_log_file(tmp_path, "test-svc")
    via_extra = next(r for r in rows if r["msg"] == "via-extra")
    assert via_extra["job_id"] == "explicit"


def test_context_propagates_across_create_task(tmp_path: Path) -> None:
    configure_service_logging("test-svc", log_dir=str(tmp_path))
    logger = logging.getLogger("arm_common.tests.task")

    async def child() -> None:
        # Inherits the parent task's context — `asyncio.create_task` copies
        # the current context by design.
        logger.info("from-child")

    async def main() -> None:
        with with_log_context(job_id="task_job"):
            await asyncio.create_task(child())

    asyncio.run(main())
    rows = _read_log_file(tmp_path, "test-svc")
    child_row = next(r for r in rows if r["msg"] == "from-child")
    assert child_row["job_id"] == "task_job"


def test_run_in_executor_does_not_inherit_without_copy_context(tmp_path: Path) -> None:
    """Documents the gotcha: `loop.run_in_executor` does NOT copy ctx by default.

    Wrap with `contextvars.copy_context().run(...)` at the executor
    boundary if a worker thread needs the contextvars set.
    """
    configure_service_logging("test-svc", log_dir=str(tmp_path))
    logger = logging.getLogger("arm_common.tests.executor")

    def worker_no_copy() -> None:
        logger.info("worker-no-copy")

    def worker_with_copy() -> None:
        logger.info("worker-with-copy")

    async def main() -> None:
        loop = asyncio.get_event_loop()
        with with_log_context(job_id="exec_job"):
            await loop.run_in_executor(None, worker_no_copy)
            ctx = contextvars.copy_context()
            await loop.run_in_executor(None, ctx.run, worker_with_copy)

    asyncio.run(main())
    rows = _read_log_file(tmp_path, "test-svc")
    no_copy = next(r for r in rows if r["msg"] == "worker-no-copy")
    with_copy = next(r for r in rows if r["msg"] == "worker-with-copy")
    assert no_copy["job_id"] is None
    assert with_copy["job_id"] == "exec_job"


def test_logger_name_is_a_top_level_key(tmp_path: Path) -> None:
    """Loop-guard depends on `logger` reflecting `record.name`."""
    configure_service_logging("test-svc", log_dir=str(tmp_path))
    logging.getLogger("arm_common.tests.loop_guard").info("named")

    rows = _read_log_file(tmp_path, "test-svc")
    named = next(r for r in rows if r["msg"] == "named")
    assert named["logger"] == "arm_common.tests.loop_guard"


def test_exception_info_is_formatted_into_exc(tmp_path: Path) -> None:
    """A record logged with `exc_info` carries the formatted traceback in top-level `exc`."""
    configure_service_logging("test-svc", log_dir=str(tmp_path))
    logger = logging.getLogger("arm_common.tests.exc")

    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("it failed")

    rows = _read_log_file(tmp_path, "test-svc")
    failed = next(r for r in rows if r["msg"] == "it failed")
    exc = failed["exc"]
    assert isinstance(exc, str)
    assert "ValueError: boom" in exc
    assert "Traceback" in exc
    assert "exc" not in failed["fields"]


def _format(record: logging.LogRecord) -> dict[str, object]:
    return json.loads(JsonFormatter("svc").format(record))


def _record(msg: str = "m", exc_info: object = None, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("lg", logging.INFO, __file__, 1, msg, None, exc_info)  # type: ignore[arg-type]
    record.__dict__.update(extra)
    return record


def test_plain_line_has_the_full_schema() -> None:
    row = _format(_record())
    assert set(row) == REQUIRED_KEYS
    assert row["event"] is None
    assert row["fields"] == {}
    assert row["exc"] is None
    assert row["logger"] == "lg"


def test_log_event_sets_event_and_fields(caplog: pytest.LogCaptureFixture) -> None:
    lg = logging.getLogger("arm_common.tests.event")
    with caplog.at_level(logging.INFO, logger=lg.name):
        log_event(lg, "track.ripped", "track 1/19 ripped", track_index=1, size_bytes=5)
    row = _format(caplog.records[-1])
    assert row["event"] == "track.ripped"
    assert row["fields"] == {"track_index": 1, "size_bytes": 5}
    assert row["msg"] == "track 1/19 ripped"
    assert row["level"] == "info"


def test_log_event_honours_level(caplog: pytest.LogCaptureFixture) -> None:
    lg = logging.getLogger("arm_common.tests.event_level")
    with caplog.at_level(logging.DEBUG, logger=lg.name):
        log_event(lg, "x.y", "m", level=logging.WARNING)
    assert _format(caplog.records[-1])["level"] == "warning"


def test_extra_keys_land_in_fields_and_ids_stay_top_level() -> None:
    row = _format(_record(job_id="job_1", foo=1))
    assert row["job_id"] == "job_1"
    assert row["fields"] == {"foo": 1}


def test_unserialisable_field_value_is_stringified(caplog: pytest.LogCaptureFixture) -> None:
    lg = logging.getLogger("arm_common.tests.stringify")
    with caplog.at_level(logging.INFO, logger=lg.name):
        log_event(lg, "a.b", "m", path=Path("/x"))
    assert _format(caplog.records[-1])["fields"] == {"path": "/x"}


def test_caller_extra_named_like_a_schema_key_goes_to_fields(caplog: pytest.LogCaptureFixture) -> None:
    lg = logging.getLogger("arm_common.tests.schema_names")
    with caplog.at_level(logging.INFO, logger=lg.name):
        lg.info("real msg", extra={"msg_note": 1})
        row = _format(caplog.records[-1])
        log_event(lg, "a.b", "m2", event_hint="x")
        row2 = _format(caplog.records[-1])
    assert row["msg"] == "real msg"
    assert row["fields"] == {"msg_note": 1}
    assert row2["event"] == "a.b"
    assert row2["fields"] == {"event_hint": "x"}


@pytest.mark.parametrize("name", QUIET_LOGGERS)
def test_quiet_loggers_raised_at_info(tmp_path: Path, name: str) -> None:
    configure_service_logging("s", str(tmp_path), "info")
    assert logging.getLogger(name).level == logging.WARNING


@pytest.mark.parametrize("name", QUIET_LOGGERS)
def test_quiet_loggers_untouched_at_debug(tmp_path: Path, name: str) -> None:
    logging.getLogger(name).setLevel(logging.WARNING)
    configure_service_logging("s", str(tmp_path), "debug")
    assert logging.getLogger(name).level == logging.NOTSET


def test_unusable_log_dir_falls_back_to_stdout_only(tmp_path: Path) -> None:
    """When the log dir can't be created, no file handler is installed and nothing raises."""
    blocker = tmp_path / "afile"
    blocker.write_text("not a directory", encoding="utf-8")

    configure_service_logging("test-svc", log_dir=str(blocker / "logs"))

    handlers = logging.getLogger().handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0], logging.StreamHandler)
    assert not isinstance(handlers[0], logging.FileHandler)
    assert not (tmp_path / "test-svc.log").exists()
    assert not (blocker / "logs").exists()

