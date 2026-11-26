"""Grouped, masked view of the backend's `Settings` for the environment report."""

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from arm_common import Config, Drive, DriveLifecycle, Gpu
from arm_common.config_metadata import CONFIG_FIELD_META
from arm_common.enums import GpuVendor
from arm_common.schemas.system import (
    ContainerEnvView,
    ContainerMountView,
    ContainerView,
    EnvEffectiveView,
    EnvGroupView,
    EnvVarView,
)

from arm_backend.config import Settings
from arm_backend.env_registry import CONTAINER_PUBLIC_ENV, ENV_GROUP_ORDER, ENV_REGISTRY, EnvVarMeta
from arm_backend.ripper_container_spec import container_spec, ripper_volume_pairs
from arm_backend.transcode_container_spec import (
    backend_url_for_spawn,
    container_identity_env,
    gpu_env,
    gpu_run_kwargs,
    task_volume_pairs,
)
from arm_backend.transcode_images import vendor_override

# The GPU inventory card lives on the Transcoding settings tab.
_GPUS_TAB = "Transcoding"


def strip_userinfo(url: str) -> str:
    """Replace any `user:pass@` in a URL with `***@`; non-URLs pass through, malformed ones are masked."""
    try:
        parts = urlsplit(url)
    except ValueError:
        # Unparseable: fail closed, the raw string may carry credentials.
        return "***"
    if "@" not in parts.netloc:
        return url
    host = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit(parts._replace(netloc=f"***@{host}"))


def _stringify(raw: object) -> str:
    if isinstance(raw, (list, tuple, set, frozenset)):
        return ",".join(str(i) for i in raw)
    return str(raw)


def _tab_for(setting_key: str) -> str:
    for meta in CONFIG_FIELD_META:
        if meta.key == setting_key:
            return meta.group
    return _GPUS_TAB


def _effective(meta: EnvVarMeta, env_value: str, cfg: Config | None, gpu_count: int) -> EnvEffectiveView | None:
    key = meta.seed_of
    if key == "gpus":
        return EnvEffectiveView(value=f"{gpu_count} device(s) in inventory", setting_key=key, tab=_GPUS_TAB)
    if key == "max_parallel_transcodes":
        db_value = cfg.max_parallel_transcodes if cfg is not None else None
        value = str(db_value) if db_value is not None else env_value
        return EnvEffectiveView(value=value, setting_key=key, tab=_tab_for(key))
    return None


def _view(key: str, meta: EnvVarMeta, settings: Settings, cfg: Config | None, gpu_count: int) -> EnvVarView:
    value = _stringify(getattr(settings, key))
    if meta.url and not meta.secret:
        value = strip_userinfo(value)
    return EnvVarView(
        key=key,
        value=None if meta.secret else value,
        secret=meta.secret,
        is_set=bool(value),
        source="env" if key in settings.model_fields_set else "default",
        effective=None if meta.secret else _effective(meta, value, cfg, gpu_count) if meta.seed_of else None,
    )


def build_env_groups(settings: Settings, cfg: Config | None, gpu_count: int) -> list[EnvGroupView]:
    by_group: dict[str, list[EnvVarView]] = {name: [] for name in ENV_GROUP_ORDER}
    for key in Settings.model_fields:
        meta = ENV_REGISTRY[key]
        by_group[meta.group].append(_view(key, meta, settings, cfg, gpu_count))
    return [EnvGroupView(name=name, vars=vs) for name, vs in by_group.items() if vs]


def mask_container_env(env: Mapping[str, str]) -> list[ContainerEnvView]:
    """Container env sorted by key; anything off the public allowlist is masked."""
    out: list[ContainerEnvView] = []
    for key in sorted(env):
        if key not in CONTAINER_PUBLIC_ENV:
            out.append(ContainerEnvView(key=key, value=None, secret=True))
            continue
        value = strip_userinfo(env[key]) if key == "ARM_BACKEND_URL" else env[key]
        out.append(ContainerEnvView(key=key, value=value, secret=False))
    return out


def _mounts(pairs: list[tuple[str, str, str]]) -> list[ContainerMountView]:
    # An empty host path is a misconfiguration; show it rather than a blank.
    return [ContainerMountView(host=host or "(unset)", container=bind, mode=mode) for host, bind, mode in pairs]


def _ripper_view(settings: Settings, drive: Drive) -> ContainerView:
    label = drive.display_name or drive.model or drive.hostname
    state = f"{drive.lifecycle.value}, {drive.status.value}"
    try:
        spec: dict[str, Any] = container_spec(settings, drive)
    except Exception:  # noqa: BLE001 — one malformed drive must not 500 the report
        return ContainerView(
            kind="ripper",
            label=label,
            state=f"{state}, spec error",
            image=settings.ARM_RIPPER_IMAGE,
            network=settings.ARM_DOCKER_NETWORK,
            docker_host=None,
            mounts=[],
            devices=[],
            env=[],
        )
    mounts = _mounts(ripper_volume_pairs(settings))
    # A virtual (ISO) ripper mounts its ISO as a docker Mount, not a volume.
    for m in spec.get("mounts", []):
        mounts.append(
            ContainerMountView(host=m["Source"], container=m["Target"], mode="ro" if m.get("ReadOnly") else "rw")
        )
    return ContainerView(
        kind="ripper",
        label=label,
        state=state,
        image=spec["image"],
        network=spec["network"],
        docker_host=None,
        mounts=mounts,
        devices=[],
        env=mask_container_env(spec["environment"]),
    )


def ripper_container_views(settings: Settings, drives: list[Drive]) -> list[ContainerView]:
    return [_ripper_view(settings, d) for d in drives if d.lifecycle != DriveLifecycle.RETIRED]


def _nvenc_device(request: Any) -> str:
    ids = getattr(request, "device_ids", None) or (request.get("DeviceIDs") if isinstance(request, dict) else None)
    return f"nvidia runtime, device {','.join(ids)}" if ids else "nvidia runtime, any device"


def _transcode_view(settings: Settings, gpu: Gpu | None) -> ContainerView:
    vendor: GpuVendor | None = gpu.vendor if gpu is not None else None
    env = container_identity_env(settings, vendor) | gpu_env(gpu, None)
    env |= {
        "ARM_BACKEND_URL": backend_url_for_spawn(settings),
        "ARM_SERVICE_TOKEN": settings.ARM_SERVICE_TOKEN,
        "ARM_LOG_LEVEL": settings.ARM_LOG_LEVEL,
    }
    devices: list[str] = []
    image = settings.ARM_TRANSCODE_IMAGE
    label, state = "CPU", None
    if gpu is not None and vendor is not None:
        kwargs = gpu_run_kwargs(gpu)
        devices = list(kwargs.get("devices", []))
        devices += [_nvenc_device(r) for r in kwargs.get("device_requests", [])]
        image = vendor_override(settings, vendor) or image
        label = f"{vendor.value} {gpu.device_path}"
        state = ("enabled" if gpu.enabled else "disabled") + (", not probed" if gpu.probed_at is None else "")
    return ContainerView(
        kind="transcode",
        label=label,
        state=state,
        image=image,
        network=None,
        docker_host=strip_userinfo(settings.ARM_TRANSCODE_DOCKER_HOST) or None,
        mounts=_mounts(task_volume_pairs(settings)),
        devices=devices,
        env=mask_container_env(env),
    )


def transcode_container_views(settings: Settings, gpus: list[Gpu]) -> list[ContainerView]:
    return [_transcode_view(settings, None), *(_transcode_view(settings, g) for g in gpus)]
