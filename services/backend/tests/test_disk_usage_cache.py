import subprocess

import arm_backend.disk_usage_cache as duc


def test_get_disk_usage_cache_hit(monkeypatch):
    duc._cache.clear()
    with duc._cache_lock:
        duc._cache["/raw"] = {"total": 100, "used": 40, "free": 60, "percent": 40.0, "ts": 0.0}
    # A cache hit must NOT spawn a subprocess.
    def boom(*a, **k):
        raise AssertionError("should not refresh on a cache hit")
    monkeypatch.setattr(duc, "refresh_path", boom)
    out = duc.get_disk_usage("/raw")
    assert out == {"total": 100, "used": 40, "free": 60, "percent": 40.0}


def test_get_disk_usage_miss_triggers_refresh(monkeypatch):
    duc._cache.clear()
    def fake_refresh(path):
        with duc._cache_lock:
            duc._cache[path] = {"total": 10, "used": 3, "free": 7, "percent": 30.0, "ts": 0.0}
    monkeypatch.setattr(duc, "refresh_path", fake_refresh)
    out = duc.get_disk_usage("/raw")
    assert out == {"total": 10, "used": 3, "free": 7, "percent": 30.0}


def test_refresh_path_timeout_leaves_no_entry(monkeypatch):
    duc._cache.clear()
    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=5)
    monkeypatch.setattr(duc.subprocess, "run", fake_run)
    duc.refresh_path("/nfs-stalled")           # must not raise
    assert duc.get_disk_usage("/nfs-stalled") is None


def test_refresh_path_parses_subprocess_json(monkeypatch):
    duc._cache.clear()
    class R:
        returncode = 0
        stdout = '{"total": 200, "used": 50, "free": 150, "percent": 25.0}'
    monkeypatch.setattr(duc.subprocess, "run", lambda *a, **k: R())
    duc.refresh_path("/raw")
    assert duc.get_disk_usage("/raw") == {"total": 200, "used": 50, "free": 150, "percent": 25.0}
