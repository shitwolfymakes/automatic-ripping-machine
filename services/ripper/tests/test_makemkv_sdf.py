import json
import logging
import stat

import httpx
import respx

from arm_common import MakemkvSdfState
from arm_ripper.backend_client import BackendClient
from arm_ripper.makemkv_sdf import REFRESH_TIMEOUT_SECONDS, SdfResult, _parse, refresh_makemkv_sdf


@respx.mock
async def test_report_sdf_status_posts_body():
    route = respx.post("https://bk/api/ripper/sdf-status").mock(return_value=httpx.Response(204))
    client = BackendClient("https://bk", "tok", "host1", drive_id="drv_1")
    await client.report_sdf_status(state=MakemkvSdfState.UPDATED, age_days=0)
    await client.close()
    assert route.called
    assert json.loads(route.calls.last.request.content) == {"state": "updated", "age_days": 0}


def _write_fake_script(tmp_path, body: str) -> str:
    p = tmp_path / "update_sdf.sh"
    p.write_text("#!/usr/bin/env bash\n" + body + "\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(p)


async def test_sdf_wrapper_parses_updated(tmp_path):
    script = _write_fake_script(tmp_path, 'echo "sdf-status: updated"')
    result = await refresh_makemkv_sdf(script_path=script, enabled=True)
    assert result == SdfResult(state=MakemkvSdfState.UPDATED, age_days=None)


async def test_sdf_wrapper_parses_fresh_kept_with_age(tmp_path):
    script = _write_fake_script(tmp_path, 'echo "sdf-status: fresh_kept age_days=4"')
    result = await refresh_makemkv_sdf(script_path=script, enabled=True)
    assert result == SdfResult(state=MakemkvSdfState.FRESH_KEPT, age_days=4)


async def test_sdf_wrapper_injects_disabled_env(tmp_path):
    script = _write_fake_script(
        tmp_path,
        'test "$ARM_MAKEMKV_SDF" = "false" && echo "sdf-status: disabled" || echo "sdf-status: updated"',
    )
    result = await refresh_makemkv_sdf(script_path=script, enabled=False)
    assert result.state is MakemkvSdfState.DISABLED


async def test_sdf_wrapper_non_executable_returns_none(tmp_path):
    p = tmp_path / "noexec.sh"
    p.write_text("#!/usr/bin/env bash\necho hi\n")
    result = await refresh_makemkv_sdf(script_path=str(p), enabled=True)
    assert result is None


async def test_sdf_wrapper_nonzero_exit_is_probe_failed(tmp_path):
    script = _write_fake_script(tmp_path, "echo boom >&2; exit 3")
    result = await refresh_makemkv_sdf(script_path=script, enabled=True)
    assert result.state is MakemkvSdfState.PROBE_FAILED


async def test_sdf_wrapper_unparseable_is_probe_failed(tmp_path):
    script = _write_fake_script(tmp_path, 'echo "no status here"')
    result = await refresh_makemkv_sdf(script_path=script, enabled=True)
    assert result.state is MakemkvSdfState.PROBE_FAILED


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


def _patch_spawn(monkeypatch, proc: _FakeProc) -> None:
    async def _spawn(*_a, **_k):
        return proc

    monkeypatch.setattr("arm_ripper.refresh_script.asyncio.create_subprocess_exec", _spawn)


def _patch_timeout(monkeypatch) -> None:
    async def _timeout(coro, *_a, **_k):
        coro.close()
        raise TimeoutError

    monkeypatch.setattr("arm_ripper.refresh_script.asyncio.wait_for", _timeout)


def _records(caplog):
    return [(r.name, r.levelno, r.getMessage()) for r in caplog.records if r.name == "arm_ripper.makemkv_sdf"]


async def test_sdf_not_executable_logs_debug(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.makemkv_sdf")
    p = tmp_path / "noexec.sh"
    p.write_text("#!/usr/bin/env bash\necho hi\n")
    await refresh_makemkv_sdf(str(p))
    assert _records(caplog) == [("arm_ripper.makemkv_sdf", logging.DEBUG, f"SDF refresh skipped: {p} not executable")]


async def test_sdf_oserror_logs_warning(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.makemkv_sdf")
    script = _write_fake_script(tmp_path, "exit 0")

    async def _boom(*_a, **_k):
        raise OSError("no fork")

    monkeypatch.setattr("arm_ripper.refresh_script.asyncio.create_subprocess_exec", _boom)
    assert await refresh_makemkv_sdf(script) is None
    assert _records(caplog) == [
        ("arm_ripper.makemkv_sdf", logging.WARNING, f"SDF refresh could not start ({script}): no fork")
    ]


async def test_sdf_timeout_kills_waits_and_logs(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.makemkv_sdf")
    script = _write_fake_script(tmp_path, "exit 0")
    proc = _FakeProc()
    _patch_spawn(monkeypatch, proc)
    _patch_timeout(monkeypatch)
    assert await refresh_makemkv_sdf(script) == SdfResult(state=MakemkvSdfState.PROBE_FAILED)
    assert proc.calls == ["kill", "wait"]
    assert _records(caplog) == [
        ("arm_ripper.makemkv_sdf", logging.WARNING, f"SDF refresh timed out after {REFRESH_TIMEOUT_SECONDS:.0f}s")
    ]


async def test_sdf_nonzero_exit_logs_text(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.makemkv_sdf")
    script = _write_fake_script(tmp_path, "echo boom; echo bang >&2; exit 3")
    assert await refresh_makemkv_sdf(script) == SdfResult(state=MakemkvSdfState.PROBE_FAILED)
    assert _records(caplog) == [("arm_ripper.makemkv_sdf", logging.WARNING, "SDF refresh exited 3: boom\nbang")]


async def test_sdf_nonzero_exit_without_output_logs_placeholder(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.makemkv_sdf")
    script = _write_fake_script(tmp_path, "exit 4")
    assert await refresh_makemkv_sdf(script) == SdfResult(state=MakemkvSdfState.PROBE_FAILED)
    assert _records(caplog) == [("arm_ripper.makemkv_sdf", logging.WARNING, "SDF refresh exited 4: <no output>")]


async def test_sdf_success_with_output_logs_info(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.makemkv_sdf")
    script = _write_fake_script(tmp_path, "echo first; echo 'sdf-status: updated'")
    await refresh_makemkv_sdf(script)
    assert _records(caplog) == [("arm_ripper.makemkv_sdf", logging.INFO, "SDF refresh: first | sdf-status: updated")]


async def test_sdf_clean_exit_without_output_parses_empty_and_logs_nothing(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.makemkv_sdf")
    script = _write_fake_script(tmp_path, "exit 0")
    assert await refresh_makemkv_sdf(script) == _parse("")
    assert _records(caplog) == []


def test_sdf_parse_invalid_state_is_probe_failed():
    result = _parse("sdf-status: bogus age_days=2")
    assert result == SdfResult(state=MakemkvSdfState.PROBE_FAILED, age_days=None)
