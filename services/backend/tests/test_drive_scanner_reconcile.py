from __future__ import annotations

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
