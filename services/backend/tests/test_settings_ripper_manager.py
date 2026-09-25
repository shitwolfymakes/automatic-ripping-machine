from __future__ import annotations

from arm_backend.config import Settings


def _settings(**overrides: str) -> Settings:
    base = {"DATABASE_URL": "postgresql://x:x@localhost/x", "ARM_SERVICE_TOKEN": "tok-service"}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_ripper_manager_settings_defaults() -> None:
    s = _settings()
    assert s.ARM_RIPPER_IMAGE == "arm-ripper:latest"
    assert s.PUID == "" and s.PGID == "" and s.CDROM_GID == ""


def test_ripper_manager_settings_from_env() -> None:
    s = _settings(ARM_RIPPER_IMAGE="armv3-local/arm-ripper:x", PUID="1001", PGID="1000", CDROM_GID="24")
    assert s.ARM_RIPPER_IMAGE == "armv3-local/arm-ripper:x"
    assert (s.PUID, s.PGID, s.CDROM_GID) == ("1001", "1000", "24")


def test_ripper_tunable_passthroughs_default_empty() -> None:
    s = _settings()
    for key in (
        "ARM_RIPPER_POLL_INTERVAL_SECONDS",
        "ARM_RIPPER_MIN_LENGTH_SECONDS",
        "ARM_RIPPER_MAKEMKV_KEYCHECK_INTERVAL_SECONDS",
        "ARM_RIPPER_NOT_READY_REARM_POLLS",
        "ARM_RIPPER_OPTICAL_SR_MAX",
        "ARM_RIPPER_OPTICAL_SG_MAX",
    ):
        assert getattr(s, key) == ""
