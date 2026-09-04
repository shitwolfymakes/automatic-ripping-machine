import socket

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    ARM_DRIVE_DEV: str
    # Identity handed down by the backend when it spawns this ripper.
    # ARM_DRIVE_ID is the Drive row this container serves (registration and
    # heartbeats are keyed to it from Plan 3 on). Required — the backend
    # spawns every ripper for one Drive row (spec §5); there is no
    # hostname-keyed registration. ARM_DRIVE_BY_ID is the exact udev
    # /dev/disk/by-id link name for the physical drive — one readlink
    # resolves it to the current /dev/srN, which is how the ripper follows its
    # drive across a renumbering replug. None => port-identity drive (no by-id
    # link on the host); ARM_DRIVE_DEV is then the hint and is refreshed from
    # the backend while the drive is absent.
    ARM_DRIVE_ID: str
    ARM_DRIVE_BY_ID: str | None = None
    # Where the host's /dev/disk is bind-mounted (read-only). Only the by-id
    # symlink directory is needed; the host's /dev is never mounted whole.
    ARM_HOST_DISK_ROOT: str = "/host-disk"
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
    # Manual-trigger ISO mode. When set, the ripper skips its poll loop,
    # treats the path as the bound device everywhere (registering it as
    # such with the backend), and runs the scan → identify → rip
    # pipeline against the file exactly once. After the pipeline returns
    # the container idles so the WS subscription stays open for
    # cancellation. Intended for local smoke tests against the
    # matrix256-corpus ISOs; production deployments leave this unset.
    ARM_MANUAL_TRIGGER_ISO: str | None = None
    # Tier-4: how often the ripper re-probes makemkv key validity (daily default).
    MAKEMKV_KEYCHECK_INTERVAL_SECONDS: int = 86400
    # Tier-4: consecutive NOT_READY polls before re-arming insert detection.
    # Flaky USB-BD vs cheap optical need different swap-detection windows.
    ARM_NOT_READY_REARM_POLLS: int = 3


settings = Settings()  # type: ignore[call-arg]  # fields loaded from env by pydantic-settings
