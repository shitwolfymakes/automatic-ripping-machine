"""Tier-4: image-proxy cache caps are env-tunable, defaulting to current values."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "x")

from arm_backend.config import Settings  # noqa: E402


def test_image_cache_caps_default_to_current_values():
    s = Settings()  # type: ignore[call-arg]
    assert s.ARM_IMAGE_CACHE_MAX_ENTRIES == 1000
    assert s.ARM_IMAGE_CACHE_MAX_BYTES == 2 * 1024 * 1024
    assert s.ARM_IMAGE_CACHE_TTL_SECONDS == 7 * 24 * 3600


def test_image_cache_accessors_read_settings(monkeypatch):
    from arm_backend import config, image_cache

    monkeypatch.setattr(config.settings, "ARM_IMAGE_CACHE_MAX_ENTRIES", 5)
    monkeypatch.setattr(config.settings, "ARM_IMAGE_CACHE_MAX_BYTES", 123)
    monkeypatch.setattr(config.settings, "ARM_IMAGE_CACHE_TTL_SECONDS", 99)
    assert image_cache._max_entries() == 5
    assert image_cache._max_image_bytes() == 123
    assert image_cache._ttl_seconds() == 99
