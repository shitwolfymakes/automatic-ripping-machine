import json
import stat

import httpx
import respx

from arm_common import MakemkvSdfState
from arm_ripper.backend_client import BackendClient
from arm_ripper.makemkv_sdf import SdfResult, refresh_makemkv_sdf


@respx.mock
async def test_report_sdf_status_posts_body():
    route = respx.post("https://bk/api/ripper/sdf-status").mock(return_value=httpx.Response(204))
    client = BackendClient("https://bk", "tok", "host1")
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
    script = _write_fake_script(tmp_path, 'echo boom >&2; exit 3')
    result = await refresh_makemkv_sdf(script_path=script, enabled=True)
    assert result.state is MakemkvSdfState.PROBE_FAILED


async def test_sdf_wrapper_unparseable_is_probe_failed(tmp_path):
    script = _write_fake_script(tmp_path, 'echo "no status here"')
    result = await refresh_makemkv_sdf(script_path=script, enabled=True)
    assert result.state is MakemkvSdfState.PROBE_FAILED
