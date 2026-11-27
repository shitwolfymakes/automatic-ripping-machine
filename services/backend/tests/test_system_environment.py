import pytest
from arm_backend.config import Settings
from arm_backend.env_registry import CONTAINER_PUBLIC_ENV, ENV_GROUP_ORDER, EnvVarMeta
from arm_backend.ripper_container_spec import container_spec
from arm_backend.system_environment import (
    _effective,
    _nvenc_device,
    _tab_for,
    build_env_groups,
    mask_container_env,
    ripper_container_views,
    transcode_container_views,
)
from arm_backend.transcode_container_spec import container_identity_env, gpu_env
from arm_common import Config, Drive, DriveKind, DriveLifecycle, Gpu
from arm_common.enums import DriveStatus, GpuVendor
from arm_common.schemas.system import ContainerMountView, EnvEffectiveView, EnvGroupView, EnvVarView


@pytest.fixture
def make_settings(monkeypatch: pytest.MonkeyPatch):
    def _make(**env: str) -> Settings:
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db/arm")
        monkeypatch.setenv("ARM_SERVICE_TOKEN", "tok")
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        return Settings()

    return _make


def _absent(image: str) -> bool:
    return False


def _var(groups: list[EnvGroupView], key: str) -> EnvVarView:
    return next(v for g in groups for v in g.vars if v.key == key)


def test_groups_follow_order_and_cover_every_field(make_settings):
    groups = build_env_groups(make_settings(), Config(id=1), 0)
    assert [g.name for g in groups] == [n for n in ENV_GROUP_ORDER if any(g.name == n for g in groups)]
    assert {v.key for g in groups for v in g.vars} == set(Settings.model_fields)


def test_secret_masked_but_reported_set(make_settings):
    v = _var(build_env_groups(make_settings(), Config(id=1), 0), "ARM_SERVICE_TOKEN")
    assert v.value is None and v.secret and v.is_set and v.source == "env"


def test_source_default_vs_env(make_settings):
    groups = build_env_groups(make_settings(BIND_PORT="9443"), Config(id=1), 0)
    assert _var(groups, "BIND_PORT").source == "env" and _var(groups, "BIND_PORT").value == "9443"
    assert _var(groups, "RAW_ROOT").source == "default" and _var(groups, "RAW_ROOT").value == "/raw"


def test_explicit_empty_string_is_env_source(make_settings):
    v = _var(
        build_env_groups(make_settings(ARM_RIPPER_MIN_LENGTH_SECONDS=""), Config(id=1), 0),
        "ARM_RIPPER_MIN_LENGTH_SECONDS",
    )
    assert v.source == "env" and v.value == "" and v.is_set is False


def test_url_userinfo_stripped(make_settings):
    groups = build_env_groups(make_settings(ARM_TRANSCODE_DOCKER_HOST="ssh://bob:pw@nas:22"), Config(id=1), 0)
    assert _var(groups, "ARM_TRANSCODE_DOCKER_HOST").value == "ssh://***@nas:22"


def test_malformed_url_var_does_not_break_groups(make_settings):
    groups = build_env_groups(make_settings(ARM_TRANSCODE_DOCKER_HOST="http://[bad"), Config(id=1), 0)
    assert _var(groups, "ARM_TRANSCODE_DOCKER_HOST").value == "***"


def test_seed_only_shows_effective_db_value(make_settings):
    groups = build_env_groups(make_settings(MAX_PARALLEL_TRANSCODES="2"), Config(id=1, max_parallel_transcodes=4), 0)
    eff = _var(groups, "MAX_PARALLEL_TRANSCODES").effective
    assert eff == EnvEffectiveView(value="4", setting_key="max_parallel_transcodes", tab="Transcoding")


def test_seed_only_falls_back_without_config_row(make_settings):
    groups = build_env_groups(make_settings(MAX_PARALLEL_TRANSCODES="2"), None, 0)
    eff = _var(groups, "MAX_PARALLEL_TRANSCODES").effective
    assert eff is not None and eff.value == "2"


def test_gpus_effective_is_inventory_count(make_settings):
    eff = _var(build_env_groups(make_settings(), Config(id=1), 3), "ARM_GPUS").effective
    assert eff is not None and eff.value == "3 device(s) in inventory"


def test_ripper_view_masks_token_and_lists_mounts(make_settings):
    s = make_settings(ARM_HOST_RAW_PATH="/srv/raw", ARM_HOST_LOGS_PATH="/srv/logs", ARM_HOST_CERTS_PATH="/srv/certs")
    drive = Drive(
        id="drv_on0000000000000000000001",
        hostname="h1",
        device_path="/dev/sr0",
        lifecycle=DriveLifecycle.ENROLLED,
        status=DriveStatus.ONLINE,
    )
    [view] = ripper_container_views(s, [drive])
    env = {e.key: e for e in view.env}
    assert env["ARM_SERVICE_TOKEN"].value is None and env["ARM_SERVICE_TOKEN"].secret
    assert env["ARM_DRIVE_DEV"].value == "/dev/sr0"
    assert ContainerMountView(host="/srv/raw", container="/raw", mode="rw") in view.mounts
    assert view.image == s.ARM_RIPPER_IMAGE and view.network == s.ARM_DOCKER_NETWORK
    assert view.kind == "ripper" and view.state == "enrolled, online"


def test_retired_virtual_drives_skipped(make_settings):
    retired = Drive(
        id="drv_iso000000000000000000003",
        hostname="iso",
        device_path="",
        kind=DriveKind.VIRTUAL,
        lifecycle=DriveLifecycle.RETIRED,
    )
    assert ripper_container_views(make_settings(), [retired]) == []


def test_virtual_ripper_lists_iso_mount(make_settings):
    s = make_settings(ARM_HOST_ISO_LIBRARY_PATH="/srv/isos")
    drive = Drive(
        id="drv_iso000000000000000000004",
        hostname="iso4",
        device_path="/source/a.iso",
        kind=DriveKind.VIRTUAL,
        source_path="a.iso",
        display_name="My ISO",
        status=DriveStatus.ONLINE,
    )
    [view] = ripper_container_views(s, [drive])
    assert view.label == "My ISO"
    assert ContainerMountView(host="/srv/isos/a.iso", container="/source/a.iso", mode="ro") in view.mounts


def test_unknown_container_key_masked():
    [e] = mask_container_env({"SOMETHING_NEW": "x"})
    assert e.value is None and e.secret


def test_transcode_views_cpu_plus_each_gpu(make_settings):
    gpu = Gpu(id="gpu_1", vendor=GpuVendor.VAAPI, device_path="/dev/dri/renderD128", enabled=True)
    cpu, vaapi = transcode_container_views(make_settings(ARM_RENDER_GID="109"), [gpu], _absent)
    assert cpu.label == "CPU" and cpu.devices == []
    assert vaapi.devices == ["/dev/dri/renderD128:/dev/dri/renderD128:rwm"]
    env = {e.key: e for e in vaapi.env}
    assert env["RENDER_GID"].value == "109" and env["ARM_SERVICE_TOKEN"].value is None
    assert "ARM_TRANSCODE_TASK_ID" not in env
    assert vaapi.state == "enabled, not probed"


def test_transcode_nvenc_renders_runtime_device(make_settings):
    gpu = Gpu(id="gpu_2", vendor=GpuVendor.NVENC, device_path="nvidia://1", enabled=False)
    _, nv = transcode_container_views(make_settings(), [gpu], _absent)
    assert nv.devices == ["nvidia runtime, device 1"]
    assert nv.state == "disabled, not probed"


def test_nvenc_device_reads_raw_device_request_dicts():
    assert _nvenc_device({"DeviceIDs": ["0", "2"]}) == "nvidia runtime, device 0,2"


def test_nvenc_device_without_ids_is_any_device():
    assert _nvenc_device({"Count": -1}) == "nvidia runtime, any device"
    assert _nvenc_device(object()) == "nvidia runtime, any device"


def test_transcode_backend_url_userinfo_stripped(make_settings):
    s = make_settings(
        ARM_TRANSCODE_DOCKER_HOST="ssh://bob:pw@nas:22", ARM_TRANSCODE_BACKEND_URL="https://u:p@host:8443"
    )
    [cpu] = transcode_container_views(s, [], _absent)
    env = {e.key: e.value for e in cpu.env}
    assert env["ARM_BACKEND_URL"] == "https://***@host:8443"
    assert cpu.docker_host == "ssh://***@nas:22"


def test_transcode_local_view_uses_the_spawn_network(make_settings):
    [cpu] = transcode_container_views(make_settings(ARM_DOCKER_NETWORK="armv3_default"), [], _absent)
    assert cpu.network == "armv3_default"


def test_transcode_remote_view_has_no_network(make_settings):
    s = make_settings(ARM_DOCKER_NETWORK="armv3_default", ARM_TRANSCODE_DOCKER_HOST="ssh://nas")
    [cpu] = transcode_container_views(s, [], _absent)
    assert cpu.network is None


def test_transcode_view_shows_the_vendor_variant_the_spawn_picks(make_settings):
    s = make_settings(ARM_TRANSCODE_IMAGE="ghcr.io/x/arm-transcode:3.1.0")
    gpu = Gpu(id="gpu_q", vendor=GpuVendor.QSV, device_path="/dev/dri/renderD128", enabled=True)
    seen: list[str] = []

    def _present(image: str) -> bool:
        seen.append(image)
        return True

    cpu, qsv = transcode_container_views(s, [gpu], _present)
    assert cpu.image == "ghcr.io/x/arm-transcode:3.1.0"
    assert qsv.image == "ghcr.io/x/arm-transcode:3.1.0-intel"
    assert seen == ["ghcr.io/x/arm-transcode:3.1.0-intel"]


def test_transcode_view_falls_back_to_the_base_image_without_the_variant(make_settings):
    s = make_settings(ARM_TRANSCODE_IMAGE="ghcr.io/x/arm-transcode:3.1.0")
    gpu = Gpu(id="gpu_q", vendor=GpuVendor.QSV, device_path="/dev/dri/renderD128", enabled=True)
    _, qsv = transcode_container_views(s, [gpu], _absent)
    assert qsv.image == "ghcr.io/x/arm-transcode:3.1.0"


def test_container_env_keys_all_allowlisted_except_token(make_settings):
    s = make_settings(
        ARM_RENDER_GID="109",
        ARM_TRANSCODE_PUID="1000",
        ARM_TRANSCODE_PGID="1000",
        PUID="1000",
        PGID="1000",
        CDROM_GID="24",
        ARM_RIPPER_MIN_LENGTH_SECONDS="120",
        ARM_RIPPER_POLL_INTERVAL_SECONDS="5",
        ARM_RIPPER_MAKEMKV_KEYCHECK_INTERVAL_SECONDS="60",
        ARM_RIPPER_NOT_READY_REARM_POLLS="3",
        ARM_RIPPER_OPTICAL_SR_MAX="4",
        ARM_RIPPER_OPTICAL_SG_MAX="4",
        ARM_HOST_ISO_LIBRARY_PATH="/srv/isos",
    )
    optical = Drive(id="drv_on0000000000000000000001", hostname="h1", device_path="/dev/sr0", by_id_name="ata-X")
    virtual = Drive(
        id="drv_iso000000000000000000004",
        hostname="iso4",
        device_path="/source/a.iso",
        kind=DriveKind.VIRTUAL,
        source_path="a.iso",
        rip_params_json={"session_id": "s1"},
    )
    keys: set[str] = set()
    for d in (optical, virtual):
        keys |= set(container_spec(s, d)["environment"])
    for vendor in GpuVendor:
        keys |= set(container_identity_env(s, vendor))
        gpu = Gpu(id="gpu_x", vendor=vendor, device_path="/dev/dri/renderD128")
        keys |= set(gpu_env(gpu, None))
    keys |= {"ARM_BACKEND_URL", "ARM_SERVICE_TOKEN", "ARM_LOG_LEVEL"}
    assert keys - CONTAINER_PUBLIC_ENV == {"ARM_SERVICE_TOKEN"}


def test_empty_host_paths_keep_every_mount_and_show_unset(make_settings):
    s = make_settings(ARM_HOST_RAW_PATH="", ARM_HOST_MEDIA_PATH="", ARM_HOST_LOGS_PATH="")
    drive = Drive(
        id="drv_on0000000000000000000005",
        hostname="h5",
        device_path="/dev/sr0",
        lifecycle=DriveLifecycle.ENROLLED,
        status=DriveStatus.ONLINE,
    )
    [rip] = ripper_container_views(s, [drive])
    assert {m.container for m in rip.mounts if m.host == "(unset)"} == {"/raw", "/logs"}
    cpu = transcode_container_views(s, [], _absent)[0]
    assert {m.container for m in cpu.mounts if m.host == "(unset)"} == {"/raw", "/media", "/logs"}


def test_spec_error_degrades_to_a_view(make_settings):
    bad = Drive(
        id="drv_iso000000000000000000006",
        hostname="iso6",
        device_path="/source/x.iso",
        kind=DriveKind.VIRTUAL,
        source_path=None,
        lifecycle=DriveLifecycle.ENROLLED,
        status=DriveStatus.ONLINE,
    )
    [view] = ripper_container_views(make_settings(), [bad])
    assert view.state == "enrolled, online, spec error"
    assert view.env == [] and view.mounts == []


def test_tab_for_unknown_setting_falls_back_to_gpus_tab() -> None:
    assert _tab_for("no_such_setting") == "Transcoding"


def test_effective_unknown_seed_is_none() -> None:
    assert _effective(EnvVarMeta("Transcode", seed_of="no_such_setting"), "1", None, 0) is None
