"""Effective transcode capability: env flag OR a configured remote docker host."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.config import Settings, effective_transcode_capable  # noqa: E402


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "DATABASE_URL": "postgresql://x:x@localhost/x",
        "ARM_SERVICE_TOKEN": "tok-service",
    }
    base.update(overrides)
    return Settings.model_construct(**base)


def test_capable_by_default() -> None:
    assert effective_transcode_capable(_settings(ARM_TRANSCODE_CAPABLE=True, ARM_TRANSCODE_DOCKER_HOST="")) is True


def test_ripper_only_not_capable() -> None:
    assert effective_transcode_capable(_settings(ARM_TRANSCODE_CAPABLE=False, ARM_TRANSCODE_DOCKER_HOST="")) is False


def test_remote_docker_host_implies_capability() -> None:
    s = _settings(ARM_TRANSCODE_CAPABLE=False, ARM_TRANSCODE_DOCKER_HOST="ssh://sam@transcoder-server")
    assert effective_transcode_capable(s) is True
