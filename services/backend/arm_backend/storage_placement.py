"""Where the staging area sits relative to the raw folder.

Two binds of one disk cannot hard link (EXDEV), so a stage outside raw is a full copy unless
it lives on its own device. The pure decision is `staging_placement`; `root_placement` stats the
two roots and applies it to the staging root only."""

import os

from arm_backend.config import Settings, staging_inside_raw
from arm_common.schemas import StoragePlacement

STAGING_ROOT_NAME = "STAGING_ROOT"
RAW_ROOT_NAME = "RAW_ROOT"


def staging_placement(inside: bool, staging_dev: int | None, raw_dev: int | None) -> StoragePlacement | None:
    """Placement of staging relative to raw, or None when a device id is unknown."""
    if inside:
        return StoragePlacement.INSIDE_RAW
    if staging_dev is None or raw_dev is None:
        return None
    return StoragePlacement.SAME_DEVICE if staging_dev == raw_dev else StoragePlacement.SEPARATE_DEVICE


def _device_of(path: str | None) -> int | None:
    """The st_dev of `path`, or None when it cannot be stat-ed."""
    if not path:
        return None
    try:
        return os.stat(path).st_dev
    except OSError:
        return None


def root_placement(name: str, roots: dict[str, str], s: Settings) -> StoragePlacement | None:
    """The placement of the named root: set only for the staging root."""
    if name != STAGING_ROOT_NAME:
        return None
    return staging_placement(
        staging_inside_raw(s), _device_of(roots.get(STAGING_ROOT_NAME)), _device_of(roots.get(RAW_ROOT_NAME))
    )
