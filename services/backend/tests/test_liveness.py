from datetime import timedelta

from arm_backend.liveness import STALE_AFTER


def test_stale_after_is_five_minutes():
    assert STALE_AFTER == timedelta(minutes=5)
