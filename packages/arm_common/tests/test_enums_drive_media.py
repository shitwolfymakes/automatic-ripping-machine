from arm_common.enums import DriveMediaStatus


def test_detached_is_a_distinct_media_status() -> None:
    assert DriveMediaStatus.DETACHED == "detached"
    assert DriveMediaStatus.DETACHED is not DriveMediaStatus.UNAVAILABLE


def test_media_status_values_are_stable_wire_strings() -> None:
    # These are persisted as VARCHAR and sent on the heartbeat; renaming one is a wire change.
    assert {s.value for s in DriveMediaStatus} == {
        "loaded", "no_disc", "tray_open", "not_ready", "unavailable", "unknown", "detached",
    }
