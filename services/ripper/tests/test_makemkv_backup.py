"""`rip_backup` against a faked makemkvcon (same harness as test_makemkv_rip_disc)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

import arm_ripper.rip.makemkv_rip as makemkv_rip
from arm_ripper.rip.makemkv_backup import BACKUP_DIRNAME, rip_backup


class _FakeStream:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    async def readline(self) -> bytes:
        return self._lines.pop(0) if self._lines else b""

    async def read(self) -> bytes:
        return b""


class _FakeProc:
    def __init__(self, lines: list[str], returncode: int = 0) -> None:
        self.stdout = _FakeStream([(ln + "\n").encode() for ln in lines])
        self.stderr = _FakeStream([])
        self.returncode: int | None = None
        self._rc = returncode
        self.killed = False

    async def wait(self) -> int:
        await asyncio.sleep(0)
        if self.returncode is None:
            self.returncode = self._rc
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


def _stub(monkeypatch, proc: _FakeProc, calls: list[tuple[Any, ...]], *, writes_to: Path | None = None) -> None:
    """`writes_to`: the fake makemkvcon writes a backup there when it runs."""

    async def fake_exec(*args: Any, **_kwargs: Any) -> _FakeProc:
        calls.append(args)
        if writes_to is not None:
            _write_backup(writes_to)
        return proc

    monkeypatch.setattr(makemkv_rip.asyncio, "create_subprocess_exec", fake_exec)


def _write_backup(output_dir: Path) -> None:
    bdmv = output_dir / BACKUP_DIRNAME / "BDMV" / "STREAM"
    bdmv.mkdir(parents=True)
    (bdmv.parent / "index.bdmv").write_bytes(b"i" * 10)
    (bdmv / "00000.m2ts").write_bytes(b"v" * 90)


async def test_rip_backup_runs_one_backup_decrypt_command(monkeypatch, tmp_path):
    calls: list[tuple[Any, ...]] = []
    _stub(monkeypatch, _FakeProc([]), calls, writes_to=tmp_path)
    await rip_backup("/dev/sr0", tmp_path)
    assert calls == [
        (
            "makemkvcon",
            "backup",
            "--decrypt",
            "--robot",
            "--progress=-stdout",
            "dev:/dev/sr0",
            str(tmp_path / BACKUP_DIRNAME),
        )
    ]


async def test_rip_backup_success_reports_the_folder_size_and_no_sha(monkeypatch, tmp_path):
    _stub(monkeypatch, _FakeProc([]), [], writes_to=tmp_path)
    result = await rip_backup("/dev/sr0", tmp_path)
    assert (result.ok, result.output_path, result.size_bytes, result.sha256) == (
        True,
        tmp_path / BACKUP_DIRNAME,
        100,
        None,
    )


async def test_rip_backup_reports_disc_progress_without_a_save_phase_marker(monkeypatch, tmp_path):
    _stub(monkeypatch, _FakeProc(["PRGV:0,2500,10000", "PRGV:0,10000,10000"]), [], writes_to=tmp_path)
    ticks: list[float] = []

    async def on_progress(fraction: float) -> None:
        ticks.append(fraction)

    await rip_backup("/dev/sr0", tmp_path, on_progress=on_progress)
    assert ticks == [0.25, 1.0]


async def test_rip_backup_exit_zero_without_index_bdmv_fails(monkeypatch, tmp_path):
    _stub(monkeypatch, _FakeProc([]), [])
    (tmp_path / BACKUP_DIRNAME).mkdir()
    result = await rip_backup("/dev/sr0", tmp_path)
    assert result.ok is False
    assert result.error is not None and "produced no BDMV" in result.error


async def test_rip_backup_never_passes_on_a_stale_backup(monkeypatch, tmp_path):
    """A backup left by an earlier run is cleared first, so its index.bdmv
    cannot pass the success check for a run that wrote nothing."""
    _write_backup(tmp_path)
    _stub(monkeypatch, _FakeProc([]), [])
    result = await rip_backup("/dev/sr0", tmp_path)
    assert result.ok is False
    assert result.error is not None and "produced no BDMV" in result.error


async def test_rip_backup_nonzero_exit_fails_with_diagnostics(monkeypatch, tmp_path):
    _stub(monkeypatch, _FakeProc(['MSG:1002,0,1,"Error while reading input","%1","x"'], returncode=1), [])
    result = await rip_backup("/dev/sr0", tmp_path)
    assert result.ok is False
    assert result.error is not None and "Error while reading input" in result.error


async def test_rip_backup_expired_binary_kills_and_fails(monkeypatch, tmp_path):
    proc = _FakeProc(['MSG:5021,0,0,"expired","%1"'])
    _stub(monkeypatch, proc, [])
    result = await rip_backup("/dev/sr0", tmp_path)
    assert proc.killed
    assert result.ok is False and "MSG:5021" in (result.error or "")


async def test_rip_backup_cancelled_kills_makemkvcon(monkeypatch, tmp_path):
    """Abandoning a job mid-backup must not leave makemkvcon running."""

    class _Hanging(_FakeProc):
        async def wait(self) -> int:
            if self.returncode is None:
                await asyncio.sleep(3600)
            return self.returncode  # type: ignore[return-value]

    proc = _Hanging([])
    _stub(monkeypatch, proc, [])
    task = asyncio.create_task(rip_backup("/dev/sr0", tmp_path))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert proc.killed
