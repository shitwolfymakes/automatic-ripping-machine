"""Transcoder config — env-var binding + ws-url derivation."""

from __future__ import annotations

import pytest

from arm_transcode.config import TranscoderConfig


def test_required_env_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARM_TRANSCODE_TASK_ID", "txt_abc")
    monkeypatch.setenv("ARM_BACKEND_URL", "https://arm-backend:8443")
    monkeypatch.setenv("ARM_SERVICE_TOKEN", "tok-12345")
    monkeypatch.setenv("HOSTNAME", "arm-transcode-xyz")
    cfg = TranscoderConfig()
    assert cfg.task_id == "txt_abc"
    assert cfg.backend_url == "https://arm-backend:8443"
    assert cfg.service_token == "tok-12345"
    assert cfg.hostname == "arm-transcode-xyz"


def test_https_ws_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARM_TRANSCODE_TASK_ID", "txt_abc")
    monkeypatch.setenv("ARM_BACKEND_URL", "https://arm-backend:8443")
    monkeypatch.setenv("ARM_SERVICE_TOKEN", "tok")
    monkeypatch.setenv("HOSTNAME", "h")
    assert TranscoderConfig().ws_url == "wss://arm-backend:8443/ws"


def test_missing_var_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARM_TRANSCODE_TASK_ID", raising=False)
    with pytest.raises(RuntimeError, match="ARM_TRANSCODE_TASK_ID"):
        TranscoderConfig()
