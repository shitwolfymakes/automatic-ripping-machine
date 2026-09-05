from __future__ import annotations

import logging
import os
from typing import Any
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import docker.errors  # noqa: E402
import pytest  # noqa: E402

from arm_backend.config import Settings  # noqa: E402
from arm_backend.ripper_manager import (  # noqa: E402
    DOCKER_LABEL_KEY,
    ReconcileSummary,
    RipperManager,
    RipperManagerError,
)
from arm_common import Drive, DriveLifecycle, DriveStatus  # noqa: E402


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "DATABASE_URL": "postgresql://x:x@localhost/x",
        "ARM_SERVICE_TOKEN": "tok-service",
        "ARM_HOST_RAW_PATH": "/host/raw",
        "ARM_HOST_LOGS_PATH": "/host/logs",
        "ARM_HOST_CERTS_PATH": "/host/certs",
        "ARM_HOST_MEDIA_PATH": "/host/media",
        "ARM_DOCKER_NETWORK": "armv3_default",
        "ARM_RIPPER_IMAGE": "arm-ripper:test",
        "ARM_LOG_LEVEL": "debug",
    }
    base.update(overrides)
    return Settings(**base)


def _manager(**overrides: Any) -> tuple[RipperManager, MagicMock]:
    client = MagicMock()
    client.containers.list.return_value = []
    client.images.get.return_value.id = "sha256:same"
    return RipperManager(_settings(**overrides), client), client


def _drive(
    drive_id: str = "drv_01JABCDEFGHJKMNPQ",
    serial: str | None = "AAAABBBB000E",
    by_id_name: str | None = "usb-PIONEER_BD-RW_BDR-S12JX_AAAABBBB000E-0:0",
    device_path: str = "/dev/sr0",
) -> Drive:
    return Drive(
        id=drive_id,
        hostname=f"scan-{drive_id}",
        device_path=device_path,
        status=DriveStatus.ONLINE,
        lifecycle=DriveLifecycle.ENROLLED,
        serial=serial,
        by_id_name=by_id_name,
    )


def _container(drive_id: str, status: str = "running", name: str = "arm-ripper-x") -> MagicMock:
    c = MagicMock()
    c.status = status
    c.name = name
    c.labels = {DOCKER_LABEL_KEY: drive_id}
    c.image.id = "sha256:same"
    return c


# --- naming --------------------------------------------------------------


def test_container_name_uses_the_serial_slug() -> None:
    m, _ = _manager()
    assert m.container_name(_drive()) == "arm-ripper-aaaabbbb000e"


def test_container_name_falls_back_to_the_drive_id_suffix() -> None:
    m, _ = _manager()
    assert m.container_name(_drive(serial=None)) == "arm-ripper-" + "drv_01JABCDEFGHJKMNPQ"[-12:].lower()


def test_container_name_falls_back_to_the_drive_id_suffix_for_an_empty_serial() -> None:
    """B3: an empty-string serial sanitises to "" (not None), so the `or`
    fallback in `container_name` must trigger on the sanitised-empty case
    too, not just serial is None."""
    m, _ = _manager()
    assert m.container_name(_drive(serial="")) == "arm-ripper-" + "drv_01JABCDEFGHJKMNPQ"[-12:].lower()


def test_container_name_sanitises_hostname_unsafe_characters() -> None:
    m, _ = _manager()
    assert m.container_name(_drive(serial="S/N 12_3.")) == "arm-ripper-s-n-12-3"


# --- spec ------------------------------------------------------------------


def test_container_spec_matches_spec_section_3() -> None:
    m, _ = _manager(PUID="1001", PGID="1000", CDROM_GID="24")
    spec = m.container_spec(_drive())
    assert spec["image"] == "arm-ripper:test"
    assert spec["name"] == spec["hostname"] == "arm-ripper-aaaabbbb000e"
    assert spec["labels"] == {DOCKER_LABEL_KEY: "drv_01JABCDEFGHJKMNPQ"}
    assert spec["device_cgroup_rules"] == ["b 11:* rmw", "c 21:* rmw"]
    assert spec["restart_policy"] == {"Name": "unless-stopped"}
    assert spec["network"] == "armv3_default"
    assert spec["detach"] is True
    assert "auto_remove" not in spec and "devices" not in spec and "privileged" not in spec
    env = spec["environment"]
    assert env["ARM_DRIVE_ID"] == "drv_01JABCDEFGHJKMNPQ"
    assert env["ARM_DRIVE_BY_ID"] == "usb-PIONEER_BD-RW_BDR-S12JX_AAAABBBB000E-0:0"
    assert env["ARM_DRIVE_DEV"] == "/dev/sr0"
    assert env["ARM_BACKEND_URL"] == "https://arm-backend:8443"
    assert env["ARM_SERVICE_TOKEN"] == "tok-service"
    assert env["ARM_LOG_LEVEL"] == "debug"
    assert env["ARM_HOST_DISK_ROOT"] == "/host-disk"
    assert (env["PUID"], env["PGID"], env["CDROM_GID"]) == ("1001", "1000", "24")
    assert spec["volumes"] == {
        "/host/raw": {"bind": "/raw", "mode": "rw"},
        "/host/logs": {"bind": "/logs", "mode": "rw"},
        "/host/certs/arm-ca.crt": {"bind": "/etc/ssl/arm/arm-ca.crt", "mode": "ro"},
        "/dev/disk": {"bind": "/host-disk", "mode": "ro"},
    }


def test_container_spec_omits_by_id_and_ids_when_unset() -> None:
    m, _ = _manager()
    env = m.container_spec(_drive(by_id_name=None))["environment"]
    assert "ARM_DRIVE_BY_ID" not in env
    assert "PUID" not in env and "PGID" not in env and "CDROM_GID" not in env


def test_container_spec_forwards_ripper_tunables_under_their_ripper_names() -> None:
    m, _ = _manager(
        ARM_RIPPER_POLL_INTERVAL_SECONDS="1.5",
        ARM_RIPPER_MIN_LENGTH_SECONDS="300",
        ARM_RIPPER_MAKEMKV_KEYCHECK_INTERVAL_SECONDS="3600",
        ARM_RIPPER_NOT_READY_REARM_POLLS="5",
        ARM_RIPPER_OPTICAL_SR_MAX="15",
        ARM_RIPPER_OPTICAL_SG_MAX="31",
    )
    env = m.container_spec(_drive())["environment"]
    assert env["POLL_INTERVAL_SECONDS"] == "1.5"
    assert env["ARM_MIN_LENGTH_SECONDS"] == "300"
    assert env["MAKEMKV_KEYCHECK_INTERVAL_SECONDS"] == "3600"
    assert env["ARM_NOT_READY_REARM_POLLS"] == "5"
    assert env["ARM_OPTICAL_SR_MAX"] == "15"
    assert env["ARM_OPTICAL_SG_MAX"] == "31"


def test_container_spec_omits_unset_tunables() -> None:
    m, _ = _manager()
    env = m.container_spec(_drive())["environment"]
    assert "POLL_INTERVAL_SECONDS" not in env and "ARM_OPTICAL_SR_MAX" not in env


def test_container_spec_prefers_the_local_ripper_certs_path() -> None:
    m, _ = _manager(ARM_RIPPER_CERTS_PATH="/local/certs")
    volumes = m.container_spec(_drive())["volumes"]
    assert "/local/certs/arm-ca.crt" in volumes and "/host/certs/arm-ca.crt" not in volumes


def test_host_paths_set_accepts_a_ripper_certs_path_alone() -> None:
    assert _manager(ARM_HOST_CERTS_PATH="", ARM_RIPPER_CERTS_PATH="/local/certs")[0].host_paths_set() is True


def test_host_paths_set_needs_raw_logs_and_certs_only() -> None:
    assert _manager()[0].host_paths_set() is True
    assert _manager(ARM_HOST_MEDIA_PATH="")[0].host_paths_set() is True
    assert _manager(ARM_HOST_RAW_PATH="")[0].host_paths_set() is False


# --- ensure_running ----------------------------------------------------------


def test_ensure_running_creates_when_no_container_carries_the_label() -> None:
    m, client = _manager()
    client.containers.run.return_value = _container("drv_01JABCDEFGHJKMNPQ", name="arm-ripper-aaaabbbb000e")
    assert m.ensure_running(_drive()) == "arm-ripper-aaaabbbb000e"
    client.containers.list.assert_called_once_with(
        all=True, filters={"label": f"{DOCKER_LABEL_KEY}=drv_01JABCDEFGHJKMNPQ"}
    )
    kwargs = client.containers.run.call_args.kwargs
    assert kwargs["name"] == "arm-ripper-aaaabbbb000e" and kwargs["restart_policy"] == {"Name": "unless-stopped"}


def test_ensure_running_adopts_a_running_container_without_creating() -> None:
    m, client = _manager()
    client.containers.list.return_value = [_container("drv_01JABCDEFGHJKMNPQ", name="arm-ripper-old")]
    assert m.ensure_running(_drive()) == "arm-ripper-old"
    client.containers.run.assert_not_called()


def test_ensure_running_starts_an_exited_container() -> None:
    m, client = _manager()
    exited = _container("drv_01JABCDEFGHJKMNPQ", status="exited")
    client.containers.list.return_value = [exited]
    m.ensure_running(_drive())
    exited.start.assert_called_once()
    client.containers.run.assert_not_called()


def test_ensure_running_wraps_docker_errors() -> None:
    m, client = _manager()
    client.containers.run.side_effect = docker.errors.ImageNotFound("no such image: arm-ripper:test")
    with pytest.raises(RipperManagerError) as ei:
        m.ensure_running(_drive())
    assert "ImageNotFound" in str(ei.value) and "arm-ripper:test" in str(ei.value)


def test_ensure_running_wraps_transport_errors_too() -> None:
    m, client = _manager()
    client.containers.list.side_effect = ConnectionError("socket gone")
    with pytest.raises(RipperManagerError, match="socket gone"):
        m.ensure_running(_drive())


def test_ensure_running_adopts_on_a_409_name_conflict_from_a_concurrent_creator() -> None:
    """B1: a concurrent creator can win the create race between our
    `_labelled` lookup and `containers.run` — docker answers 409 for the
    name collision. Re-list and adopt the winner's container instead of
    failing the whole call."""
    m, client = _manager()
    winner = _container("drv_01JABCDEFGHJKMNPQ", status="running", name="arm-ripper-aaaabbbb000e")
    conflict = docker.errors.APIError("Conflict", response=MagicMock(status_code=409))
    client.containers.run.side_effect = conflict
    client.containers.list.side_effect = [[], [winner]]
    assert m.ensure_running(_drive()) == "arm-ripper-aaaabbbb000e"
    assert client.containers.list.call_count == 2


def test_ensure_running_reraises_a_409_when_no_container_shows_up() -> None:
    """B1: if the re-list after a 409 finds nothing, it wasn't a name-conflict
    adopt after all — the original error must propagate."""
    m, client = _manager()
    conflict = docker.errors.APIError("Conflict", response=MagicMock(status_code=409))
    client.containers.run.side_effect = conflict
    client.containers.list.side_effect = [[], []]
    with pytest.raises(RipperManagerError, match="409"):
        m.ensure_running(_drive())


def test_ensure_running_does_not_treat_a_non_409_api_error_as_adopt() -> None:
    m, client = _manager()
    client.containers.run.side_effect = docker.errors.APIError("busy", response=MagicMock(status_code=500))
    with pytest.raises(RipperManagerError, match="500"):
        m.ensure_running(_drive())
    assert client.containers.list.call_count == 1  # no re-list attempted


# --- remove ----------------------------------------------------------------


def test_remove_stops_and_removes_every_labelled_container() -> None:
    m, client = _manager()
    a, b = _container("drv_x"), _container("drv_x", status="exited")
    client.containers.list.return_value = [a, b]
    assert m.remove("drv_x") == 2
    client.containers.list.assert_called_once_with(all=True, filters={"label": f"{DOCKER_LABEL_KEY}=drv_x"})
    a.stop.assert_called_once()
    a.remove.assert_called_once()
    b.remove.assert_called_once()


def test_remove_returns_zero_when_nothing_matches() -> None:
    m, _ = _manager()
    assert m.remove("drv_none") == 0


def test_remove_wraps_docker_errors() -> None:
    m, client = _manager()
    c = _container("drv_x")
    c.remove.side_effect = docker.errors.APIError("in use")
    client.containers.list.return_value = [c]
    with pytest.raises(RipperManagerError, match="in use"):
        m.remove("drv_x")


# --- reconcile ---------------------------------------------------------------


def test_reconcile_creates_adopts_restarts_and_removes_orphans() -> None:
    m, client = _manager()
    running = _container("drv_running")
    exited = _container("drv_exited", status="exited")
    orphan = _container("drv_orphan")
    client.containers.list.return_value = [running, exited, orphan]
    client.containers.run.return_value = _container("drv_new", name="arm-ripper-new")
    summary = m.reconcile([_drive("drv_running"), _drive("drv_exited"), _drive("drv_new", serial="NEW1")])
    assert summary == ReconcileSummary(
        created=["drv_new"],
        adopted=["drv_running"],
        restarted=["drv_exited"],
        orphans_removed=["drv_orphan"],
        failed={},
    )
    client.containers.list.assert_called_once_with(all=True, filters={"label": DOCKER_LABEL_KEY})
    exited.start.assert_called_once()
    orphan.stop.assert_called_once()
    orphan.remove.assert_called_once()
    running.start.assert_not_called()


def test_reconcile_records_per_drive_failures_and_continues() -> None:
    m, client = _manager()
    orphan = _container("drv_orphan")
    orphan.remove.side_effect = docker.errors.APIError("busy")
    client.containers.list.return_value = [orphan]
    client.containers.run.side_effect = [docker.errors.ImageNotFound("nope"), _container("drv_b", name="b")]
    summary = m.reconcile([_drive("drv_a", serial="A"), _drive("drv_b", serial="B")])
    assert summary.created == ["drv_b"]
    assert set(summary.failed) == {"drv_orphan", "drv_a"}
    assert "nope" in summary.failed["drv_a"] and "busy" in summary.failed["drv_orphan"]


def test_reconcile_raises_when_the_daemon_cannot_be_listed() -> None:
    m, client = _manager()
    client.containers.list.side_effect = docker.errors.DockerException("no socket")
    with pytest.raises(RipperManagerError, match="no socket"):
        m.reconcile([])


def _with_image(c: MagicMock, image_id: str) -> MagicMock:
    c.image.id = image_id
    return c


def test_reconcile_recreates_an_idle_container_on_a_stale_image() -> None:
    m, client = _manager()
    client.images.get.return_value.id = "sha256:new"
    stale = _with_image(_container("drv_a"), "sha256:old")
    client.containers.list.return_value = [stale]
    client.containers.run.return_value = _container("drv_a", name="arm-ripper-a")
    summary = m.reconcile([_drive("drv_a", serial="A")])
    assert summary.recreated == ["drv_a"] and summary.adopted == [] and summary.failed == {}
    stale.stop.assert_called_once()
    stale.remove.assert_called_once()
    client.containers.run.assert_called_once()


def test_reconcile_records_a_failure_when_recreating_a_stale_container_fails() -> None:
    m, client = _manager()
    client.images.get.return_value.id = "sha256:new"
    stale = _with_image(_container("drv_a"), "sha256:old")
    client.containers.list.return_value = [stale]
    client.containers.run.side_effect = docker.errors.ImageNotFound("nope")
    summary = m.reconcile([_drive("drv_a", serial="A")])
    assert summary.recreated == [] and summary.adopted == []
    assert "nope" in summary.failed["drv_a"]
    stale.stop.assert_called_once()
    stale.remove.assert_called_once()


def test_reconcile_adopts_a_stale_image_while_the_drive_is_ripping(caplog) -> None:
    m, client = _manager()
    client.images.get.return_value.id = "sha256:new"
    stale = _with_image(_container("drv_a"), "sha256:old")
    client.containers.list.return_value = [stale]
    with caplog.at_level(logging.INFO, logger="arm_backend.ripper_manager"):
        summary = m.reconcile([_drive("drv_a", serial="A")], busy=frozenset({"drv_a"}))
    assert summary.adopted == ["drv_a"] and summary.recreated == []
    stale.remove.assert_not_called()
    assert "stale image" in caplog.text and "drv_a" in caplog.text


def test_reconcile_keeps_a_current_image() -> None:
    m, client = _manager()
    client.images.get.return_value.id = "sha256:same"
    running = _with_image(_container("drv_a"), "sha256:same")
    client.containers.list.return_value = [running]
    summary = m.reconcile([_drive("drv_a", serial="A")])
    assert summary.adopted == ["drv_a"] and summary.recreated == []
    client.containers.run.assert_not_called()


def test_reconcile_does_not_recreate_when_the_image_lookup_fails(caplog) -> None:
    m, client = _manager()
    client.images.get.side_effect = docker.errors.ImageNotFound("gone")
    running = _with_image(_container("drv_a"), "sha256:old")
    client.containers.list.return_value = [running]
    with caplog.at_level(logging.WARNING, logger="arm_backend.ripper_manager"):
        summary = m.reconcile([_drive("drv_a", serial="A")])
    assert summary.adopted == ["drv_a"]
    assert "cannot compare image" in caplog.text


# --- probe -----------------------------------------------------------------


def test_probe_checks_the_ripper_image() -> None:
    m, client = _manager()
    client.images.get.side_effect = docker.errors.ImageNotFound("x")
    assert m.probe() == (False, "image arm-ripper:test not present on docker host")


# --- container_status -------------------------------------------------------


def test_container_status_reports_missing_running_exited_and_stale() -> None:
    m, client = _manager()
    client.images.get.return_value.id = "sha256:same"
    assert m.container_status("drv_none") == ("missing", None)
    client.containers.list.return_value = [_container("drv_a")]
    assert m.container_status("drv_a") == ("running", True)
    client.containers.list.return_value = [_container("drv_a", status="exited")]
    assert m.container_status("drv_a") == ("exited", True)
    client.containers.list.return_value = [_with_image(_container("drv_a"), "sha256:old")]
    assert m.container_status("drv_a") == ("running", False)


def test_container_status_never_raises() -> None:
    m, client = _manager()
    client.containers.list.side_effect = docker.errors.DockerException("socket gone")
    assert m.container_status("drv_a") == ("unknown", None)
