import socket

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    ARM_DRIVE_DEV: str
    ARM_BACKEND_URL: str
    ARM_SERVICE_TOKEN: str
    ARM_LOG_LEVEL: str = "info"
    HOSTNAME: str = socket.gethostname()
    POLL_INTERVAL_SECONDS: float = 2.0
    # Host-side baseline `--minlength` passed to `makemkvcon mkv all`.
    # Filters very short titles (menu loops, vendor bumpers) without
    # cutting features that don't quite hit v2's 600s default — the
    # smallest non-trivial extras on most discs are 2–5 minutes. A
    # Session can override per-rip via
    # `Session.overrides_json["min_length_seconds"]`; if the backend
    # sends a non-null value in `RipStartResponse.min_length_seconds`,
    # the ripper uses that instead of this baseline.
    ARM_MIN_LENGTH_SECONDS: int = 120


settings = Settings()  # type: ignore[call-arg]  # fields loaded from env by pydantic-settings
