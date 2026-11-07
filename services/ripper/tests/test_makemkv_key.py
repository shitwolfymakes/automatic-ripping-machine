"""Unit tests for the per-rip MakeMKV key refresh."""

import logging
import os
import stat

import pytest

from arm_ripper.makemkv_key import REFRESH_TIMEOUT_SECONDS, refresh_makemkv_key


def _write_script(path, body: str) -> str:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


async def test_runs_executable_script(tmp_path):
    """A present, executable update_key.sh is invoked."""
    marker = tmp_path / "ran"
    script = _write_script(
        tmp_path / "update_key.sh",
        f"#!/usr/bin/env bash\necho 'update_key: scraping monthly beta key from forum'\ntouch {marker}\n",
    )

    await refresh_makemkv_key(script)

    assert marker.exists()


async def test_missing_script_is_noop(tmp_path):
    """No scraper installed (non-makemkv image / unit-test host) → no-op, no raise."""
    await refresh_makemkv_key(str(tmp_path / "does_not_exist.sh"))


async def test_non_executable_script_is_noop(tmp_path):
    """A present-but-not-executable script is skipped like the entrypoint's `[[ -x ]]` guard."""
    script = tmp_path / "update_key.sh"
    script.write_text("#!/usr/bin/env bash\nexit 0\n")
    script.chmod(script.stat().st_mode & ~stat.S_IXUSR & ~stat.S_IXGRP & ~stat.S_IXOTH)
    assert not os.access(str(script), os.X_OK)

    await refresh_makemkv_key(str(script))


async def test_nonzero_exit_is_non_fatal(tmp_path, caplog):
    """A failing script warns but never raises."""
    script = _write_script(
        tmp_path / "update_key.sh",
        "#!/usr/bin/env bash\necho 'boom' >&2\nexit 3\n",
    )

    await refresh_makemkv_key(script)

    assert any("makemkv key refresh exited 3" in r.message for r in caplog.records)


async def test_configured_key_injected_as_env(tmp_path):
    """A configured key is exported to the script as MAKEMKV_KEY so its
    env-var branch picks it up ahead of any host-set value."""
    out = tmp_path / "seen_key"
    script = _write_script(
        tmp_path / "update_key.sh",
        f'#!/usr/bin/env bash\necho "key=${{MAKEMKV_KEY:-unset}}" > {out}\n',
    )

    await refresh_makemkv_key(script, key="T-fromconfig")

    assert out.read_text().strip() == "key=T-fromconfig"


async def test_blank_key_does_not_shadow_env(tmp_path, monkeypatch):
    """A blank/whitespace key is treated as unset so it doesn't override the
    inherited env-var / scrape fallback."""
    monkeypatch.delenv("MAKEMKV_KEY", raising=False)
    out = tmp_path / "seen_key"
    script = _write_script(
        tmp_path / "update_key.sh",
        f'#!/usr/bin/env bash\necho "key=${{MAKEMKV_KEY:-unset}}" > {out}\n',
    )

    await refresh_makemkv_key(script, key="   ")

    assert out.read_text().strip() == "key=unset"


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
    return [(r.name, r.levelno, r.getMessage()) for r in caplog.records if r.name == "arm_ripper.makemkv_key"]


async def test_key_not_executable_logs_debug(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.makemkv_key")
    p = tmp_path / "noexec.sh"
    p.write_text("#!/usr/bin/env bash\necho hi\n")
    await refresh_makemkv_key(str(p))
    assert _records(caplog) == [
        ("arm_ripper.makemkv_key", logging.DEBUG, f"makemkv key refresh skipped: {p} not executable")
    ]


async def test_key_oserror_logs_warning(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.makemkv_key")
    script = _bash_script(tmp_path, "exit 0")

    async def _boom(*_a, **_k):
        raise OSError("no fork")

    monkeypatch.setattr("arm_ripper.refresh_script.asyncio.create_subprocess_exec", _boom)
    assert await refresh_makemkv_key(script) is None
    assert _records(caplog) == [
        ("arm_ripper.makemkv_key", logging.WARNING, f"makemkv key refresh could not start ({script}): no fork")
    ]


async def test_key_timeout_kills_waits_and_logs(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.makemkv_key")
    script = _bash_script(tmp_path, "exit 0")
    proc = _FakeProc()
    _patch_spawn(monkeypatch, proc)
    _patch_timeout(monkeypatch)
    assert await refresh_makemkv_key(script) is None
    assert proc.calls == ["kill", "wait"]
    assert _records(caplog) == [
        (
            "arm_ripper.makemkv_key",
            logging.WARNING,
            f"makemkv key refresh timed out after {REFRESH_TIMEOUT_SECONDS:.0f}s",
        )
    ]


async def test_key_nonzero_exit_logs_text(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.makemkv_key")
    script = _bash_script(tmp_path, "echo boom; echo bang >&2; exit 3")
    assert await refresh_makemkv_key(script) is None
    assert _records(caplog) == [("arm_ripper.makemkv_key", logging.WARNING, "makemkv key refresh exited 3: boom\nbang")]


async def test_key_nonzero_exit_without_output_logs_placeholder(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.makemkv_key")
    script = _bash_script(tmp_path, "exit 4")
    assert await refresh_makemkv_key(script) is None
    assert _records(caplog) == [
        ("arm_ripper.makemkv_key", logging.WARNING, "makemkv key refresh exited 4: <no output>")
    ]


async def test_key_success_with_output_logs_info(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.makemkv_key")
    script = _bash_script(tmp_path, "echo first; echo 'using key'")
    await refresh_makemkv_key(script)
    assert _records(caplog) == [("arm_ripper.makemkv_key", logging.INFO, "makemkv key refresh: first | using key")]


def _bash_script(tmp_path, body: str) -> str:
    return _write_script(tmp_path / "update_key.sh", "#!/usr/bin/env bash\n" + body + "\n")


def _capture_env(monkeypatch) -> dict:
    seen: dict = {}

    async def _spawn(*_a, **kwargs):
        seen.update(kwargs)
        return _FakeProc()

    monkeypatch.setattr("arm_ripper.refresh_script.asyncio.create_subprocess_exec", _spawn)
    return seen


@pytest.mark.parametrize("key", [None, "", "   "])
async def test_blank_key_passes_env_none(tmp_path, monkeypatch, key):
    seen = _capture_env(monkeypatch)
    await refresh_makemkv_key(_bash_script(tmp_path, "exit 0"), key=key)
    assert seen["env"] is None


async def test_real_key_sets_makemkv_key_on_top_of_environ(tmp_path, monkeypatch):
    monkeypatch.setenv("MAKEMKV_KEY", "T-host")
    monkeypatch.setenv("ARM_TEST_MARKER", "present")
    seen = _capture_env(monkeypatch)
    await refresh_makemkv_key(_bash_script(tmp_path, "exit 0"), key="T-cfg")
    assert seen["env"] == {**os.environ, "MAKEMKV_KEY": "T-cfg"}
    assert seen["env"]["MAKEMKV_KEY"] == "T-cfg"
    assert seen["env"]["ARM_TEST_MARKER"] == "present"
