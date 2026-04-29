from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    DATABASE_URL: str
    ARM_SERVICE_TOKEN: str
    TLS_CERT_PATH: str = "/etc/ssl/arm/tls.crt"
    TLS_KEY_PATH: str = "/etc/ssl/arm/tls.key"
    ARM_LOG_LEVEL: str = "info"
    BIND_HOST: str = "0.0.0.0"
    BIND_PORT: int = 8443

    # Filesystem root the apply-time collision check stats against. Resolved
    # relative paths (`{title} ({year})/...`) are joined to this; the partial
    # unique index on `transcode_tasks.output_path` is the safety net for races.
    MEDIA_ROOT: str = "/media"

    # Optional .env override for the OMDB key. When set, takes precedence over
    # config.omdb_api_key on every identify call — useful in dev where the
    # secret lives in v3/.env and the Config row stays empty.
    OMDB_API_KEY: str | None = None

    # Comma-separated list of `Origin` header values the WS endpoint accepts
    # from browser clients. Service-token connections (rippers, transcoders)
    # mark themselves with the `arm-service-token` subprotocol and skip this
    # check. `NoDecode` opts the field out of pydantic-settings' default
    # JSON parsing so the validator below sees the raw string.
    ARM_ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = []

    @field_validator("ARM_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


settings = Settings()  # type: ignore[call-arg]  # fields loaded from env by pydantic-settings
