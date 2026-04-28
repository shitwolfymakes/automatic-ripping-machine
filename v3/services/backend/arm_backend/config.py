from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    DATABASE_URL: str
    ARM_SERVICE_TOKEN: str
    TLS_CERT_PATH: str = "/etc/ssl/arm/tls.crt"
    TLS_KEY_PATH: str = "/etc/ssl/arm/tls.key"
    ARM_LOG_LEVEL: str = "info"
    BIND_HOST: str = "0.0.0.0"
    BIND_PORT: int = 8443

    # Optional .env override for the OMDB key. When set, takes precedence over
    # config.omdb_api_key on every identify call — useful in dev where the
    # secret lives in v3/.env and the Config row stays empty.
    OMDB_API_KEY: str | None = None


settings = Settings()  # type: ignore[call-arg]  # fields loaded from env by pydantic-settings
