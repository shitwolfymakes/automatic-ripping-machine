from __future__ import annotations

import stat
from pathlib import Path

import pytest

from arm_backend.notifications.script_meta import (
    list_scripts,
    parse_header,
    read_script_info,
    resolve_script,
    validate_script_name,
)

HEADER = """#!/usr/bin/env bash
# arm-hook: Send an email through the local SMTP relay
# arm-input: TO        label="Recipient"     required
# arm-input: SUBJECT   label="Subject"       default="ARM {event_type}: {job_title}"
# arm-input: PRIORITY  label="Priority"      values=low,normal,high default=normal
# arm-input: SMTP_PASS label="SMTP password" secret
# arm-input: bad-key   label="ignored"
# arm-input: ARM_X     label="ignored, reserved prefix"
# arm-input: TO        label="Recipient (last wins)" required
set -euo pipefail
"""


def _write(tmp_path: Path, name: str, text: str, executable: bool = True) -> Path:
    p = tmp_path / name
    p.write_text(text)
    if executable:
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return p


@pytest.mark.parametrize("bad", ["", ".", "..", "a/b.sh", "..\\x.sh", "/etc/passwd", "a\x00b"])
def test_validate_script_name_rejects(bad: str) -> None:
    with pytest.raises(ValueError):
        validate_script_name(bad)


def test_resolve_script(tmp_path: Path) -> None:
    assert resolve_script(str(tmp_path), "a.sh") == tmp_path / "a.sh"


def test_parse_header() -> None:
    description, inputs = parse_header(HEADER)
    assert description == "Send an email through the local SMTP relay"
    keys = [i.key for i in inputs]
    assert keys == ["TO", "SUBJECT", "PRIORITY", "SMTP_PASS"]
    to = inputs[0]
    assert (to.label, to.required, to.secret) == ("Recipient (last wins)", True, False)
    assert inputs[1].default == "ARM {event_type}: {job_title}"
    assert (inputs[2].values, inputs[2].default) == (["low", "normal", "high"], "normal")
    assert inputs[3].secret is True and inputs[3].label == "SMTP password"


def test_parse_header_no_metadata_and_label_fallback() -> None:
    assert parse_header("#!/bin/bash\necho hi\n") == ("", [])
    _, inputs = parse_header("# arm-input: TOKEN secret\n")
    assert inputs[0].label == "TOKEN" and inputs[0].secret


def test_parse_header_bad_quotes_line_ignored() -> None:
    _, inputs = parse_header('# arm-input: A label="unterminated\n# arm-input: B\n')
    assert [i.key for i in inputs] == ["B"]


def test_parse_header_ignores_unrecognized_attributes() -> None:
    _, inputs = parse_header('# arm-input: KEY label="Label" unknown_attr default="val"\n')
    assert len(inputs) == 1
    assert inputs[0].key == "KEY" and inputs[0].label == "Label" and inputs[0].default == "val"


def test_parse_header_empty_values_becomes_none() -> None:
    _, inputs = parse_header('# arm-input: KEY values="   , , "\n')
    assert len(inputs) == 1
    assert inputs[0].values is None


def test_parse_header_stops_after_60_lines() -> None:
    text = "\n" * 60 + "# arm-input: LATE\n"
    assert parse_header(text) == ("", [])


def test_read_script_info(tmp_path: Path) -> None:
    _write(tmp_path, "send-email.sh", HEADER)
    info = read_script_info(str(tmp_path), "send-email.sh")
    assert info.name == "send-email.sh" and info.executable and info.size_bytes == len(HEADER.encode())
    assert info.description.startswith("Send an email")
    assert [i.key for i in info.inputs] == ["TO", "SUBJECT", "PRIORITY", "SMTP_PASS"]
    assert info.preview.startswith("#!/usr/bin/env bash")
    assert info.modified_at.tzinfo is not None


def test_read_script_info_preview_capped(tmp_path: Path) -> None:
    _write(tmp_path, "big.sh", "#!/bin/bash\n" + ("x" * 100 + "\n") * 200)
    info = read_script_info(str(tmp_path), "big.sh")
    assert len(info.preview.encode()) <= 8192 and info.preview.count("\n") <= 80


def test_read_script_info_missing_or_dir(tmp_path: Path) -> None:
    (tmp_path / "d.sh").mkdir()
    with pytest.raises(FileNotFoundError):
        read_script_info(str(tmp_path), "nope.sh")
    with pytest.raises(FileNotFoundError):
        read_script_info(str(tmp_path), "d.sh")


def test_read_script_info_binary_safe(tmp_path: Path) -> None:
    p = tmp_path / "bin.sh"
    p.write_bytes(b"#!/bin/bash\n\xff\xfe# arm-hook: still parsed\n")
    p.chmod(0o755)
    assert read_script_info(str(tmp_path), "bin.sh").description == "still parsed"


def test_list_scripts(tmp_path: Path) -> None:
    _write(tmp_path, "b.sh", "# arm-hook: B\n", executable=False)
    _write(tmp_path, "a.sh", "exit 0\n")
    _write(tmp_path, ".hidden", "exit 0\n")
    (tmp_path / "sub").mkdir()
    out = list_scripts(str(tmp_path))
    assert [(s.name, s.executable, s.description) for s in out] == [("a.sh", True, ""), ("b.sh", False, "B")]
    assert list_scripts(str(tmp_path / "missing")) == []
