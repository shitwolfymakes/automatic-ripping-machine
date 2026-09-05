from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.drive_scanner import ScannedDrive, ScanSummary, reconcile_drives  # noqa: E402
from arm_common import Drive, DriveIdentityKind, DriveLifecycle, DriveStatus  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
BY_ID = "usb-PIONEER_BD-RW_BDR-S12JX_AAAABBBB000E-0:0"
PORT = "/sys/devices/pci0000:00/0000:00:14.0/usb4/4-1/4-1:1.0"


def _scanned(node: str = "sr0", by_id: str | None = BY_ID, port: str = PORT) -> ScannedDrive:
    return ScannedDrive(
        node=node,
        device_path=f"/dev/{node}",
        major=11,
        minor=int(node[2:]),
        vendor="PIONEER",
        model="BD-RW  BDR-S12JX",
        sg="sg0",
        by_id_name=by_id,
        serial="AAAABBBB000E" if by_id else None,
        sysfs_port=port,
    )


def _row(**kw) -> Drive:
    base = dict(
        id="drv_1",
        hostname="h",
        device_path="/dev/sr0",
        status=DriveStatus.ONLINE,
        lifecycle=DriveLifecycle.DETECTED,
        present=True,
        last_seen_at=NOW,
    )
    base.update(kw)
    return Drive(**base)


async def test_new_drive_is_inserted_as_detected_by_id() -> None:
    db = FakeSession()
    summary = await reconcile_drives(db, [_scanned()], now=NOW, prune_days=7)
    [row] = db.rows["drives"]
    assert row.lifecycle is DriveLifecycle.DETECTED and row.present is True
    assert row.identity_kind is DriveIdentityKind.BY_ID and row.by_id_name == BY_ID
    assert row.serial == "AAAABBBB000E" and row.sysfs_port == PORT and row.vendor == "PIONEER"
    assert row.device_path == "/dev/sr0" and row.last_seen_at == NOW
    assert summary == ScanSummary(detected=1, ignored=0, enrolled=0, absent=0, pruned=0)


async def test_no_by_id_inserts_port_identity() -> None:
    db = FakeSession()
    await reconcile_drives(db, [_scanned(by_id=None)], now=NOW, prune_days=7)
    [row] = db.rows["drives"]
    assert row.identity_kind is DriveIdentityKind.PORT and row.by_id_name is None and row.serial is None


async def test_seen_row_is_refreshed_not_duplicated() -> None:
    db = FakeSession()
    db.rows["drives"] = [
        _row(
            by_id_name=BY_ID,
            identity_kind=DriveIdentityKind.BY_ID,
            present=False,
            last_seen_at=NOW - timedelta(days=2),
            device_path="/dev/sr0",
        )
    ]
    await reconcile_drives(db, [_scanned("sr2")], now=NOW, prune_days=7)
    [row] = db.rows["drives"]
    assert row.present is True and row.last_seen_at == NOW and row.device_path == "/dev/sr2"


async def test_enrolled_row_gets_node_refresh_but_presence_untouched() -> None:
    """Presence of an enrolled drive is the ripper's call; its node is a host fact."""
    db = FakeSession()
    db.rows["drives"] = [
        _row(lifecycle=DriveLifecycle.ENROLLED, by_id_name=BY_ID, identity_kind=DriveIdentityKind.BY_ID, present=False)
    ]
    await reconcile_drives(db, [_scanned("sr3")], now=NOW, prune_days=7)
    [row] = db.rows["drives"]
    assert row.device_path == "/dev/sr3"
    assert row.present is False  # NOT flipped by the scanner


async def test_unseen_detected_and_ignored_go_absent_enrolled_does_not() -> None:
    db = FakeSession()
    db.rows["drives"] = [
        _row(
            id="d", lifecycle=DriveLifecycle.DETECTED, by_id_name="usb-A_1-0:0", identity_kind=DriveIdentityKind.BY_ID
        ),
        _row(id="i", lifecycle=DriveLifecycle.IGNORED, by_id_name="usb-B_2-0:0", identity_kind=DriveIdentityKind.BY_ID),
        _row(
            id="e", lifecycle=DriveLifecycle.ENROLLED, by_id_name="usb-C_3-0:0", identity_kind=DriveIdentityKind.BY_ID
        ),
    ]
    summary = await reconcile_drives(db, [], now=NOW, prune_days=7)
    by = {r.id: r for r in db.rows["drives"]}
    assert by["d"].present is False and by["i"].present is False and by["e"].present is True
    assert summary.absent == 2 and summary.enrolled == 1


async def test_stale_detected_rows_are_pruned_ignored_never() -> None:
    db = FakeSession()
    old = NOW - timedelta(days=8)
    db.rows["drives"] = [
        _row(id="stale", lifecycle=DriveLifecycle.DETECTED, present=False, last_seen_at=old, by_id_name="usb-A_1-0:0"),
        _row(
            id="fresh",
            lifecycle=DriveLifecycle.DETECTED,
            present=False,
            last_seen_at=NOW - timedelta(days=6),
            by_id_name="usb-B_2-0:0",
        ),
        _row(id="ign", lifecycle=DriveLifecycle.IGNORED, present=False, last_seen_at=old, by_id_name="usb-C_3-0:0"),
    ]
    summary = await reconcile_drives(db, [], now=NOW, prune_days=7)
    assert {r.id for r in db.rows["drives"]} == {"fresh", "ign"}
    assert summary.pruned == 1


async def test_naive_last_seen_at_is_treated_as_utc_for_pruning() -> None:
    """SQLite hands back naive datetimes for TIMESTAMP columns; comparing a
    naive last_seen_at against the (always aware) cutoff must not raise
    TypeError, and a naive-but-stale row must still be pruned."""
    db = FakeSession()
    naive_old = (NOW - timedelta(days=8)).replace(tzinfo=None)
    db.rows["drives"] = [
        _row(id="stale-naive", lifecycle=DriveLifecycle.DETECTED, present=False, last_seen_at=naive_old),
    ]
    summary = await reconcile_drives(db, [], now=NOW, prune_days=7)
    assert db.rows["drives"] == []
    assert summary.pruned == 1


async def test_port_match_when_by_id_absent_on_both_sides() -> None:
    db = FakeSession()
    db.rows["drives"] = [
        _row(by_id_name=None, identity_kind=DriveIdentityKind.PORT, sysfs_port=PORT, device_path="/dev/sr0")
    ]
    await reconcile_drives(db, [_scanned("sr1", by_id=None)], now=NOW, prune_days=7)
    [row] = db.rows["drives"]
    assert row.device_path == "/dev/sr1"


async def test_a_drive_that_gains_a_by_id_link_upgrades_its_identity() -> None:
    """Port-identity row; udev later publishes a by-id link (driver update). Same port → same row, now by_id."""
    db = FakeSession()
    db.rows["drives"] = [_row(by_id_name=None, identity_kind=DriveIdentityKind.PORT, sysfs_port=PORT)]
    await reconcile_drives(db, [_scanned()], now=NOW, prune_days=7)
    [row] = db.rows["drives"]
    assert row.identity_kind is DriveIdentityKind.BY_ID and row.by_id_name == BY_ID


async def test_enrolled_port_row_adopting_by_id_logs_warning(caplog) -> None:
    """A different physical drive in an enrolled port's slot starts
    publishing a by-id link the enrolled row didn't have — the row silently
    adopts a new identity. That's surprising enough (a possible drive swap
    under an active enrollment) to warrant a log line naming the drive,
    port, and new by-id name; Plan 3's register-time identity check is the
    actual safety net."""
    db = FakeSession()
    db.rows["drives"] = [
        _row(
            id="drv_enrolled",
            lifecycle=DriveLifecycle.ENROLLED,
            by_id_name=None,
            identity_kind=DriveIdentityKind.PORT,
            sysfs_port=PORT,
        )
    ]
    with caplog.at_level(logging.WARNING, logger="arm_backend.drive_scanner"):
        await reconcile_drives(db, [_scanned(port=PORT)], now=NOW, prune_days=7)
    [row] = db.rows["drives"]
    assert row.identity_kind is DriveIdentityKind.BY_ID and row.by_id_name == BY_ID
    messages = [r.message for r in caplog.records]
    assert any("drv_enrolled" in m and PORT in m and BY_ID in m for m in messages)


async def test_prune_window_zero_prunes_absent_detected_rows_now() -> None:
    """Force Rescan passes prune_days=0 straight through to reconcile_drives:
    every DETECTED row that is not present right now is pruned immediately —
    IGNORED and ENROLLED rows are never pruned, regardless of the window."""
    db = FakeSession()
    stale = _row(
        id="drv_gone", lifecycle=DriveLifecycle.DETECTED, present=False, last_seen_at=NOW - timedelta(minutes=5)
    )
    ignored = _row(id="drv_ign", lifecycle=DriveLifecycle.IGNORED, present=False, last_seen_at=NOW - timedelta(days=30))
    enrolled = _row(
        id="drv_enr", lifecycle=DriveLifecycle.ENROLLED, present=False, last_seen_at=NOW - timedelta(days=30)
    )
    db.rows["drives"] = [stale, ignored, enrolled]
    summary = await reconcile_drives(db, [], now=NOW, prune_days=0)
    assert summary.pruned == 1
    assert [r.id for r in db.rows["drives"]] == ["drv_ign", "drv_enr"]


async def test_two_new_rows_on_the_same_node_across_ticks_get_distinct_hostnames() -> None:
    """A node-keyed placeholder (scan-{node}) collides across ticks: a swap on
    sr0 (or an ignored row that's never pruned, so the old by-id stays out of
    `seen`) inserts a second new row for the same srN. hostname is UNIQUE —
    the placeholder must be per-row unique, not node-keyed."""
    db = FakeSession()
    by_id_a = "usb-A_1-0:0"
    by_id_b = "usb-B_2-0:0"

    # Tick 1: drive A detected on sr0.
    await reconcile_drives(db, [_scanned("sr0", by_id=by_id_a)], now=NOW, prune_days=7)
    [row_a] = db.rows["drives"]
    assert row_a.by_id_name == by_id_a

    # Tick 2: drive A is gone, drive B now on sr0 — a different by-id, so a
    # new row is inserted; A's old row is left behind (not pruned same-tick).
    later = NOW + timedelta(minutes=1)
    await reconcile_drives(db, [_scanned("sr0", by_id=by_id_b)], now=later, prune_days=7)

    rows = db.rows["drives"]
    assert len(rows) == 2
    hostnames = {r.hostname for r in rows}
    by_ids = {r.by_id_name for r in rows}
    assert len(hostnames) == 2  # distinct — no UNIQUE collision
    assert by_ids == {by_id_a, by_id_b}
