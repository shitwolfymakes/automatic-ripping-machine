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


settings = Settings()
