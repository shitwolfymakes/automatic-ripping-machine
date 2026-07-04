from datetime import datetime, timezone

from arm_backend.host_snapshots import HostSnapshotStore
from arm_common.schemas import HostResourcesSnapshot, MemoryInfo


def _snap(cpu: float) -> HostResourcesSnapshot:
    return HostResourcesSnapshot(
        cpu_percent=cpu,
        cpu_temp=0.0,
        memory=MemoryInfo(total_gb=8.0, used_gb=1.0, free_gb=7.0, percent=12.5),
        storage=[],
    )


def test_put_then_get_returns_latest():
    store = HostSnapshotStore()
    t0 = datetime(2026, 7, 4, tzinfo=timezone.utc)
    store.put("h1", _snap(1.0), t0)
    got = store.get("h1")
    assert got is not None
    snap, ts = got
    assert snap.cpu_percent == 1.0
    assert ts == t0


def test_put_overwrites():
    store = HostSnapshotStore()
    t0 = datetime(2026, 7, 4, tzinfo=timezone.utc)
    store.put("h1", _snap(1.0), t0)
    store.put("h1", _snap(2.0), t0)
    got = store.get("h1")
    assert got is not None
    assert got[0].cpu_percent == 2.0


def test_get_unknown_returns_none():
    assert HostSnapshotStore().get("nope") is None
