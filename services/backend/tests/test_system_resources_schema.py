from arm_common.schemas import HostResourcesSnapshot, HostResourcesView, MemoryInfo, StorageRoot


def test_host_resources_snapshot_shape():
    s = HostResourcesSnapshot(
        cpu_percent=12.5,
        cpu_temp=0.0,
        memory=MemoryInfo(total_gb=15.0, used_gb=1.6, free_gb=13.0, percent=10.7),
        storage=[StorageRoot(name="Raw", path="/raw", total_gb=100.0, used_gb=40.0, free_gb=60.0, percent=40.0)],
    )
    assert s.cpu_percent == 12.5
    assert s.memory.free_gb == 13.0
    assert s.storage[0].name == "Raw"


def test_host_resources_view_shape():
    v = HostResourcesView(
        role="backend",
        hostname="backend-1",
        version="9.9",
        snapshot=HostResourcesSnapshot(
            cpu_percent=1.0,
            cpu_temp=0.0,
            memory=MemoryInfo(total_gb=8.0, used_gb=1.0, free_gb=7.0, percent=12.5),
            storage=[],
        ),
    )
    assert v.role == "backend"
    assert v.hostname == "backend-1"
    assert v.snapshot.memory.total_gb == 8.0
