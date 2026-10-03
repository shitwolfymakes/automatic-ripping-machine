"""DriveScanner.scan_once + .run loop: config tunables, error survival (spec §2)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend import drive_scanner as mod  # noqa: E402
from arm_backend.drive_scanner import DriveScanner  # noqa: E402
from arm_common import Config, DriveLifecycle  # noqa: E402

from tests._fakes import FakeSession, _table_for_stmt  # noqa: E402
from tests.test_drive_scanner_enumerate import Tree  # noqa: E402


def _db(interval: int = 30, prune: int = 7) -> FakeSession:
    db = FakeSession()
    db.rows["config"] = [Config(id=1, drive_scan_interval_seconds=interval, drive_detected_prune_days=prune)]
    return db


async def test_tunables_zero_value_is_not_treated_as_missing() -> None:
    """`x or DEFAULT` treats 0 as falsy and silently substitutes the default —
    an operator setting drive_scan_interval_seconds=0 (scan every tick, no
    wait) or drive_detected_prune_days=0 (prune immediately) would be
    ignored. `x if x is not None else DEFAULT` must honour an explicit 0."""
    db = _db(interval=0, prune=0)
    interval, prune = await mod._tunables(db)
    assert (interval, prune) == (0, 0)


async def test_scan_once_detects_and_uses_config_prune_days(tmp_path: Path) -> None:
    t = Tree(tmp_path)
    t.drive()
    db = _db(prune=1)
    scanner = DriveScanner(lambda: db, sysfs_root=t.sysfs, disk_root=t.disk)
    summary = await scanner.scan_once(db)
    assert summary.detected == 1
    [row] = db.rows["drives"]
    assert row.lifecycle is DriveLifecycle.DETECTED


async def test_scan_once_with_missing_config_uses_defaults(tmp_path: Path) -> None:
    t = Tree(tmp_path)
    t.drive()
    db = FakeSession()  # no config row
    scanner = DriveScanner(lambda: db, sysfs_root=t.sysfs, disk_root=t.disk)
    assert (await scanner.scan_once(db)).detected == 1


async def test_run_reads_interval_from_config_each_tick_and_survives_errors(monkeypatch, tmp_path: Path) -> None:
    t = Tree(tmp_path)
    t.drive()
    db = _db(interval=5)
    scanner = DriveScanner(lambda: db, sysfs_root=t.sysfs, disk_root=t.disk)
    sleeps: list[float] = []
    calls = {"n": 0}

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)
        if len(sleeps) == 3:
            raise asyncio.CancelledError

    async def flaky_scan(session):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")  # must be logged and swallowed
        return await DriveScanner.scan_once(scanner, session)

    monkeypatch.setattr(mod.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(scanner, "scan_once", flaky_scan)
    # change the interval mid-run: tick 3 must pick it up without a restart
    orig = fake_sleep

    async def sleep_then_retune(s: float) -> None:
        if len(sleeps) == 1:
            db.rows["config"][0].drive_scan_interval_seconds = 9
        await orig(s)

    monkeypatch.setattr(mod.asyncio, "sleep", sleep_then_retune)
    with pytest.raises(asyncio.CancelledError):
        await scanner.run()
    assert calls["n"] == 3
    # Ruling A: run() reads tunables BEFORE scanning, so a failed tick keeps
    # the configured cadence. tick1 reads 5, scans ok, sleep#1 appends 5;
    # tick2 reads 5, scan raises, sleep#2 retunes to 9 THEN appends 5;
    # tick3 reads 9, sleep#3 appends 9 and raises Cancelled.
    assert sleeps == [5, 5, 9]


async def test_concurrent_scan_once_calls_serialize_to_one_row(monkeypatch, tmp_path: Path) -> None:
    """POST /rescan and the background loop can call scan_once concurrently
    against the same session. Without a lock, both see an empty table via
    select(Drive) before either inserts, and each decides the drive is new —
    two rows for one physical drive. The scanner's own asyncio.Lock must
    serialize these so only one row is ever created.

    FakeSession.execute never actually suspends (no internal await), so two
    scan_once() coroutines under plain asyncio.gather wouldn't interleave
    even without a lock — the race wouldn't reproduce. Force a real
    scheduling point inside the (would-be) critical section so an absent
    lock provably lets both calls interleave past the read-then-insert race.
    """
    t = Tree(tmp_path)
    t.drive()
    db = _db()
    scanner = DriveScanner(lambda: db, sysfs_root=t.sysfs, disk_root=t.disk)

    # Patch db.execute to yield to the loop right after the select(Drive)
    # read at the top of reconcile_drives, so a second overlapping call gets
    # a real chance to run its own read — and, without the lock, its own
    # insert — before the first call proceeds to insert.
    real_execute = db.execute

    async def _execute_yield_after_drive_select(stmt, *args, **kwargs):
        result = await real_execute(stmt, *args, **kwargs)
        if _table_for_stmt(stmt) == "drives":
            await asyncio.sleep(0)
        return result

    monkeypatch.setattr(db, "execute", _execute_yield_after_drive_select)
    await asyncio.gather(scanner.scan_once(db), scanner.scan_once(db))
    assert len(db.rows["drives"]) == 1


async def test_run_propagates_cancellederror_raised_inside_the_scan(monkeypatch, tmp_path: Path) -> None:
    """A CancelledError raised from inside the try block (task cancelled
    mid-scan, not mid-sleep) must propagate immediately, not be swallowed by
    the generic `except Exception` below it."""
    t = Tree(tmp_path)
    t.drive()
    db = _db(interval=5)
    scanner = DriveScanner(lambda: db, sysfs_root=t.sysfs, disk_root=t.disk)

    async def cancelled_scan(session):
        raise asyncio.CancelledError

    monkeypatch.setattr(scanner, "scan_once", cancelled_scan)
    with pytest.raises(asyncio.CancelledError):
        await scanner.run()
