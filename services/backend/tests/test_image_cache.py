"""Disk-backed image cache: store/retrieve/TTL/LRU/traversal/startup_scan."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend import image_cache  # noqa: E402


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(image_cache.settings, "ARM_IMAGE_CACHE_PATH", str(tmp_path))
    image_cache.reset()
    yield str(tmp_path)
    image_cache.reset()


def test_store_and_retrieve_roundtrip(cache_dir):
    assert image_cache.store("http://h/x.jpg", b"bytes", "image/jpeg") is True
    got = image_cache.retrieve("http://h/x.jpg")
    assert got == (b"bytes", "image/jpeg")


def test_retrieve_miss_returns_none(cache_dir):
    assert image_cache.retrieve("http://h/missing.jpg") is None


def test_store_rejects_oversized(cache_dir):
    big = b"x" * (2 * 1024 * 1024 + 1)
    assert image_cache.store("http://h/big.jpg", big, "image/png") is False
    assert image_cache.retrieve("http://h/big.jpg") is None


def test_ttl_expiry_evicts(cache_dir, monkeypatch):
    image_cache.store("http://h/old.jpg", b"d", "image/jpeg")
    monkeypatch.setitem(image_cache._index["http://h/old.jpg"], "cached_at", 0.0)
    assert image_cache.retrieve("http://h/old.jpg") is None


def test_lru_eviction_at_capacity(cache_dir, monkeypatch):
    monkeypatch.setattr(image_cache, "_MAX_ENTRIES", 2)
    image_cache.store("http://h/a.jpg", b"a", "image/jpeg")
    image_cache.store("http://h/b.jpg", b"b", "image/jpeg")
    image_cache.retrieve("http://h/a.jpg")
    image_cache.store("http://h/c.jpg", b"c", "image/jpeg")
    assert image_cache.retrieve("http://h/b.jpg") is None
    assert image_cache.retrieve("http://h/a.jpg") is not None
    assert image_cache.retrieve("http://h/c.jpg") is not None


def test_clear_returns_stats(cache_dir):
    image_cache.store("http://h/a.jpg", b"aa", "image/jpeg")
    out = image_cache.clear()
    assert out["success"] is True
    assert out["cleared"] == 1
    assert out["freed_bytes"] > 0
    assert image_cache.retrieve("http://h/a.jpg") is None


def test_stats_shape(cache_dir):
    image_cache.store("http://h/a.jpg", b"aaaa", "image/jpeg")
    s = image_cache.stats()
    assert s["count"] == 1
    assert s["size_bytes"] == 4
    assert "size_mb" in s and "oldest" in s and s["path"] == cache_dir


def test_retrieve_evicts_when_file_missing(cache_dir):
    image_cache.store("http://h/a.jpg", b"a", "image/jpeg")
    import pathlib

    for p in pathlib.Path(cache_dir).glob("*.img"):
        p.unlink()
    assert image_cache.retrieve("http://h/a.jpg") is None


def test_startup_scan_rebuilds_index(cache_dir):
    image_cache.store("http://h/a.jpg", b"a", "image/jpeg")
    image_cache.reset()
    assert image_cache.retrieve("http://h/a.jpg") is None
    image_cache.startup_scan()
    assert image_cache.retrieve("http://h/a.jpg") == (b"a", "image/jpeg")


def test_startup_scan_drops_expired(cache_dir, monkeypatch):
    image_cache.store("http://h/a.jpg", b"a", "image/jpeg")
    image_cache.reset()
    monkeypatch.setattr(image_cache, "_TTL_SECONDS", -1)
    image_cache.startup_scan()
    assert image_cache.retrieve("http://h/a.jpg") is None


def test_startup_scan_skips_corrupt_entry(cache_dir):
    import pathlib

    (pathlib.Path(cache_dir) / "bad.json").write_text("{not json")
    (pathlib.Path(cache_dir) / "bad.img").write_bytes(b"x")
    image_cache.startup_scan()
    assert image_cache.stats()["count"] == 0


def test_store_blocks_path_traversal(cache_dir, monkeypatch):
    monkeypatch.setattr(image_cache, "_url_to_filename", lambda url: "../escape")
    with pytest.raises(ValueError, match="traversal"):
        image_cache.store("http://h/x.jpg", b"d", "image/jpeg")


def test_remove_absent_url_returns_zero(cache_dir):
    assert image_cache._remove("http://h/absent.jpg") == 0


def test_startup_scan_no_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(image_cache.settings, "ARM_IMAGE_CACHE_PATH", str(tmp_path / "does-not-exist"))
    image_cache.reset()
    image_cache.startup_scan()
    assert image_cache.stats()["count"] == 0


def test_startup_scan_reaps_orphaned_metadata(cache_dir):
    import pathlib

    image_cache.store("http://h/a.jpg", b"a", "image/jpeg")
    for p in pathlib.Path(cache_dir).glob("*.img"):
        p.unlink()
    orphans = list(pathlib.Path(cache_dir).glob("*.json"))
    assert orphans
    image_cache.reset()
    image_cache.startup_scan()
    assert image_cache.stats()["count"] == 0
    assert list(pathlib.Path(cache_dir).glob("*.json")) == []
