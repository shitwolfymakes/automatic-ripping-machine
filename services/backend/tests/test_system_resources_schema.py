from arm_common.schemas import MemoryInfo, StorageRoot, SystemResourcesResponse


def test_system_resources_response_shape():
    r = SystemResourcesResponse(
        cpu_percent=12.5,
        cpu_temp=0.0,
        memory=MemoryInfo(total_gb=15.0, used_gb=1.6, free_gb=13.0, percent=10.7),
        storage=[StorageRoot(name="Raw", path="/raw", total_gb=100.0, used_gb=40.0, free_gb=60.0, percent=40.0)],
    )
    assert r.cpu_percent == 12.5
    assert r.memory.free_gb == 13.0
    assert r.storage[0].name == "Raw"
