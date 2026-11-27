import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "install" / "update_key.sh"
PURCHASED = "M-" + "A" * 66
BETA = "T-" + "B" * 66


def _run(home, key):
    env = {**os.environ, "HOME": str(home), "MAKEMKV_KEY": key}
    return subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env)


def _settings(home):
    return (home / ".MakeMKV" / "settings.conf").read_text().splitlines()


def test_creates_settings_when_missing(tmp_path):
    out = _run(tmp_path, BETA)
    assert out.returncode == 0, out.stderr
    assert _settings(tmp_path) == [f'app_Key = "{BETA}"']


def test_replaces_a_beta_key(tmp_path):
    (tmp_path / ".MakeMKV").mkdir()
    (tmp_path / ".MakeMKV" / "settings.conf").write_text('app_Key = "T-old"\n')
    assert _run(tmp_path, BETA).returncode == 0
    assert _settings(tmp_path) == [f'app_Key = "{BETA}"']


def test_replaces_a_stored_purchased_key(tmp_path):
    (tmp_path / ".MakeMKV").mkdir()
    (tmp_path / ".MakeMKV" / "settings.conf").write_text(f'app_Key = "{PURCHASED}"\n')
    assert _run(tmp_path, BETA).returncode == 0
    assert _settings(tmp_path) == [f'app_Key = "{BETA}"']


def test_keeps_other_settings_and_leaves_one_app_key(tmp_path):
    (tmp_path / ".MakeMKV").mkdir()
    (tmp_path / ".MakeMKV" / "settings.conf").write_text(
        f'app_DefaultLanguage = "eng"\napp_Key = "{PURCHASED}"\napp_Key = "T-dup"\n'
    )
    assert _run(tmp_path, BETA).returncode == 0
    lines = _settings(tmp_path)
    assert lines.count(f'app_Key = "{BETA}"') == 1
    assert [x for x in lines if x.startswith("app_Key")] == [f'app_Key = "{BETA}"']
    assert 'app_DefaultLanguage = "eng"' in lines
    assert not list((tmp_path / ".MakeMKV").glob("settings.conf.*"))
