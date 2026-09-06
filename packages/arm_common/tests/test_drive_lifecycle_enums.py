from arm_common import DriveIdentityKind, DriveLifecycle
from arm_common.schemas import DriveDevicePathUpdateRequest, DriveRescanResponse, DriveView


def test_lifecycle_wire_strings_are_stable() -> None:
    assert {s.value for s in DriveLifecycle} == {"detected", "ignored", "enrolled"}
    assert {s.value for s in DriveIdentityKind} == {"by_id", "port"}


def test_drive_view_carries_lifecycle_fields() -> None:
    fields = DriveView.model_fields
    for name in ("lifecycle", "present", "identity_kind", "serial", "by_id_name", "vendor", "model", "last_error"):
        assert name in fields, name


def test_rescan_response_counts_default_to_zero() -> None:
    r = DriveRescanResponse(online=1, stale=0)
    assert (r.detected, r.ignored, r.enrolled, r.absent, r.pruned) == (0, 0, 0, 0, 0)


def test_device_path_update_request() -> None:
    assert DriveDevicePathUpdateRequest(device_path="/dev/sr2").device_path == "/dev/sr2"
