"""container_identity_env: the uid/gid (and render gid) a transcode-family container drops to."""

from __future__ import annotations

from typing import Any

import pytest

from arm_backend.config import Settings
from arm_backend.ripper_container_spec import container_spec as ripper_container_spec
from arm_backend.transcode_container_spec import container_identity_env
from arm_common import Drive, DriveKind, DriveLifecycle, DriveStatus
from arm_common.enums import GpuVendor


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "DATABASE_URL": "postgresql://x:x@localhost/x",
        "ARM_SERVICE_TOKEN": "tok-service",
        "ARM_HOST_RAW_PATH": "/host/raw",
        "ARM_HOST_LOGS_PATH": "/host/logs",
        "ARM_HOST_CERTS_PATH": "/host/certs",
        "ARM_HOST_MEDIA_PATH": "/host/media",
        "ARM_DOCKER_NETWORK": "armv3_default",
        "PUID": "",
        "PGID": "",
        "CDROM_GID": "",
        "ARM_TRANSCODE_PUID": "",
        "ARM_TRANSCODE_PGID": "",
        "ARM_RENDER_GID": "",
    }
    base.update(overrides)
    return Settings.model_construct(**base)


def _drive() -> Drive:
    return Drive(
        id="drv_01JABCDEFGHJKMNPQ",
        hostname="scan-drv_01JABCDEFGHJKMNPQ",
        device_path="/dev/sr0",
        status=DriveStatus.ONLINE,
        lifecycle=DriveLifecycle.ENROLLED,
        serial="AAAABBBB000E",
        by_id_name=None,
        kind=DriveKind.OPTICAL,
        rip_params_json={},
    )


def test_falls_back_to_the_stack_identity_when_no_override() -> None:
    # A local install whose user is not uid 1000: the transcoder must drop to
    # the same uid as every other service, not the entrypoint's 1000 default.
    env = container_identity_env(_settings(PUID="1001", PGID="1001"), None)
    assert env == {"PUID": "1001", "PGID": "1001"}


def test_override_wins_over_the_stack_identity() -> None:
    settings = _settings(PUID="1001", PGID="1001", ARM_TRANSCODE_PUID="2000", ARM_TRANSCODE_PGID="2001")
    assert container_identity_env(settings, None) == {"PUID": "2000", "PGID": "2001"}


def test_each_id_falls_back_on_its_own() -> None:
    settings = _settings(PUID="1001", PGID="1002", ARM_TRANSCODE_PUID="2000")
    assert container_identity_env(settings, None) == {"PUID": "2000", "PGID": "1002"}


def test_omits_ids_when_nothing_is_configured() -> None:
    assert container_identity_env(_settings(), None) == {}


@pytest.mark.parametrize("vendor", [GpuVendor.VAAPI, GpuVendor.QSV])
def test_render_gid_passes_through_for_render_node_vendors(vendor: GpuVendor) -> None:
    env = container_identity_env(_settings(ARM_RENDER_GID="993"), vendor)
    assert env == {"RENDER_GID": "993"}


@pytest.mark.parametrize("vendor", [GpuVendor.NVENC, None])
def test_render_gid_is_dropped_for_other_vendors(vendor: GpuVendor | None) -> None:
    assert container_identity_env(_settings(ARM_RENDER_GID="993"), vendor) == {}


@pytest.mark.parametrize(("puid", "pgid"), [("1000", "1000"), ("1001", "1001"), ("1001", "100")])
def test_transcoder_and_ripper_drop_to_the_same_identity(puid: str, pgid: str) -> None:
    # Contract: every container the backend spawns on the local daemon writes
    # the shared raw/logs/media dirs, so all of them run as one uid:gid unless
    # ARM_TRANSCODE_PUID/PGID deliberately say otherwise.
    settings = _settings(PUID=puid, PGID=pgid, ARM_RIPPER_IMAGE="arm-ripper:test")
    ripper_env = ripper_container_spec(settings, _drive())["environment"]
    transcode_env = container_identity_env(settings, None)
    assert (transcode_env["PUID"], transcode_env["PGID"]) == (ripper_env["PUID"], ripper_env["PGID"])
