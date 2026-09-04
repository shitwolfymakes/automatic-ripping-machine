from __future__ import annotations

import logging
import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend.ripper_manager import ReconcileSummary, RipperManagerError, reconcile_enrolled_rippers  # noqa: E402
from arm_common import DiscType, Drive, DriveLifecycle, DriveStatus, Job, JobStatus  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


class _StubManager:
    def __init__(self, summary: ReconcileSummary | Exception) -> None:
        self._summary = summary
        self.seen: list[list[str]] = []
        self.busy: frozenset[str] = frozenset()

    def reconcile(self, enrolled, *, busy=frozenset()):  # sync, like the real one (runs under to_thread)
        self.seen.append([d.id for d in enrolled])
        self.busy = busy
        if isinstance(self._summary, Exception):
            raise self._summary
        return self._summary


def _row(drive_id: str, lifecycle: DriveLifecycle, last_error: str | None = None) -> Drive:
    return Drive(
        id=drive_id,
        hostname=f"scan-{drive_id}",
        device_path="/dev/sr0",
        status=DriveStatus.ONLINE,
        lifecycle=lifecycle,
        last_error=last_error,
    )


def _factory(db: FakeSession):
    def make() -> FakeSession:
        return db

    return make


@pytest.mark.asyncio
async def test_boot_reconcile_passes_only_enrolled_rows_and_writes_last_error() -> None:
    db = FakeSession()
    ok = _row("drv_ok", DriveLifecycle.ENROLLED, last_error="stale error from last boot")
    bad = _row("drv_bad", DriveLifecycle.ENROLLED)
    detected = _row("drv_det", DriveLifecycle.DETECTED, last_error="untouched")
    error_row = _row("drv_err", DriveLifecycle.ENROLLED, last_error="identity mismatch: row is bound to A but B")
    error_row.status = DriveStatus.ERROR
    db.rows["drives"] = [ok, bad, detected, error_row]
    manager = _StubManager(ReconcileSummary(adopted=["drv_ok", "drv_err"], failed={"drv_bad": "ImageNotFound: nope"}))

    summary = await reconcile_enrolled_rippers(manager, _factory(db))  # type: ignore[arg-type]

    assert summary is not None and summary.adopted == ["drv_ok", "drv_err"]
    assert manager.seen == [["drv_ok", "drv_bad", "drv_err"]]
    assert ok.last_error is None  # success clears a stale error
    assert bad.last_error == "ImageNotFound: nope"
    assert detected.last_error == "untouched"
    # B2: an ENROLLED row sitting in ERROR (e.g. a register-time identity
    # mismatch) that reconcile successfully adopts keeps its diagnostic
    # reason — reconcile succeeding at the docker level doesn't mean the
    # identity problem is fixed; only a fresh register (or a fixed
    # enrollment) clears it.
    assert error_row.last_error == "identity mismatch: row is bound to A but B"
    assert db.committed >= 1


@pytest.mark.asyncio
async def test_boot_reconcile_logs_and_returns_none_when_the_daemon_is_unlistable(caplog) -> None:
    db = FakeSession()
    db.rows["drives"] = [_row("drv_ok", DriveLifecycle.ENROLLED)]
    manager = _StubManager(RipperManagerError("DockerException: no socket"))
    with caplog.at_level(logging.ERROR, logger="arm_backend.ripper_manager"):
        assert await reconcile_enrolled_rippers(manager, _factory(db)) is None  # type: ignore[arg-type]
    assert "no socket" in caplog.text


@pytest.mark.asyncio
async def test_boot_reconcile_passes_ripping_drives_as_busy() -> None:
    db = FakeSession()
    db.rows["drives"] = [_row("drv_a", DriveLifecycle.ENROLLED), _row("drv_b", DriveLifecycle.ENROLLED)]
    db.rows["jobs"] = [
        Job(id="job_1", drive_id="drv_a", status=JobStatus.RIPPING, disc_type=DiscType.DVD),
        Job(id="job_2", drive_id="drv_b", status=JobStatus.RIPPED, disc_type=DiscType.DVD),
    ]
    manager = _StubManager(ReconcileSummary(adopted=["drv_a", "drv_b"]))
    await reconcile_enrolled_rippers(manager, _factory(db))  # type: ignore[arg-type]
    assert manager.busy == frozenset({"drv_a"})
