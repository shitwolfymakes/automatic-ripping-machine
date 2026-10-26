import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.metadata.details_cache import TtlCache  # noqa: E402


def test_get_returns_until_expiry() -> None:
    now = [0.0]
    cache: TtlCache[str, int] = TtlCache(ttl_s=10, max_entries=4, clock=lambda: now[0])
    cache.put("a", 1)
    now[0] = 9.9
    assert cache.get("a") == 1
    now[0] = 10.1
    assert cache.get("a") is None


def test_oldest_entry_is_evicted_at_the_cap() -> None:
    cache: TtlCache[str, int] = TtlCache(ttl_s=100, max_entries=2, clock=lambda: 0.0)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert (cache.get("a"), cache.get("b"), cache.get("c")) == (None, 2, 3)


def test_clear_empties() -> None:
    cache: TtlCache[str, int] = TtlCache()
    cache.put("a", 1)
    cache.clear()
    assert cache.get("a") is None
