from arm_backend.config import Settings


def _settings(**over: object) -> Settings:
    base = dict(
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        ARM_SERVICE_TOKEN="tok",
    )
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def test_remote_transcode_settings_default_empty() -> None:
    s = _settings()
    assert s.ARM_TRANSCODE_DOCKER_HOST == ""
    assert s.ARM_TRANSCODE_BACKEND_URL == ""


def test_remote_transcode_settings_read_from_env() -> None:
    s = _settings(
        ARM_TRANSCODE_DOCKER_HOST="ssh://sam@transcoder-server",
        ARM_TRANSCODE_BACKEND_URL="https://192.168.0.68:8080",
    )
    assert s.ARM_TRANSCODE_DOCKER_HOST == "ssh://sam@transcoder-server"
    assert s.ARM_TRANSCODE_BACKEND_URL == "https://192.168.0.68:8080"
