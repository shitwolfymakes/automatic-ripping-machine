"""Milestone logs that never raise into the work that reached the milestone."""

from __future__ import annotations

from arm_backend.log_safely import log_safely, log_safely_sync
from tests._logs import LineCapture


async def test_log_safely_logs_a_failed_milestone_instead_of_raising(job_log: LineCapture) -> None:
    async def _broken() -> None:
        raise RuntimeError("db gone")

    await log_safely("transcode.started", _broken())
    (line,) = job_log.lines(level="error")
    assert line["msg"] == "could not log the transcode.started milestone" and "db gone" in line["exc"]


async def test_log_safely_runs_the_work() -> None:
    ran: list[bool] = []

    async def _work() -> None:
        ran.append(True)

    await log_safely("transcode.started", _work())
    assert ran == [True]


def test_log_safely_sync_logs_a_failed_milestone_instead_of_raising(job_log: LineCapture) -> None:
    def _broken(_job: str) -> None:
        raise RuntimeError("log bug")

    log_safely_sync("rip.completed", _broken, "job_1")
    (line,) = job_log.lines(level="error")
    assert line["msg"] == "could not log the rip.completed milestone" and "log bug" in line["exc"]


def test_log_safely_sync_passes_its_arguments_to_the_work() -> None:
    calls: list[tuple[str, int]] = []

    def _work(job: str, *, done: int) -> None:
        calls.append((job, done))

    log_safely_sync("rip.completed", _work, "job_1", done=3)
    assert calls == [("job_1", 3)]
