"""Tier-4: log query/zip caps are env-tunable, defaulting to current values."""

from arm_backend.config import Settings


def test_log_caps_default_to_current_values():
    s = Settings()  # type: ignore[call-arg]
    assert s.ARM_LOG_PER_FILE_DEFAULT == 1000
    assert s.ARM_LOG_PER_FILE_HARD_CAP == 10_000
    assert s.ARM_LOG_ZIP_PER_ENTRY_LINE_CAP == 5000
    assert s.ARM_LOG_ZIP_PER_ENTRY_BYTE_CAP == 5 * 1024 * 1024
