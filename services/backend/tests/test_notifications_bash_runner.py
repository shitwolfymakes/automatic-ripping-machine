from __future__ import annotations

import os
import stat
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
