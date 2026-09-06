from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from arm_backend.notifications.bash_hook import (
    HookError,
    masked,
    mask_bash_config,
    merge_bash_config,
    prepare_run,
    redact_secrets,
    storage_config,
)

HEADER = (
    "#!/usr/bin/env bash\n"
    '# arm-input: TO label="Recipient" required\n'
    '# arm-input: SUBJECT default="ARM {event_type}: {job_title}"\n'
    "# arm-input: PRIORITY values=low,normal,high default=normal\n"
    "# arm-input: SMTP_PASS secret\n"
)
CTX = {"event_type": "rip.failed", "job_title": "Dune", "drive_id": "sr0"}


def _script(tmp_path: Path, name: str = "send-email.sh", text: str = HEADER) -> Path:
    p = tmp_path / name
    p.write_text(text)
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return p


def _config(**over) -> dict:
    cfg = {
        "type": "bash",
        "script": "send-email.sh",
        "timeout_seconds": 20,
        "inputs": {"TO": "me@x", "SMTP_PASS": "pw"},
        "secret_keys": ["SMTP_PASS"],
    }
    cfg.update(over)
    return cfg


def _prep(tmp_path: Path, config: dict, template: dict | None = None):
    return prepare_run(
        config=config,
        template=template,
        event_type="rip.failed",
        default_title="ARM: rip failed - {job_title}",
        default_body="{job_title} failed on {drive_id}",
        context=CTX,
        scripts_root=str(tmp_path),
        media_root="/media",
        raw_root="/raw",
    )


def test_prepare_run_resolves_defaults_config_and_event_override(tmp_path: Path) -> None:
    _script(tmp_path)
    run = _prep(tmp_path, _config(), {"title": "custom {job_title}", "inputs": {"TO": "oncall@x", "PRIORITY": "high"}})
    assert run.path == tmp_path / "send-email.sh"
    assert run.argv == ["/usr/bin/env", "bash", str(run.path), "custom Dune", "Dune failed on sr0"]
    assert run.inputs == {"TO": "oncall@x", "SUBJECT": "ARM rip.failed: Dune", "PRIORITY": "high", "SMTP_PASS": "pw"}
    assert run.env["TO"] == "oncall@x" and run.env["ARM_JOB_TITLE"] == "Dune" and run.env["ARM_TITLE"] == "custom Dune"
    assert run.secret_keys == frozenset({"SMTP_PASS"}) and run.timeout_seconds == 20


def test_prepare_run_event_override_cannot_touch_secrets(tmp_path: Path) -> None:
    _script(tmp_path)
    run = _prep(tmp_path, _config(), {"inputs": {"SMTP_PASS": "leak"}})
    assert run.inputs["SMTP_PASS"] == "pw"


def test_prepare_run_missing_required_input(tmp_path: Path) -> None:
    _script(tmp_path)
    with pytest.raises(HookError, match="input TO is required"):
        _prep(tmp_path, _config(inputs={}))


def test_prepare_run_rejects_choice_outside_values(tmp_path: Path) -> None:
    _script(tmp_path)
    with pytest.raises(HookError, match="PRIORITY must be one of low, normal, high"):
        _prep(tmp_path, _config(inputs={"TO": "a", "PRIORITY": "urgent"}))


def test_prepare_run_template_errors(tmp_path: Path) -> None:
    _script(tmp_path)
    with pytest.raises(HookError, match="unknown variable"):
        _prep(tmp_path, _config(), {"title": "{nope}"})
    with pytest.raises(HookError, match="input SUBJECT"):
        _prep(tmp_path, _config(inputs={"TO": "a", "SUBJECT": "{nope}"}))


def test_prepare_run_bad_name_and_missing_file(tmp_path: Path) -> None:
    with pytest.raises(HookError, match="file name"):
        _prep(tmp_path, _config(script="../x.sh"))
    # Missing file: still prepares (the runner reports "script not found"); no header means no inputs at all.
    run = _prep(tmp_path, _config(script="gone.sh"))
    assert run.inputs == {} and run.path.name == "gone.sh"


def test_prepare_run_drops_undeclared_config_inputs(tmp_path: Path) -> None:
    _script(tmp_path, "plain.sh", "#!/bin/bash\nexit 0\n")
    run = _prep(tmp_path, _config(script="plain.sh", inputs={"FOO": "bar"}, secret_keys=[]))
    assert run.inputs == {} and "FOO" not in run.env


def test_prepare_run_ignores_reserved_and_undeclared_keys(tmp_path: Path) -> None:
    _script(tmp_path)
    run = _prep(tmp_path, _config(inputs={"BASH_ENV": "/tmp/x", "PATH": "/tmp/evil", "TO": "a"}))
    assert "BASH_ENV" not in run.env
    assert run.env["PATH"] == os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")
    assert run.inputs["TO"] == "a"
    assert "BASH_ENV" not in run.inputs and "PATH" not in run.inputs


def test_prepare_run_optional_choice_without_default_stays_blank(tmp_path: Path) -> None:
    _script(tmp_path, "mode.sh", "#!/bin/bash\n# arm-input: MODE values=a,b\n")
    run = _prep(tmp_path, _config(script="mode.sh", inputs={}, secret_keys=[]))
    assert run.inputs == {"MODE": ""} and run.env["MODE"] == ""


def test_redact_secrets(tmp_path: Path) -> None:
    _script(tmp_path)
    run = _prep(tmp_path, _config(inputs={"TO": "a", "SMTP_PASS": "s3cret"}))
    assert redact_secrets("failed: pw=s3cret", run) == "failed: pw=<hidden>"
    # An empty secret value is not substituted (it would redact everything).
    blank = _prep(tmp_path, _config(inputs={"TO": "a"}, secret_keys=["SMTP_PASS"]))
    assert redact_secrets("nothing to hide", blank) == "nothing to hide"


def test_masked(tmp_path: Path) -> None:
    _script(tmp_path)
    inputs, env = masked(_prep(tmp_path, _config()))
    assert inputs["SMTP_PASS"] == "<hidden>" and env["SMTP_PASS"] == "<hidden>" and inputs["TO"] == "me@x"


def test_mask_and_merge_config() -> None:
    stored = _config()
    m = mask_bash_config(stored)
    assert m["inputs"] == {"TO": "me@x", "SMTP_PASS": "<hidden>"} and stored["inputs"]["SMTP_PASS"] == "pw"
    merged = merge_bash_config(stored, _config(inputs={"TO": "new@x", "SMTP_PASS": "<hidden>"}))
    assert merged["inputs"] == {"TO": "new@x", "SMTP_PASS": "pw"}
    replaced = merge_bash_config(stored, _config(inputs={"TO": "new@x", "SMTP_PASS": "pw2"}))
    assert replaced["inputs"]["SMTP_PASS"] == "pw2"
    dropped = merge_bash_config(stored, _config(inputs={"TO": "x"}))
    assert "SMTP_PASS" not in dropped["inputs"]
    assert mask_bash_config({"type": "bash", "script": "a.sh"})["inputs"] == {}


def test_storage_config(tmp_path: Path) -> None:
    _script(tmp_path)
    out = storage_config(
        {
            "type": "bash",
            "script": "send-email.sh",
            "inputs": {"TO": "a", "SMTP_PASS": "p", "bad key": "x"},
            "secret_keys": [],
        },
        str(tmp_path),
    )
    assert out == {
        "type": "bash",
        "script": "send-email.sh",
        "timeout_seconds": 30,
        "inputs": {"TO": "a", "SMTP_PASS": "p"},
        "secret_keys": ["SMTP_PASS"],
    }
    # Missing file keeps the caller's secret_keys so masking survives a removed script.
    kept = storage_config(
        {"type": "bash", "script": "gone.sh", "inputs": {}, "secret_keys": ["X"], "timeout_seconds": 5}, str(tmp_path)
    )
    assert kept["secret_keys"] == ["X"] and kept["timeout_seconds"] == 5
    with pytest.raises(HookError):
        storage_config({"type": "bash", "script": "a/b.sh"}, str(tmp_path))
    with pytest.raises(HookError, match="timeout"):
        storage_config({"type": "bash", "script": "send-email.sh", "timeout_seconds": 0}, str(tmp_path))
