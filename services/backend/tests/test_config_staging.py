"""`staging_root` and `effective_staging_host_path`: where the backend reaches staging (D26)."""

from __future__ import annotations

from pathlib import Path

import pytest

from arm_backend.config import Settings, effective_staging_host_path, settings as base_settings, staging_root


def _cfg(**update: str) -> Settings:
    return base_settings.model_copy(update={"RAW_ROOT": "/raw", "STAGING_ROOT": "/staging", **update})


@pytest.mark.parametrize(
    ("host_raw", "host_staging", "expected"),
    [
        ("/data/raw", "", "/raw/.staging"),  # unset: inside raw
        ("/data/raw", "/data/raw/.staging", "/raw/.staging"),  # the default spelled out
        ("/data/raw", "/data/raw/stage/here", "/raw/stage/here"),  # under raw
        ("/data/raw", "/data/raw/", "/raw/.staging"),  # raw itself is no staging area
        ("/data/raw", "/data/raw//x/../y", "/raw/y"),  # compared as normalised paths
        ("/data/raw", "/data/staging", "/staging"),  # elsewhere: its own mount
        ("/data/raw", "/data/raw2", "/staging"),  # a sibling that shares a prefix is not under raw
    ],
)
def test_staging_root(host_raw: str, host_staging: str, expected: str) -> None:
    cfg = _cfg(ARM_HOST_RAW_PATH=host_raw, ARM_HOST_STAGING_PATH=host_staging)
    assert staging_root(cfg) == Path(expected)


def test_effective_staging_host_path_defaults_to_raw_subdir() -> None:
    assert effective_staging_host_path(_cfg(ARM_HOST_RAW_PATH="/data/raw")) == "/data/raw/.staging"


def test_effective_staging_host_path_prefers_the_configured_path() -> None:
    cfg = _cfg(ARM_HOST_RAW_PATH="/data/raw", ARM_HOST_STAGING_PATH="/mnt/stage")
    assert effective_staging_host_path(cfg) == "/mnt/stage"
