"""Per-principal topic authorization.

Uses a hand-rolled fake AsyncSession that satisfies the few `select(...)`
calls the authz module makes — no real DB. Avoids the Phase 3 JSONB
limitation that blocks in-memory SQLite.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

from arm_backend.ws.authz import can_publish, can_subscribe  # noqa: E402
from arm_backend.ws.principal import ServicePrincipal, UIPrincipal  # noqa: E402
from arm_common import DiscType, Drive, DriveStatus, Job, JobStatus  # noqa: E402


class _FakeResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _FakeSession:
    """Returns the row indexed by the literal id baked into the SELECT.

    Both `select(...).where(col(X.id) == "drv_A")` paths render to the
    same shape: `WHERE <table>.id = 'drv_A'`. We yank the quoted id and
    use it as a dict key.
    """

    def __init__(self, drives: dict[str, Drive], jobs: dict[str, Job]) -> None:
        self._drives = drives
        self._jobs = jobs

    async def execute(self, stmt: Any) -> _FakeResult:
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        sql = str(compiled)
        if "FROM drives" in sql:
            return _FakeResult(self._drives.get(_extract_id(sql)))
        if "FROM jobs" in sql:
            return _FakeResult(self._jobs.get(_extract_id(sql)))
        return _FakeResult(None)


def _extract_id(sql: str) -> str | None:
    import re

    m = re.search(r"\.id = '([^']+)'", sql)
    return m.group(1) if m else None


@pytest.fixture
def session() -> Any:
    drive_a = Drive(id="drv_A", hostname="arm-ripper-A", device_path="/dev/sr0", status=DriveStatus.ONLINE)
    drive_b = Drive(id="drv_B", hostname="arm-ripper-B", device_path="/dev/sr1", status=DriveStatus.ONLINE)
    job_a = Job(id="job_A", drive_id="drv_A", disc_type=DiscType.DVD, status=JobStatus.RIPPING)
    job_b = Job(id="job_B", drive_id="drv_B", disc_type=DiscType.DVD, status=JobStatus.RIPPING)
    return _FakeSession(
        drives={"drv_A": drive_a, "drv_B": drive_b},
        jobs={"job_A": job_a, "job_B": job_b},
    )


async def test_ripper_can_subscribe_own_command_topic(session: Any) -> None:
    p = ServicePrincipal(kind="ripper", hostname="arm-ripper-A")
    assert await can_subscribe(p, "ripper.commands.drv_A", session) is True


async def test_ripper_cannot_subscribe_other_drives_command_topic(session: Any) -> None:
    p = ServicePrincipal(kind="ripper", hostname="arm-ripper-A")
    assert await can_subscribe(p, "ripper.commands.drv_B", session) is False


async def test_ripper_cannot_subscribe_ui_topics(session: Any) -> None:
    p = ServicePrincipal(kind="ripper", hostname="arm-ripper-A")
    assert await can_subscribe(p, "ripper.events", session) is False
    assert await can_subscribe(p, "ripper.progress.job_A", session) is False
    assert await can_subscribe(p, "system.events", session) is False


async def test_ripper_cannot_subscribe_to_unknown_drive(session: Any) -> None:
    p = ServicePrincipal(kind="ripper", hostname="arm-ripper-A")
    assert await can_subscribe(p, "ripper.commands.drv_NOPE", session) is False


async def test_ui_can_subscribe_to_ui_topics(session: Any) -> None:
    ui = UIPrincipal(user_id="u_1", username="admin")
    assert await can_subscribe(ui, "ripper.events", session) is True
    assert await can_subscribe(ui, "ripper.progress.job_A", session) is True
    assert await can_subscribe(ui, "transcode.events", session) is True
    assert await can_subscribe(ui, "system.events", session) is True
    assert await can_subscribe(ui, "logs.job_A", session) is True


async def test_ui_cannot_subscribe_to_command_topics(session: Any) -> None:
    ui = UIPrincipal(user_id="u_1", username="admin")
    assert await can_subscribe(ui, "ripper.commands.drv_A", session) is False
    assert await can_subscribe(ui, "transcoder.commands.tsk_1", session) is False


async def test_ripper_can_publish_progress_for_own_job(session: Any) -> None:
    p = ServicePrincipal(kind="ripper", hostname="arm-ripper-A")
    assert await can_publish(p, "ripper.progress.job_A", session) is True


async def test_ripper_cannot_publish_progress_for_other_drives_job(session: Any) -> None:
    p = ServicePrincipal(kind="ripper", hostname="arm-ripper-A")
    assert await can_publish(p, "ripper.progress.job_B", session) is False


async def test_ripper_cannot_publish_to_ripper_events(session: Any) -> None:
    """Typed events are emitted by the backend in-process, not by rippers."""
    p = ServicePrincipal(kind="ripper", hostname="arm-ripper-A")
    assert await can_publish(p, "ripper.events", session) is False


async def test_ui_cannot_publish_anywhere(session: Any) -> None:
    ui = UIPrincipal(user_id="u_1", username="admin")
    assert await can_publish(ui, "ripper.progress.job_A", session) is False
    assert await can_publish(ui, "ripper.events", session) is False
