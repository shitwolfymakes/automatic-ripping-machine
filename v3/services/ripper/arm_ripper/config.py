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


settings = Settings()  # type: ignore[call-arg]  # fields loaded from env by pydantic-settings
