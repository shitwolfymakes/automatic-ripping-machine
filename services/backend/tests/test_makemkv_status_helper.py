"""Unit tests for the shared makemkv_state_detail helper."""

from arm_backend.makemkv_status import makemkv_state_detail


def test_makemkv_state_detail_none_returns_none():
    assert makemkv_state_detail(None) is None


def test_makemkv_state_detail_known_states():
    assert makemkv_state_detail("valid") == "MakeMKV key is valid"
    assert "evaluation expired" in (makemkv_state_detail("unregistered_or_expired") or "")
    assert "rebuild the ripper image" in (makemkv_state_detail("binary_expired") or "")


def test_makemkv_state_detail_unknown_passthrough():
    # An unrecognised state string is returned as-is (no KeyError, no None).
    assert makemkv_state_detail("some_future_state") == "some_future_state"
