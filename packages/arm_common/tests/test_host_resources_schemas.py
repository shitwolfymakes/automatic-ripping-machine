from arm_common.schemas import HostResourcesSnapshot, HostResourcesView, MemoryInfo


def _snap() -> HostResourcesSnapshot:
    return HostResourcesSnapshot(
        cpu_percent=10.0,
        cpu_temp=40.0,
        memory=MemoryInfo(total_gb=8.0, used_gb=2.0, free_gb=6.0, percent=25.0),
        storage=[],
    )


def test_host_resources_view_nests_snapshot():
    view = HostResourcesView(role="ripper", hostname="ripper-sr0", version="1.2.3", snapshot=_snap())
    assert view.role == "ripper"
    assert view.hostname == "ripper-sr0"
    assert view.version == "1.2.3"
    assert view.snapshot.cpu_percent == 10.0


def test_system_resources_response_is_gone():
    import arm_common.schemas as s

    assert not hasattr(s, "SystemResourcesResponse")
