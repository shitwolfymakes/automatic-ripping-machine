"""Branch coverage for LogTailer: the run-loop error/timeout/close paths,
_discover_files (missing dir, unopenable file), _drain_file (unknown path,
rotation incl. stat-FileNotFound / reopen-OSError / close-error), _emit_line
(blank, non-dict extra), and _append_per_job_log's OSError swallow.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend import log_tailer as lt_mod  # noqa: E402
from arm_backend.log_tailer import LogTailer, _FileState  # noqa: E402


class _Hub:
    def __init__(self, subs: int = 1) -> None:
        self._subs = subs
        self.events: list[dict[str, Any]] = []

    def subscriber_count(self, _topic: str) -> int:
        return self._subs

    async def emit(self, **kw: Any) -> None:
        self.events.append(kw)


def _rec(**over: Any) -> str:
    base = {"job_id": "job_01JZXR7K3M5Q8N4VWA00000001", "msg": "hi", "extra": {"logger": "arm_backend.x"}}
    base.update(over)
    return json.dumps(base)


async def test_run_swallows_tick_error_and_closes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    t = LogTailer(_Hub(), log_dir=str(tmp_path))
    t._tick_interval = 0.01
    calls = 0

    async def _boom() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("tick boom")

    monkeypatch.setattr(t, "tick", _boom)
    task = asyncio.create_task(t.run())
    await asyncio.sleep(0.05)
    t.stop()
    await asyncio.wait_for(task, timeout=2.0)
    assert calls >= 1


def test_close_all_swallows_close_error() -> None:
    t = LogTailer(_Hub())

    class _BadFD:
        def close(self) -> None:
            raise OSError("already closed")

    t._files[Path("/x.log")] = _FileState(path=Path("/x.log"), fd=_BadFD(), inode=1)  # type: ignore[arg-type]
    t._close_all()  # must not raise
    assert t._files == {}


async def test_discover_files_missing_dir(tmp_path: Path) -> None:
    t = LogTailer(_Hub(), log_dir=str(tmp_path / "nope"))
    await t._discover_files()
    assert t._files == {}


async def test_discover_files_skips_unopenable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "svc.log").write_text("")
    t = LogTailer(_Hub(), log_dir=str(tmp_path))
    real_open = open

    def _open(path: Any, *a: Any, **k: Any) -> Any:
        if str(path).endswith("svc.log"):
            raise OSError("permission denied")
        return real_open(path, *a, **k)

    monkeypatch.setattr("builtins.open", _open)
    await t._discover_files()  # open raises → logged, file not tracked (131-132)
    assert t._files == {}


async def test_drain_file_unknown_path_noop(tmp_path: Path) -> None:
    t = LogTailer(_Hub(), log_dir=str(tmp_path))
    await t._drain_file(tmp_path / "missing.log")  # state is None → return


async def test_drain_file_rotation_reopens(tmp_path: Path) -> None:
    p = tmp_path / "svc.log"
    p.write_text("")
    t = LogTailer(_Hub(subs=0), log_dir=str(tmp_path))
    await t._discover_files()
    # Simulate rotation: replace the file so its inode changes.
    p.unlink()
    p.write_text(_rec(msg="post-rotation") + "\n")
    await t._drain_file(p)
    assert p in t._files
    t._close_all()


async def test_drain_file_stat_filenotfound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "svc.log"
    p.write_text("")
    t = LogTailer(_Hub(subs=0), log_dir=str(tmp_path))
    await t._discover_files()

    def _stat_missing(_p: object) -> object:
        raise FileNotFoundError

    monkeypatch.setattr(lt_mod.os, "stat", _stat_missing)
    await t._drain_file(p)  # FileNotFoundError → early return, fd kept
    assert p in t._files
    t._close_all()


class _EofFD:
    """fd stub: readline → EOF immediately; close() optionally raises."""

    def __init__(self, raise_on_close: bool = False) -> None:
        self._raise = raise_on_close

    def readline(self) -> str:
        return ""

    def close(self) -> None:
        if self._raise:
            raise OSError("close failed")


async def test_drain_rotation_close_error_then_reopen(tmp_path: Path) -> None:
    p = tmp_path / "svc.log"
    p.write_text("")
    t = LogTailer(_Hub(subs=0), log_dir=str(tmp_path))
    await t._discover_files()
    # Force rotation: new inode, and an fd whose close() raises (158-159).
    t._files[p] = _FileState(path=p, fd=_EofFD(raise_on_close=True), inode=-1)  # type: ignore[arg-type]
    p.unlink()
    p.write_text("after\n")
    await t._drain_file(p)
    assert p in t._files  # reopened successfully despite the close error
    t._close_all()


async def test_drain_rotation_reopen_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "svc.log"
    p.write_text("")
    t = LogTailer(_Hub(subs=0), log_dir=str(tmp_path))
    await t._discover_files()
    t._files[p] = _FileState(path=p, fd=_EofFD(), inode=-1)  # type: ignore[arg-type]
    p.unlink()
    p.write_text("after\n")

    real_open = open

    def _open(path: Any, *a: Any, **k: Any) -> Any:
        if str(path).endswith("svc.log"):
            raise OSError("reopen denied")
        return real_open(path, *a, **k)

    monkeypatch.setattr("builtins.open", _open)
    await t._drain_file(p)
    assert p not in t._files  # reopen failed → path dropped (167-170)


async def test_emit_line_blank_and_non_json(tmp_path: Path) -> None:
    t = LogTailer(_Hub(), log_dir=str(tmp_path))
    await t._emit_line("   \n")  # blank → return
    await t._emit_line("not json\n")  # ValueError → return
    await t._emit_line(json.dumps({"msg": "no job"}) + "\n")  # job_id missing → return
    assert t._hub.events == []  # type: ignore[attr-defined]


async def test_emit_line_extra_not_dict_still_emits(tmp_path: Path) -> None:
    hub = _Hub(subs=1)
    t = LogTailer(hub, log_dir=str(tmp_path))
    await t._emit_line(_rec(extra="a-string") + "\n")  # extra not dict → 199->204
    assert hub.events and hub.events[0]["event_type"] == "log.line"


async def test_emit_line_skips_when_no_subscribers(tmp_path: Path) -> None:
    hub = _Hub(subs=0)
    t = LogTailer(hub, log_dir=str(tmp_path))
    await t._emit_line(_rec() + "\n")
    assert hub.events == []


async def test_emit_line_skips_hub_self_logs(tmp_path: Path) -> None:
    hub = _Hub(subs=1)
    t = LogTailer(hub, log_dir=str(tmp_path))
    await t._emit_line(_rec(extra={"logger": lt_mod._HUB_LOGGER_PREFIX + "x"}) + "\n")
    assert hub.events == []


def test_append_per_job_log_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Point the per-job dir at a path whose mkdir fails (parent is a file).
    afile = tmp_path / "afile"
    afile.write_text("x")
    t = LogTailer(_Hub(), log_dir=str(tmp_path))
    t._per_job_dir = afile / "jobs"  # mkdir(parents=True) under a file → OSError
    t._append_per_job_log("job_01JZXR7K3M5Q8N4VWA00000001", "line")  # swallowed, no raise
