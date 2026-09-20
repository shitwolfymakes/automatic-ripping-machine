import json
import stat

import httpx
import respx

from arm_common import KeydbState
from arm_ripper.backend_client import BackendClient
from arm_ripper.community_keydb import KeydbResult, refresh_community_keydb


@respx.mock
async def test_report_keydb_status_posts_body():
    route = respx.post("https://bk/api/ripper/keydb-status").mock(return_value=httpx.Response(204))
    client = BackendClient("https://bk", "tok", "host1")
    await client.report_keydb_status(state=KeydbState.OK, vuk_count=4200, age_days=0)
    await client.close()
    assert route.called
    sent = route.calls.last.request
    assert json.loads(sent.content) == {"state": "ok", "vuk_count": 4200, "age_days": 0}


def _write_fake_script(tmp_path, body: str) -> str:
    p = tmp_path / "update_keydb.sh"
    p.write_text("#!/usr/bin/env bash\n" + body + "\n")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(p)


async def test_keydb_wrapper_parses_ok_line(tmp_path):
    script = _write_fake_script(tmp_path, 'echo "keydb-status: ok vuk=4200"')
    result = await refresh_community_keydb(script_path=script, enabled=True)
    assert result == KeydbResult(state=KeydbState.OK, vuk_count=4200, age_days=None)


async def test_keydb_wrapper_parses_fresh_kept_with_age(tmp_path):
    script = _write_fake_script(tmp_path, 'echo "keydb-status: fresh_kept age_days=3"')
    result = await refresh_community_keydb(script_path=script, enabled=True)
    assert result == KeydbResult(state=KeydbState.FRESH_KEPT, vuk_count=None, age_days=3)


async def test_keydb_wrapper_injects_enabled_env(tmp_path):
    # The fake script branches on the injected ARM_COMMUNITY_KEYDB value.
    script = _write_fake_script(
        tmp_path,
        'test "$ARM_COMMUNITY_KEYDB" = "false" && echo "keydb-status: disabled" || echo "keydb-status: ok"',
    )
    result = await refresh_community_keydb(script_path=script, enabled=False)
    assert result.state is KeydbState.DISABLED


async def test_keydb_wrapper_non_executable_returns_none(tmp_path):
    p = tmp_path / "noexec.sh"
    p.write_text("#!/usr/bin/env bash\necho hi\n")  # NOT chmod +x
    result = await refresh_community_keydb(script_path=str(p), enabled=True)
    assert result is None


async def test_keydb_wrapper_nonzero_exit_is_probe_failed(tmp_path):
    script = _write_fake_script(tmp_path, 'echo "boom" >&2; exit 3')
    result = await refresh_community_keydb(script_path=script, enabled=True)
    assert result.state is KeydbState.PROBE_FAILED


async def test_keydb_wrapper_unparseable_output_is_probe_failed(tmp_path):
    script = _write_fake_script(tmp_path, 'echo "no status line here"')
    result = await refresh_community_keydb(script_path=script, enabled=True)
    assert result.state is KeydbState.PROBE_FAILED


async def test_keydb_wrapper_parses_fields_regardless_of_order(tmp_path):
    # vuk= and age_days= are looked up independently, so their order on the
    # line must not matter — neither field is dropped when reversed.
    script = _write_fake_script(tmp_path, 'echo "keydb-status: ok age_days=2 vuk=99"')
    result = await refresh_community_keydb(script_path=script, enabled=True)
    assert result == KeydbResult(state=KeydbState.OK, vuk_count=99, age_days=2)


async def test_keydb_wrapper_spawn_oserror_returns_none(tmp_path, monkeypatch):
    script = _write_fake_script(tmp_path, 'echo "keydb-status: ok"')

    async def _boom(*_a, **_k):
        raise OSError("no fork")

    monkeypatch.setattr("arm_ripper.community_keydb.asyncio.create_subprocess_exec", _boom)
    result = await refresh_community_keydb(script_path=script, enabled=True)
    assert result is None


async def test_keydb_wrapper_timeout_kills_and_probe_failed(tmp_path, monkeypatch):
    # A script that would hang; we force wait_for to time out so the branch is
    # exercised deterministically without actually sleeping. Close the
    # communicate() coroutine wait_for received so it isn't left un-awaited.
    script = _write_fake_script(tmp_path, 'sleep 5; echo "keydb-status: ok"')

    async def _timeout(coro, *_a, **_k):
        coro.close()
        raise TimeoutError

    monkeypatch.setattr("arm_ripper.community_keydb.asyncio.wait_for", _timeout)
    result = await refresh_community_keydb(script_path=script, enabled=True)
    assert result.state is KeydbState.PROBE_FAILED
