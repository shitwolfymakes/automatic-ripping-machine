import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

from arm_ripper.config import Settings  # noqa: E402


def _settings(**over):
    base = dict(ARM_DRIVE_DEV="/dev/sr0", ARM_BACKEND_URL="https://b", ARM_SERVICE_TOKEN="t")
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def test_tunables_default_to_current_values():
    s = _settings()
    assert s.MAKEMKV_KEYCHECK_INTERVAL_SECONDS == 86400
    assert s.ARM_NOT_READY_REARM_POLLS == 3


def test_tunables_overridable(monkeypatch):
    monkeypatch.setenv("MAKEMKV_KEYCHECK_INTERVAL_SECONDS", "3600")
    monkeypatch.setenv("ARM_NOT_READY_REARM_POLLS", "5")
    s = Settings(ARM_DRIVE_DEV="/dev/sr0", ARM_BACKEND_URL="https://b", ARM_SERVICE_TOKEN="t")  # type: ignore[arg-type]
    assert s.MAKEMKV_KEYCHECK_INTERVAL_SECONDS == 3600
    assert s.ARM_NOT_READY_REARM_POLLS == 5
