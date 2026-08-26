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

    # Sandbox root for ISO-import scanning (kept for the diagnostics path
    # check; the iso-scan endpoint itself was dropped upstream in favor of
    # the ephemeral-worker design).
    ISO_INGRESS_ROOT: str = "/ingress"

    # Disk cache for the image-proxy router (GET /api/images/proxy). Posters
    # fetched from allowlisted external hosts are cached here (LRU + 7-day TTL)
    # so the UI can load them without browser CORS/ORB issues. Bind-mount a
    # volume here in compose.
    ARM_IMAGE_CACHE_PATH: str = "/data/cache/images"

    # User-uploaded themes live here (bind-mounted via ./arm/themes:/data/themes).
    # Built-in themes are a frontend concern — tokens compiled into the UI, CSS
    # served as static assets — so the backend stores only user themes.
    ARM_THEMES_PATH: str = "/data/themes"

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

    # The image name the dispatcher passes to docker. Dev builds it locally as
    # arm-transcode:latest (the arm-transcode compose service, deploy.replicas:0,
    # built by `docker compose up --build` but never run); production overrides
    # this with the versioned, pulled image. Compose always sets it, so this
    # default only applies in tests.
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

    # Public URL of the image Apprise attaches to outbound notifications
    # (e.g. the Discord avatar / embed thumbnail). MUST be reachable by the
    # notification service (Discord/Slack fetch it server-side), so a LAN-only
    # URL won't render. Empty (default) attaches no image — the sender is still
    # labelled "ARM" via the AppriseAsset app_id. Set this in compose/.env to a
    # public ARM logo URL to brand the notifications.
    ARM_NOTIFY_IMAGE_URL: str = ""

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

    # Remote transcode offload. When ARM_TRANSCODE_DOCKER_HOST is set (e.g.
    # "ssh://sam@transcoder-server"), the transcode dispatcher's docker client
    # targets that daemon so containers spawn on a remote GPU host; empty =
    # local socket (docker.from_env), unchanged. ARM_TRANSCODE_BACKEND_URL is
    # the routable ARM_BACKEND_URL injected into a remote-spawned transcoder
    # (the docker-DNS "arm-backend" name won't resolve off the backend host);
    # empty = keep the local "https://arm-backend:8443".
    ARM_TRANSCODE_DOCKER_HOST: str = ""
    ARM_TRANSCODE_BACKEND_URL: str = ""

    # PUID/PGID the spawned transcoder drops to (the entrypoint reads these;
    # empty = its own default, current behavior unchanged). Set these when the
    # transcoder writes to shared storage owned by a uid/gid that differs from
    # the backend's PUID — e.g. a remote NFS export whose media dir is owned by
    # a specific NAS user. Without this the entrypoint chowns /media to its
    # default uid every run, which can revert externally-set ownership.
    ARM_TRANSCODE_PUID: str = ""
    ARM_TRANSCODE_PGID: str = ""

    # --- Phase 7b: GPU inventory --------------------------------------------
    # JSON array of GPUs detected host-side at install time (install.sh /
    # setup-dev.sh enumerate /dev/dri + nvidia-smi and write this). The backend
    # parses it at lifespan startup to fill the `gpus` table — it does NOT probe
    # hardware itself. Empty/absent => CPU-only transcoding. See gpu_probe.py
    # for the schema. Re-run the installer after a GPU/driver change.
    # Default "[]" so config.py, .env.example, and compose all agree on the
    # canonical "no GPUs" value; gpu_probe treats "" and "[]" identically (it
    # short-circuits blank input before json.loads).
    ARM_GPUS: str = "[]"

    # GID of the host's /dev/dri render node group (detected host-side, like
    # CDROM_GID for the ripper). The dispatcher adds it via `group_add` to each
    # VAAPI/QSV transcoder so the PUID-dropped process can open the render node
    # (root:render 0660) — without it HandBrake's QSV/VAAPI init fails with
    # "failed to create hwdevice". Empty => no group added (CPU / NVENC-only).
    ARM_RENDER_GID: str = ""

    # --- Tier-3 air-gap: external metadata API base URLs --------------------
    # Default to the public endpoints; override to point at a mirror/proxy for
    # air-gapped or regional deployments. No trailing-slash normalization — set
    # them exactly as the client expects (matching the former module literals).
    ARM_TMDB_BASE_URL: str = "https://api.themoviedb.org/3"
    ARM_OMDB_BASE_URL: str = "https://www.omdbapi.com/"
    ARM_TVDB_BASE_URL: str = "https://api4.thetvdb.com/v4"
    ARM_MUSICBRAINZ_BASE_URL: str = "https://musicbrainz.org/ws/2"
    ARM_ARMSERVER_BASE_URL: str = "https://1337server.pythonanywhere.com/api/v1/"

    # Tier-3: additional hostnames the image-proxy allowlist accepts, on TOP of
    # the built-in set (never replacing it — the allowlist is an SSRF guard).
    # Comma-separated bare hostnames (no scheme/path). Empty => built-ins only.
    ARM_EXTRA_IMAGE_HOSTS: Annotated[list[str], NoDecode] = []

    @field_validator("ARM_EXTRA_IMAGE_HOSTS", mode="before")
    @classmethod
    def _split_extra_image_hosts(cls, v: object) -> object:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    # --- Tier-4: image-proxy disk-cache caps -------------------------------
    # Homelab vs large installs differ; safe defaults match the former
    # hardcoded constants in image_cache.py.
    ARM_IMAGE_CACHE_MAX_ENTRIES: int = 1000
    ARM_IMAGE_CACHE_MAX_BYTES: int = 2 * 1024 * 1024  # 2 MB
    ARM_IMAGE_CACHE_TTL_SECONDS: int = 7 * 24 * 3600  # 7 days

    # --- Tier-4: log query/zip caps ----------------------------------------
    # Multi-drive deployments outgrow the defaults; safe defaults match the
    # former hardcoded constants in routers/logs.py.
    ARM_LOG_PER_FILE_DEFAULT: int = 1000
    ARM_LOG_PER_FILE_HARD_CAP: int = 10_000
    ARM_LOG_ZIP_PER_ENTRY_LINE_CAP: int = 5000
    ARM_LOG_ZIP_PER_ENTRY_BYTE_CAP: int = 5 * 1024 * 1024  # 5 MB


settings = Settings()  # type: ignore[call-arg]  # fields loaded from env by pydantic-settings
