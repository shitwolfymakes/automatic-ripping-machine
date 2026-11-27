"""Rip behaviour settings: a global default on Config, a per-drive override on Drive.

A NULL on the drive follows the global, the same shape as `drive_mode` over `auto_rip_on_insert`. Each setting has one
resolver here, so a rip start and a resume read the same answer.
"""

from arm_common import Config, Drive


def resolve_end_on_completion(cfg: Config | None, drive: Drive | None) -> bool:
    """Whether a makemkvcon run may be ended once it reports the copy complete and its files are closed: the drive's
    own setting when it has one, else the global. No config row reads as the shipped default, off."""
    if drive is not None and drive.rip_end_on_completion_message is not None:
        return drive.rip_end_on_completion_message
    return cfg is not None and bool(cfg.rip_end_on_completion_message)
