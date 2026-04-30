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

REQUIRED_KEYS = {
    "ts",
    "level",
    "service",
    "job_id",
    "track_id",
    "session_application_id",
    "msg",
    "extra",
}


def _read_log_file(tmp_path: Path, service: str) -> list[dict[str, object]]:
    text = (tmp_path / f"{service}.log").read_text(encoding="utf-8")
    out: list[dict[str, object]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        out.append(json.loads(line))
    return out


@pytest.fixture(autouse=True)
def reset_root_logger() -> None:
    yield
    root = logging.getLogger()
    for h in list(root.handlers):
        try:
            h.close()
        except Exception:
            pass
        root.removeHandler(h)


def test_emitted_lines_are_valid_json_with_required_fields(tmp_path: Path) -> None:
    configure_service_logging("test-svc", log_dir=str(tmp_path))
    logger = logging.getLogger("arm_common.tests.shape")
    logger.info("hello %s", "world")
    logger.warning("uhoh")

    rows = _read_log_file(tmp_path, "test-svc")
    assert len(rows) >= 2
    for row in rows:
        assert REQUIRED_KEYS.issubset(row.keys())
        assert isinstance(row["extra"], dict)
        assert row["service"] == "test-svc"


def test_with_log_context_populates_then_restores(tmp_path: Path) -> None:
    configure_service_logging("test-svc", log_dir=str(tmp_path))
    logger = logging.getLogger("arm_common.tests.ctx")

    logger.info("outside")
    with with_log_context(job_id="job_x"):
        logger.info("inside")
    logger.info("after")

    rows = _read_log_file(tmp_path, "test-svc")
    msgs = {row["msg"]: row for row in rows}
    assert msgs["outside"]["job_id"] is None
    assert msgs["inside"]["job_id"] == "job_x"
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


def test_logger_name_appears_in_extra(tmp_path: Path) -> None:
    """Loop-guard depends on `extra.logger` reflecting `record.name`."""
    configure_service_logging("test-svc", log_dir=str(tmp_path))
    logger = logging.getLogger("arm_common.tests.loop_guard")

    logger.info("named")

    rows = _read_log_file(tmp_path, "test-svc")
    named = next(r for r in rows if r["msg"] == "named")
    extra = named["extra"]
    assert isinstance(extra, dict)
    assert extra.get("logger") == "arm_common.tests.loop_guard"
