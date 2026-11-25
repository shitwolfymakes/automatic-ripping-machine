"""The minimum title length: the configured value, or the ripper env value that seeds it."""

from arm_common import Config

# MakeMKV's own default, used when nothing else is set.
DEFAULT_MIN_TITLE_LENGTH_SECONDS = 120


def env_min_title_length_seconds() -> int:
    """The ARM_RIPPER_MIN_LENGTH_SECONDS env value that seeds the setting, or the default when it is unset or not a
    whole number of seconds."""
    from arm_backend.config import settings  # noqa: PLC0415 — avoid import cycle at module load

    raw = settings.ARM_RIPPER_MIN_LENGTH_SECONDS.strip()
    if not raw.isdigit():
        return DEFAULT_MIN_TITLE_LENGTH_SECONDS
    return int(raw)


def min_title_length_seconds(cfg: Config) -> int:
    """The configured minimum title length, or the env seed for a row not yet seeded."""
    if cfg.min_title_length_seconds is None:
        return env_min_title_length_seconds()
    return int(cfg.min_title_length_seconds)
