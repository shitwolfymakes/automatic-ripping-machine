"""rip_data: dd invocation per source kind, byte progress, failure paths."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from arm_ripper.rip import data_rip


class _FakeProc:
    """Stands in for dd: writes the output file in steps while "running"."""

    def __init__(self, out: Path, chunks: list[bytes], returncode: int = 0) -> None:
        self._out = out
        self._chunks = chunks
        self._rc = returncode
        self.returncode: int | None = None
        self.stderr = None

    async def wait(self) -> int:
        with self._out.open("ab") as fh:
            for chunk in self._chunks:
                fh.write(chunk)
                fh.flush()
                await asyncio.sleep(0.02)
        self.returncode = self._rc
        return self._rc

    def kill(self) -> None:
        self.returncode = -9


def _patch_dd(monkeypatch: pytest.MonkeyPatch, chunks: list[bytes], calls: list[list[str]], rc: int = 0) -> None:
    async def fake_exec(*cmd: str, **_kw: object) -> _FakeProc:
        calls.append(list(cmd))
        out = Path(next(a for a in cmd if a.startswith("of="))[3:])
        return _FakeProc(out, chunks, rc)

    async def fake_sha(_p: Path) -> str:
        return "sha"

    monkeypatch.setattr(data_rip.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(data_rip, "sha256_file", fake_sha)
    monkeypatch.setattr(data_rip, "PROGRESS_INTERVAL_SECONDS", 0.01)


async def test_iso_copy_uses_big_blocks_and_reports_bytes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    src = tmp_path / "movie.iso"
    src.write_bytes(b"x" * 3000)
    calls: list[list[str]] = []
    _patch_dd(monkeypatch, [b"x" * 1000, b"x" * 1000, b"x" * 1000], calls)
    seen: list[tuple[int, int | None]] = []

    async def on_progress(done: int, total: int | None) -> None:
        seen.append((done, total))

    result = await data_rip.rip_data(str(src), tmp_path / "out", on_progress=on_progress)
    assert result.ok and result.size_bytes == 3000
    assert "bs=4M" in calls[0] and not any(a.startswith("conv=") for a in calls[0])
    assert seen[-1] == (3000, 3000)
    assert all(total == 3000 for _done, total in seen)
    assert [done for done, _t in seen] == sorted(done for done, _t in seen)


async def test_device_keeps_sector_blocks_with_noerror(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    _patch_dd(monkeypatch, [b"y" * 2048], calls)
    monkeypatch.setattr(data_rip, "source_size", lambda _p: None)
    result = await data_rip.rip_data("/dev/sr0", tmp_path / "out")
    assert result.ok
    assert "bs=2048" in calls[0] and "conv=noerror,sync" in calls[0]


async def test_progress_callback_errors_never_fail_the_copy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    src = tmp_path / "movie.iso"
    src.write_bytes(b"x" * 10)
    _patch_dd(monkeypatch, [b"x" * 5, b"x" * 5], [])

    async def boom(_done: int, _total: int | None) -> None:
        raise RuntimeError("ws down")

    result = await data_rip.rip_data(str(src), tmp_path / "out", on_progress=boom)
    assert result.ok


async def test_dd_failure_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    src = tmp_path / "movie.iso"
    src.write_bytes(b"x")
    _patch_dd(monkeypatch, [], [], rc=1)
    result = await data_rip.rip_data(str(src), tmp_path / "out")
    assert not result.ok and "dd failed" in (result.error or "")


def test_source_size(tmp_path: Path) -> None:
    f = tmp_path / "a.iso"
    f.write_bytes(b"x" * 42)
    assert data_rip.source_size(str(f)) == 42
    assert data_rip.source_size(str(tmp_path / "missing.iso")) is None
