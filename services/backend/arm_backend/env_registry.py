"""Classification of every `Settings` field for the system environment report.

Fail closed: a unit test requires each `Settings` field to be listed here, and
container env keys are masked unless named in `CONTAINER_PUBLIC_ENV`.
"""

from dataclasses import dataclass

ENV_GROUP_ORDER: tuple[str, ...] = (
    "Paths",
    "Server",
    "Images",
    "Ripper",
    "Transcode",
    "Providers",
    "Limits",
    "IDs",
    "Logging",
)


@dataclass(frozen=True)
class EnvVarMeta:
    group: str
    secret: bool = False
    url: bool = False
    # Key of the DB setting this env var only seeds (a `CONFIG_FIELD_META` key,
    # or "gpus" for ARM_GPUS); None when the env var is the live value.
    seed_of: str | None = None


def _paths(*names: str) -> dict[str, EnvVarMeta]:
    return {n: EnvVarMeta("Paths") for n in names}


def _group(group: str, *names: str, url: bool = False) -> dict[str, EnvVarMeta]:
    return {n: EnvVarMeta(group, url=url) for n in names}


ENV_REGISTRY: dict[str, EnvVarMeta] = {
    "DATABASE_URL": EnvVarMeta("Server", secret=True),
    "ARM_SERVICE_TOKEN": EnvVarMeta("Server", secret=True),
    "TLS_CERT_PATH": EnvVarMeta("Server", secret=True),
    "TLS_KEY_PATH": EnvVarMeta("Server", secret=True),
    **_paths(
        "MEDIA_ROOT",
        "RAW_ROOT",
        "ARM_SCRIPTS_ROOT",
        "ISO_INGRESS_ROOT",
        "ARM_IMAGE_CACHE_PATH",
        "ARM_THEDISCDB_PATH",
        "ARM_THEMES_PATH",
        "ARM_HOST_RAW_PATH",
        "ARM_HOST_MEDIA_PATH",
        "ARM_HOST_LOGS_PATH",
        "ARM_HOST_CERTS_PATH",
        "ARM_HOST_ISO_LIBRARY_PATH",
        "ARM_HOST_DISK_ROOT",
        "ARM_RIPPER_CERTS_PATH",
    ),
    **_group(
        "Server",
        "BIND_HOST",
        "BIND_PORT",
        "ARM_ALLOWED_ORIGINS",
        "ARM_DOCKER_NETWORK",
        "ARM_SYSFS_ROOT",
        "ARM_TRANSCODE_BACKEND_URL_CHECK",
    ),
    **_group("Server", "ARM_TRANSCODE_DOCKER_HOST", "ARM_TRANSCODE_BACKEND_URL", url=True),
    **_group(
        "Images",
        "ARM_TRANSCODE_IMAGE",
        "ARM_TRANSCODE_IMAGE_QSV",
        "ARM_TRANSCODE_IMAGE_VAAPI",
        "ARM_TRANSCODE_IMAGE_NVENC",
        "ARM_RIPPER_IMAGE",
    ),
    **_group("Images", "ARM_NOTIFY_IMAGE_URL", url=True),
    **_group(
        "Ripper",
        "ARM_RIPPER_POLL_INTERVAL_SECONDS",
        "ARM_RIPPER_MIN_LENGTH_SECONDS",
        "ARM_RIPPER_MAKEMKV_KEYCHECK_INTERVAL_SECONDS",
        "ARM_RIPPER_NOT_READY_REARM_POLLS",
        "ARM_RIPPER_OPTICAL_SR_MAX",
        "ARM_RIPPER_OPTICAL_SG_MAX",
    ),
    **_group(
        "Transcode",
        "ARM_TRANSCODE_STALE_THRESHOLD_SECONDS",
        "ARM_TRANSCODE_MAX_ATTEMPTS",
        "ARM_TRANSCODE_DISPATCH_INTERVAL_SECONDS",
        "ARM_NOTIFICATION_DISPATCH_INTERVAL_SECONDS",
        "ARM_TRANSCODE_CAPABLE",
    ),
    "MAX_PARALLEL_TRANSCODES": EnvVarMeta("Transcode", seed_of="max_parallel_transcodes"),
    "ARM_GPUS": EnvVarMeta("Transcode", seed_of="gpus"),
    **_group(
        "Providers",
        "ARM_TMDB_BASE_URL",
        "ARM_OMDB_BASE_URL",
        "ARM_TVDB_BASE_URL",
        "ARM_TVMAZE_BASE_URL",
        "ARM_MUSICBRAINZ_BASE_URL",
        "ARM_ARMSERVER_BASE_URL",
        url=True,
    ),
    **_group("Providers", "ARM_EXTRA_IMAGE_HOSTS"),
    **_group(
        "Limits",
        "ARM_IMAGE_CACHE_MAX_ENTRIES",
        "ARM_IMAGE_CACHE_MAX_BYTES",
        "ARM_IMAGE_CACHE_TTL_SECONDS",
        "ARM_LOG_PER_FILE_DEFAULT",
        "ARM_LOG_PER_FILE_HARD_CAP",
        "ARM_LOG_ZIP_PER_ENTRY_LINE_CAP",
        "ARM_LOG_ZIP_PER_ENTRY_BYTE_CAP",
    ),
    **_group(
        "IDs",
        "PUID",
        "PGID",
        "CDROM_GID",
        "ARM_TRANSCODE_PUID",
        "ARM_TRANSCODE_PGID",
        "ARM_RENDER_GID",
    ),
    "ARM_LOG_LEVEL": EnvVarMeta("Logging"),
}

# Non-secret keys the ripper and transcode container specs emit. Every other
# container env key is masked.
CONTAINER_PUBLIC_ENV: frozenset[str] = frozenset(
    {
        "ARM_DRIVE_ID",
        "ARM_DRIVE_DEV",
        "ARM_DRIVE_BY_ID",
        "ARM_HOST_DISK_ROOT",
        "ARM_SOURCE_PATH",
        "ARM_SOURCE_SESSION_ID",
        "ARM_BACKEND_URL",
        "ARM_LOG_LEVEL",
        "ARM_SERVICE_NAME",
        "ARM_TRANSCODE_TASK_ID",
        "PUID",
        "PGID",
        "CDROM_GID",
        "RENDER_GID",
        "POLL_INTERVAL_SECONDS",
        "ARM_MIN_LENGTH_SECONDS",
        "MAKEMKV_KEYCHECK_INTERVAL_SECONDS",
        "ARM_NOT_READY_REARM_POLLS",
        "ARM_OPTICAL_SR_MAX",
        "ARM_OPTICAL_SG_MAX",
        "ARM_TRANSCODE_ENCODER",
        "ARM_GPU_VENDOR",
        "ARM_GPU_DEVICE",
        "ARM_GPU_CODEC",
    }
)
