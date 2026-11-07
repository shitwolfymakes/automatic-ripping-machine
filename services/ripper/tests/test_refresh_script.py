import logging
import re
import stat
from enum import StrEnum

from arm_ripper.refresh_script import ScriptOutcome, ScriptRun, int_field, last_status, run_refresh_script

_LOG = logging.getLogger("test.refresh_script")
_LABEL = "demo refresh"
_ENV = {"DEMO": "1"}


def _write_fake_script(tmp_path, body: str) -> str:
    p = tmp_path / "refresh.sh"
    p.write_text("#!/usr/bin/env bash\n" + body + "\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(p)


class _FakeProc:
    def __init__(self, returncode: int = 0, out: bytes = b"") -> None:
        self.returncode = returncode
        self._out = out
        self.calls: list[str] = []

    async def communicate(self) -> tuple[bytes, None]:
        return self._out, None

    def kill(self) -> None:
        self.calls.append("kill")

    async def wait(self) -> int:
        self.calls.append("wait")
        return self.returncode


def _patch_spawn(monkeypatch, proc: _FakeProc) -> dict:
    seen: dict = {}

    async def _spawn(*args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return proc

    monkeypatch.setattr("arm_ripper.refresh_script.asyncio.create_subprocess_exec", _spawn)
    return seen


def _records(caplog):
    return [(r.name, r.levelno, r.getMessage()) for r in caplog.records if r.name == _LOG.name]


async def _run(script: str, timeout: float = 5.0) -> ScriptRun:
    return await run_refresh_script(script, env=_ENV, timeout=timeout, label=_LABEL, logger=_LOG)


async def test_skipped_when_not_executable(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger=_LOG.name)
    p = tmp_path / "noexec.sh"
    p.write_text("#!/usr/bin/env bash\necho hi\n")
    assert await _run(str(p)) == ScriptRun(ScriptOutcome.SKIPPED)
    assert _records(caplog) == [(_LOG.name, logging.DEBUG, f"{_LABEL} skipped: {p} not executable")]


async def test_not_started_when_spawn_raises(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger=_LOG.name)
    script = _write_fake_script(tmp_path, "exit 0")

    async def _boom(*_a, **_k):
        raise OSError("no fork")

    monkeypatch.setattr("arm_ripper.refresh_script.asyncio.create_subprocess_exec", _boom)
    assert await _run(script) == ScriptRun(ScriptOutcome.NOT_STARTED)
    assert _records(caplog) == [(_LOG.name, logging.WARNING, f"{_LABEL} could not start ({script}): no fork")]


async def test_timed_out_kills_waits_and_logs(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger=_LOG.name)
    script = _write_fake_script(tmp_path, "exit 0")
    proc = _FakeProc()
    seen = _patch_spawn(monkeypatch, proc)

    async def _timeout(coro, *_a, **_k):
        coro.close()
        raise TimeoutError

    monkeypatch.setattr("arm_ripper.refresh_script.asyncio.wait_for", _timeout)
    assert await _run(script, timeout=12.6) == ScriptRun(ScriptOutcome.TIMED_OUT)
    assert proc.calls == ["kill", "wait"]
    assert seen["kwargs"]["env"] == _ENV
    assert _records(caplog) == [(_LOG.name, logging.WARNING, f"{_LABEL} timed out after 13s")]


async def test_failed_with_output_logs_text(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger=_LOG.name)
    script = _write_fake_script(tmp_path, "exit 0")
    seen = _patch_spawn(monkeypatch, _FakeProc(returncode=3, out=b"boom\nbang\n"))
    assert await _run(script) == ScriptRun(ScriptOutcome.FAILED, "boom\nbang")
    assert seen["args"] == (script,)
    assert seen["kwargs"]["env"] == _ENV
    assert _records(caplog) == [(_LOG.name, logging.WARNING, f"{_LABEL} exited 3: boom\nbang")]


async def test_failed_without_output_logs_placeholder(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger=_LOG.name)
    script = _write_fake_script(tmp_path, "exit 0")
    seen = _patch_spawn(monkeypatch, _FakeProc(returncode=4))
    assert await _run(script) == ScriptRun(ScriptOutcome.FAILED, "")
    assert seen["kwargs"]["env"] == _ENV
    assert _records(caplog) == [(_LOG.name, logging.WARNING, f"{_LABEL} exited 4: <no output>")]


async def test_succeeded_with_output_logs_info(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger=_LOG.name)
    script = _write_fake_script(tmp_path, "exit 0")
    seen = _patch_spawn(monkeypatch, _FakeProc(out=b"  first\nsecond\n"))
    assert await _run(script) == ScriptRun(ScriptOutcome.SUCCEEDED, "first\nsecond")
    assert seen["kwargs"]["env"] == _ENV
    assert _records(caplog) == [(_LOG.name, logging.INFO, f"{_LABEL}: first | second")]


async def test_succeeded_without_output_logs_nothing(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger=_LOG.name)
    script = _write_fake_script(tmp_path, "exit 0")
    seen = _patch_spawn(monkeypatch, _FakeProc())
    assert await _run(script) == ScriptRun(ScriptOutcome.SUCCEEDED, "")
    assert seen["kwargs"]["env"] == _ENV
    assert _records(caplog) == []


class _State(StrEnum):
    OK = "ok"
    STALE = "stale"


_STATUS_RE = re.compile(r"x-status:\s*(?P<state>\S+)")


def test_last_status_no_matching_line_is_none():
    assert last_status("hello\nworld", _STATUS_RE, _State) is None


def test_last_status_empty_text_is_none():
    assert last_status("", _STATUS_RE, _State) is None


def test_last_status_returns_last_matching_line():
    text = "x-status: ok a=1\nx-status: stale b=2"
    assert last_status(text, _STATUS_RE, _State) == (_State.STALE, "x-status: stale b=2")


def test_last_status_invalid_last_state_is_none_even_if_earlier_valid():
    assert last_status("x-status: ok\nx-status: bogus", _STATUS_RE, _State) is None


def test_last_status_matching_line_among_others():
    text = "noise\nx-status: ok n=3\nmore noise"
    assert last_status(text, _STATUS_RE, _State) == (_State.OK, "x-status: ok n=3")


def test_int_field_match_returns_int():
    assert int_field(re.compile(r"n=(\d+)"), "n=42") == 42


def test_int_field_no_match_is_none():
    assert int_field(re.compile(r"n=(\d+)"), "m=42") is None


def test_int_field_named_group_works_via_group_one():
    assert int_field(re.compile(r"\bvuk=(?P<vuk>\d+)"), "vuk=7") == 7


def test_int_field_matches_anywhere_in_line():
    assert int_field(re.compile(r"n=(\d+)"), "ok a=1 n=5 b=2") == 5
