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

    # Per-job raw-rip tree; one `raw/<job_id>/` directory per job. Bind-mounted
    # on backend and ripper alike so DELETE /api/jobs can rmtree without an
    # online ripper (the previous WS-hop made deletes silently fail when the
    # owning drive's ripper was offline).
    RAW_ROOT: str = "/raw"

    # Optional .env override for the OMDB key. When set, takes precedence over
    # config.omdb_api_key on every identify call — useful in dev where the
    # secret lives in .env and the Config row stays empty.
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

    # --- Phase 7: transcode dispatcher --------------------------------------
    # How many transcode containers may run in parallel. A 1080p HandBrake
    # transcode pegs every CPU core, so the default is conservative; bump it
    # on a many-core host. Counted live against `transcode_tasks WHERE status
    # = 'in_progress'` so the value survives Backend restarts.
    MAX_PARALLEL_TRANSCODES: int = 1

    # The image name the dispatcher passes to docker. Dev builds it locally and
    # tags it `arm-transcode:latest` (docker compose build arm-transcode-builder);
    # production overrides this with the versioned, pulled image. Compose always
    # sets it, so this default only applies in tests.
    ARM_TRANSCODE_IMAGE: str = "arm-transcode:latest"

    # Stale-claim sweep tunables. 90 s = 3× heartbeat interval (the
    # transcoder POSTs heartbeat every 30 s). After MAX_ATTEMPTS stale resets
    # the task is hard-failed with `last_error="exceeded retry limit ..."`.
    ARM_TRANSCODE_STALE_THRESHOLD_SECONDS: int = 90
    ARM_TRANSCODE_MAX_ATTEMPTS: int = 3

    # Dispatcher tick interval — how often the spawn/sweep loop runs.
    ARM_TRANSCODE_DISPATCH_INTERVAL_SECONDS: int = 5

    # Notification dispatcher tick interval — how often we poll the events
    # table for unsent notifiable events and fire Apprise.
    ARM_NOTIFICATION_DISPATCH_INTERVAL_SECONDS: int = 5

    # Backend container's own host-side mount paths. Required to spawn
    # transcoders via the docker socket: paths in `client.containers.run`'s
    # `volumes=` arg are interpreted by the host docker daemon, NOT by the
    # Backend container. Compose sets these from `${PWD}/{raw,media,...}`
    # at parse time. Empty string disables the dispatcher (used in tests).
    ARM_HOST_RAW_PATH: str = ""
    ARM_HOST_MEDIA_PATH: str = ""
    ARM_HOST_LOGS_PATH: str = ""
    ARM_HOST_CERTS_PATH: str = ""

    # Docker network the spawned transcoder joins so it can reach
    # `https://arm-backend:8443`. Compose default project network is
    # `<project>_default`.
    ARM_DOCKER_NETWORK: str = "armv3_default"

    # --- Phase 7b: GPU inventory --------------------------------------------
    # JSON array of GPUs detected host-side at install time (install.sh /
    # setup-dev.sh enumerate /dev/dri + nvidia-smi and write this). The backend
    # parses it at lifespan startup to fill the `gpus` table — it does NOT probe
    # hardware itself. Empty/absent => CPU-only transcoding. See gpu_probe.py
    # for the schema. Re-run the installer after a GPU/driver change.
    ARM_GPUS: str = ""


settings = Settings()  # type: ignore[call-arg]  # fields loaded from env by pydantic-settings
