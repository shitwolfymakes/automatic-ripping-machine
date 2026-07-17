import os
import subprocess
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "install" / "update_keydb.sh"


def _run(env, *args, home):
    e = {**os.environ, **env, "HOME": str(home)}
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=e,
    )


@pytest.mark.skipif(not SCRIPT.exists(), reason="script not created yet")
def test_disabled_via_env_skips(tmp_path):
    out = _run({"ARM_COMMUNITY_KEYDB": "false"}, home=tmp_path)
    assert out.returncode == 0, out.stderr
    assert "keydb-status: disabled" in out.stdout


@pytest.mark.skipif(not SCRIPT.exists(), reason="script not created yet")
def test_fresh_keydb_is_kept(tmp_path):
    mk = tmp_path / ".MakeMKV"
    mk.mkdir()
    (mk / "keydb.cfg").write_text("xxx | V | yyy\n")  # mtime = now → fresh
    out = _run({"ARM_COMMUNITY_KEYDB": "true"}, home=tmp_path)
    assert out.returncode == 0, out.stderr
    assert "keydb-status: fresh_kept" in out.stdout


@pytest.mark.skipif(not SCRIPT.exists(), reason="script not created yet")
def test_filter_strips_dk_pk_keeps_vuk(tmp_path):
    # Stub curl to "download" our fixture zip into the script's -o target (last arg).
    stub = tmp_path / "bin"
    stub.mkdir()
    raw = "a | DK | b\nc | PK | d\ne | V | f\ng | V | h\n"
    zpath = tmp_path / "fixture.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("keydb.cfg", raw)
    curl = stub / "curl"
    curl.write_text(
        "#!/usr/bin/env bash\n# copy fixture to the -o output path (the arg after -o)\n"
        'out=""; prev=""\nfor a in "$@"; do [ "$prev" = "-o" ] && out="$a"; prev="$a"; done\n'
        f'cp "{zpath}" "$out"\n'
    )
    curl.chmod(0o755)
    out = _run(
        {"ARM_COMMUNITY_KEYDB": "true", "PATH": f"{stub}:{os.environ['PATH']}"},
        "--force",
        home=tmp_path,
    )
    assert out.returncode == 0, out.stderr
    assert "keydb-status: ok" in out.stdout
    assert "vuk=2" in out.stdout
    installed = (tmp_path / ".MakeMKV" / "keydb.cfg").read_text()
    assert "| V |" in installed
    assert "| DK |" not in installed and "| PK |" not in installed


@pytest.mark.skipif(not SCRIPT.exists(), reason="script not created yet")
def test_download_failure_keeps_existing(tmp_path):
    # curl stub that always fails → download_failed, existing keydb untouched.
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "curl").write_text("#!/usr/bin/env bash\nexit 7\n")
    (stub / "curl").chmod(0o755)
    mk = tmp_path / ".MakeMKV"
    mk.mkdir()
    (mk / "keydb.cfg").write_text("old | V | keep\n")
    out = _run(
        {"ARM_COMMUNITY_KEYDB": "true", "PATH": f"{stub}:{os.environ['PATH']}"},
        "--force",
        home=tmp_path,
    )
    assert out.returncode == 0, out.stderr
    assert "keydb-status: download_failed" in out.stdout
    assert (mk / "keydb.cfg").read_text() == "old | V | keep\n"  # preserved


def _curl_stub_copying(stub_dir, src) -> None:
    """Write a curl stub on PATH that copies `src` into the script's -o target."""
    curl = stub_dir / "curl"
    curl.write_text(
        "#!/usr/bin/env bash\n"
        'out=""; prev=""\n'
        'for a in "$@"; do [ "$prev" = "-o" ] && out="$a"; prev="$a"; done\n'
        f'cp "{src}" "$out"\n'
    )
    curl.chmod(0o755)


@pytest.mark.skipif(not SCRIPT.exists(), reason="script not created yet")
def test_non_zip_response_is_empty(tmp_path):
    # curl "downloads" an HTML error page (200 OK but not a ZIP) → empty.
    stub = tmp_path / "bin"
    stub.mkdir()
    page = tmp_path / "error.html"
    page.write_text("<html><body>503 Service Unavailable</body></html>\n")
    _curl_stub_copying(stub, page)
    out = _run(
        {"ARM_COMMUNITY_KEYDB": "true", "PATH": f"{stub}:{os.environ['PATH']}"},
        "--force",
        home=tmp_path,
    )
    assert out.returncode == 0, out.stderr
    assert "keydb-status: empty" in out.stdout


@pytest.mark.skipif(not SCRIPT.exists(), reason="script not created yet")
def test_zip_without_keydb_cfg_is_empty(tmp_path):
    # A valid ZIP that has no keydb.cfg entry → extraction fails → empty.
    stub = tmp_path / "bin"
    stub.mkdir()
    zpath = tmp_path / "nokeydb.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("readme.txt", "not a keydb\n")
    _curl_stub_copying(stub, zpath)
    out = _run(
        {"ARM_COMMUNITY_KEYDB": "true", "PATH": f"{stub}:{os.environ['PATH']}"},
        "--force",
        home=tmp_path,
    )
    assert out.returncode == 0, out.stderr
    assert "keydb-status: empty" in out.stdout


@pytest.mark.skipif(not SCRIPT.exists(), reason="script not created yet")
def test_zip_with_only_dk_pk_is_empty(tmp_path):
    # keydb.cfg with only DK/PK lines → 0 VUK after filter → empty, no install.
    stub = tmp_path / "bin"
    stub.mkdir()
    zpath = tmp_path / "dkpk.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("keydb.cfg", "a | DK | b\nc | PK | d\n")
    _curl_stub_copying(stub, zpath)
    out = _run(
        {"ARM_COMMUNITY_KEYDB": "true", "PATH": f"{stub}:{os.environ['PATH']}"},
        "--force",
        home=tmp_path,
    )
    assert out.returncode == 0, out.stderr
    assert "keydb-status: empty" in out.stdout
    assert not (tmp_path / ".MakeMKV" / "keydb.cfg").exists()  # nothing installed
