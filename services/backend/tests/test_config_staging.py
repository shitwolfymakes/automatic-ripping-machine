"""`staging_root` and `effective_staging_host_path`: where the backend reaches staging (D26)."""

from __future__ import annotations

from pathlib import Path

import pytest

from arm_backend.config import (
    Settings,
    effective_staging_host_path,
    root_host_path,
    settings as base_settings,
    staging_inside_raw,
    staging_root,
)


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


@pytest.mark.parametrize(
    ("host_staging", "expected"),
    [
        ("", True),
        ("/data/raw", True),
        ("/data/raw/.staging", True),
        ("/data/raw2", False),
        ("/data/staging", False),
    ],
)
def test_staging_inside_raw(host_staging: str, expected: bool) -> None:
    assert staging_inside_raw(_cfg(ARM_HOST_RAW_PATH="/data/raw", ARM_HOST_STAGING_PATH=host_staging)) is expected


@pytest.mark.parametrize(
    ("name", "update", "expected"),
    [
        ("MEDIA_ROOT", {"ARM_HOST_MEDIA_PATH": "/h/media"}, "/h/media"),
        ("MEDIA_ROOT", {"ARM_HOST_MEDIA_PATH": ""}, None),
        ("RAW_ROOT", {"ARM_HOST_RAW_PATH": "/h/raw"}, "/h/raw"),
        ("LOG_DIR", {"ARM_HOST_LOGS_PATH": "/h/logs"}, "/h/logs"),
        ("STAGING_ROOT", {"ARM_HOST_RAW_PATH": "/h/raw"}, "/h/raw/.staging"),
        ("STAGING_ROOT", {"ARM_HOST_RAW_PATH": "/h/raw", "ARM_HOST_STAGING_PATH": "/h/stage"}, "/h/stage"),
        ("STAGING_ROOT", {"ARM_HOST_RAW_PATH": ""}, None),
        ("ISO_INGRESS_ROOT", {}, None),
    ],
)
def test_root_host_path(name: str, update: dict[str, str], expected: str | None) -> None:
    assert root_host_path(name, _cfg(**update)) == expected
