from __future__ import annotations

import asyncio
import os
import stat
import time
from pathlib import Path

import pytest

from arm_backend.notifications.bash_runner import build_env, run_script


def _script(tmp_path: Path, name: str, body: str, executable: bool = True) -> Path:
    p = tmp_path / name
    p.write_text("#!/usr/bin/env bash\n" + body)
    if executable:
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return p


def test_build_env_contract(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.delenv("LC_ALL", raising=False)
    env = build_env(
        {"job_title": "Dune", "tracks_done": "3", "event_type": "rip.completed"},
        title="T",
        body="B",
        inputs={"TO": "a@b", "SUBJECT": "s"},
        media_root="/media",
        raw_root="/raw",
    )
    assert env["ARM_JOB_TITLE"] == "Dune" and env["ARM_TRACKS_DONE"] == "3" and env["ARM_EVENT_TYPE"] == "rip.completed"
    assert env["ARM_TITLE"] == "T" and env["ARM_BODY"] == "B"
    assert env["ARM_MEDIA_ROOT"] == "/media" and env["ARM_RAW_ROOT"] == "/raw"
    assert env["TO"] == "a@b" and env["SUBJECT"] == "s"
    assert env["PATH"] == "/usr/bin:/bin"
    assert "DATABASE_URL" not in env and "LC_ALL" not in env


def test_build_env_inputs_cannot_clobber_reserved_names(monkeypatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    env = build_env(
        {},
        title="T",
        body="B",
        inputs={"PATH": "/tmp/evil", "BASH_ENV": "/tmp/x", "LD_PRELOAD": "/tmp/e.so", "TO": "x"},
        media_root="/m",
        raw_root="/r",
    )
    assert env["PATH"] == "/usr/bin:/bin"
    assert "BASH_ENV" not in env and "LD_PRELOAD" not in env
    assert env["TO"] == "x"


def test_build_env_inputs_cannot_clobber_arm_context() -> None:
    env = build_env(
        {"job_title": "Dune"},
        title="T",
        body="B",
        inputs={"ARM_JOB_TITLE": "spoofed", "ARM_TITLE": "spoofed"},
        media_root="/m",
        raw_root="/r",
    )
    assert env["ARM_JOB_TITLE"] == "Dune" and env["ARM_TITLE"] == "T"


def test_build_env_default_path(monkeypatch) -> None:
    monkeypatch.delenv("PATH", raising=False)
    assert build_env({}, title="", body="", inputs={}, media_root="/m", raw_root="/r")["PATH"].startswith(
        "/usr/local/bin"
    )


@pytest.mark.asyncio
async def test_run_script_success(tmp_path: Path) -> None:
    out = tmp_path / "out.txt"
    p = _script(tmp_path, "ok.sh", f'printf "%s|%s|%s|%s" "$1" "$2" "$ARM_JOB_ID" "$TO" > "{out}"; echo done\n')
    res = await run_script(
        p,
        title="Title",
        body="Body",
        env={"ARM_JOB_ID": "job_1", "TO": "x", "PATH": os.environ["PATH"]},
        timeout_seconds=5,
    )
    assert res.ok and res.exit_code == 0 and res.error is None and res.stdout.strip() == "done"
    assert res.duration_ms >= 0
    assert out.read_text() == "Title|Body|job_1|x"


@pytest.mark.asyncio
async def test_run_script_missing(tmp_path: Path) -> None:
    res = await run_script(tmp_path / "nope.sh", title="T", body="B", env={}, timeout_seconds=5)
    assert not res.ok and res.exit_code is None and res.error == "script not found: nope.sh"


@pytest.mark.asyncio
async def test_run_script_not_executable(tmp_path: Path) -> None:
    p = _script(tmp_path, "noexec.sh", "exit 0\n", executable=False)
    res = await run_script(p, title="T", body="B", env={}, timeout_seconds=5)
    assert not res.ok and res.error == "script not executable: noexec.sh (chmod +x it on the host)"


@pytest.mark.asyncio
async def test_run_script_nonzero(tmp_path: Path) -> None:
    p = _script(tmp_path, "fail.sh", 'echo out; echo "boom" >&2; exit 3\n')
    res = await run_script(p, title="T", body="B", env={"PATH": os.environ["PATH"]}, timeout_seconds=5)
    assert not res.ok and res.exit_code == 3 and res.stderr.strip() == "boom" and res.stdout.strip() == "out"
    assert res.error == "script exit code 3: boom"


@pytest.mark.asyncio
async def test_run_script_output_capped(tmp_path: Path) -> None:
    p = _script(tmp_path, "loud.sh", "head -c 20000 /dev/zero | tr '\\0' x; exit 1\n")
    res = await run_script(p, title="T", body="B", env={"PATH": os.environ["PATH"]}, timeout_seconds=5)
    assert len(res.stdout) <= 4096 and res.error is not None and len(res.error) <= 260


@pytest.mark.asyncio
async def test_run_script_timeout(tmp_path: Path) -> None:
    p = _script(tmp_path, "slow.sh", "sleep 5\n")
    res = await run_script(p, title="T", body="B", env={"PATH": os.environ["PATH"]}, timeout_seconds=1)
    assert not res.ok and res.exit_code is None and res.error == "script timed out after 1s: slow.sh"


def _alive(pid: int) -> bool:
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except FileNotFoundError:
        return False
    return state != "Z"


@pytest.mark.asyncio
async def test_run_script_timeout_kills_the_scripts_children(tmp_path: Path) -> None:
    """D-040: the timeout kills the whole process group, not just bash."""
    pidfile = tmp_path / "child.pid"
    p = _script(tmp_path, "tree.sh", f"sleep 30 & echo $! > {pidfile}; wait\n")
    started = time.monotonic()
    res = await run_script(p, title="T", body="B", env={"PATH": os.environ["PATH"]}, timeout_seconds=1)
    assert not res.ok and res.error == "script timed out after 1s: tree.sh"
    assert time.monotonic() - started < 5
    child = int(pidfile.read_text())
    for _ in range(50):
        if not _alive(child):
            break
        await asyncio.sleep(0.05)
    else:
        os.kill(child, 9)
        raise AssertionError("the script's child survived the timeout")


@pytest.mark.asyncio
async def test_run_script_background_child_does_not_hold_the_result(tmp_path: Path) -> None:
    """D-041: bash exiting 0 is success, even with a backgrounded child still
    holding stdout/stderr; the output that arrived before the exit is kept."""
    pidfile = tmp_path / "child.pid"
    p = _script(tmp_path, "bg.sh", f"echo started; sleep 8 & echo $! > {pidfile}; exit 0\n")
    started = time.monotonic()
    res = await run_script(p, title="T", body="B", env={"PATH": os.environ["PATH"]}, timeout_seconds=3)
    try:
        assert res.ok and res.exit_code == 0 and res.error is None and res.stdout.strip() == "started"
        assert time.monotonic() - started < 3
    finally:
        os.kill(int(pidfile.read_text()), 9)


@pytest.mark.asyncio
async def test_run_script_spawn_failure_is_a_failed_run(tmp_path: Path) -> None:
    """D-042: an OSError from exec (here E2BIG) comes back as a result, not an exception."""
    p = _script(tmp_path, "ok.sh", "exit 0\n")
    res = await run_script(p, title="T", body="B", env={"BIG": "x" * 300_000}, timeout_seconds=5)
    assert not res.ok and res.exit_code is None
    assert res.error == "script could not start: Argument list too long: ok.sh"


async def test_drain_tolerates_a_missing_pipe() -> None:
    """Process.stdout/stderr are Optional; a missing pipe reads as no output."""
    from arm_backend.notifications.bash_runner import _drain

    buf = bytearray()
    await _drain(None, buf)
    assert buf == bytearray()
