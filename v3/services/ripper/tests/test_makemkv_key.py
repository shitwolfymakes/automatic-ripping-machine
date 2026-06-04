"""Unit tests for the per-rip MakeMKV key refresh."""

import os
import stat

from arm_ripper.makemkv_key import refresh_makemkv_key


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
