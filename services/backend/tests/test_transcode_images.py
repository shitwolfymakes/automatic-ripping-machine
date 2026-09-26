"""Per-vendor transcode image selection: `split_reference`'s repo/tag split
for pulls, `variant_image`'s tag-suffix
derivation, `vendor_override`'s per-vendor Settings lookup, and `image_for`'s
override > derived-variant > base precedence.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.config import Settings  # noqa: E402
from arm_backend.transcode_images import image_for, split_reference, variant_image, vendor_override  # noqa: E402
from arm_common import GpuVendor  # noqa: E402


def _settings(**overrides: object) -> Settings:
    base = {
        "DATABASE_URL": "postgresql://x:x@localhost/x",
        "ARM_SERVICE_TOKEN": "tok-service",
        "ARM_TRANSCODE_IMAGE": "arm-transcode:latest",
    }
    base.update(overrides)
    return Settings.model_construct(**base)


# --- split_reference ---------------------------------------------------------


def test_split_reference_splits_repo_and_tag() -> None:
    assert split_reference("arm-transcode:latest-intel") == ("arm-transcode", "latest-intel")


def test_split_reference_keeps_registry_port_in_the_repo() -> None:
    assert split_reference("reg:5000/ns/arm-transcode:v3-amd") == ("reg:5000/ns/arm-transcode", "v3-amd")
    assert split_reference("reg:5000/arm-transcode") == ("reg:5000/arm-transcode", "latest")


def test_split_reference_rejects_any_digest() -> None:
    assert split_reference("arm-transcode@sha256:" + "a" * 64) is None
    assert split_reference("reg:5000/arm-transcode:v1@sha512:" + "b" * 128) is None


# --- variant_image -----------------------------------------------------------


def test_variant_image_suffixes_the_tag() -> None:
    assert variant_image("arm-transcode:latest", "intel") == "arm-transcode:latest-intel"


def test_variant_image_defaults_missing_tag_to_latest() -> None:
    assert variant_image("arm-transcode", "intel") == "arm-transcode:latest-intel"


def test_variant_image_handles_registry_host_with_port() -> None:
    assert variant_image("reg:5000/arm-transcode", "amd") == "reg:5000/arm-transcode:latest-amd"


def test_variant_image_handles_registry_host_with_port_and_tag() -> None:
    assert variant_image("reg:5000/arm-transcode:v1", "amd") == "reg:5000/arm-transcode:v1-amd"


def test_variant_image_returns_none_for_digest_reference() -> None:
    digest = "arm-transcode@sha256:" + "a" * 64
    assert variant_image(digest, "intel") is None


# --- vendor_override -----------------------------------------------------------


def test_vendor_override_defaults_empty() -> None:
    settings = _settings()
    assert vendor_override(settings, GpuVendor.QSV) == ""
    assert vendor_override(settings, GpuVendor.VAAPI) == ""
    assert vendor_override(settings, GpuVendor.NVENC) == ""


def test_vendor_override_reads_the_matching_setting() -> None:
    settings = _settings(
        ARM_TRANSCODE_IMAGE_QSV="custom-qsv:latest",
        ARM_TRANSCODE_IMAGE_VAAPI="custom-vaapi:latest",
        ARM_TRANSCODE_IMAGE_NVENC="custom-nvenc:latest",
    )
    assert vendor_override(settings, GpuVendor.QSV) == "custom-qsv:latest"
    assert vendor_override(settings, GpuVendor.VAAPI) == "custom-vaapi:latest"
    assert vendor_override(settings, GpuVendor.NVENC) == "custom-nvenc:latest"


# --- image_for -----------------------------------------------------------------


def test_image_for_cpu_spawn_always_uses_base() -> None:
    settings = _settings(ARM_TRANSCODE_IMAGE_NVENC="custom-nvenc:latest")
    assert image_for(settings, None, exists=lambda _img: True) == "arm-transcode:latest"


def test_image_for_qsv_uses_derived_variant_when_it_exists() -> None:
    settings = _settings()
    assert image_for(settings, GpuVendor.QSV, exists=lambda img: img == "arm-transcode:latest-intel") == (
        "arm-transcode:latest-intel"
    )


def test_image_for_vaapi_uses_derived_variant_when_it_exists() -> None:
    settings = _settings()
    assert image_for(settings, GpuVendor.VAAPI, exists=lambda img: img == "arm-transcode:latest-amd") == (
        "arm-transcode:latest-amd"
    )


def test_image_for_falls_back_to_base_when_variant_missing() -> None:
    settings = _settings()
    assert image_for(settings, GpuVendor.QSV, exists=lambda _img: False) == "arm-transcode:latest"


def test_image_for_nvenc_uses_base_even_when_variant_would_exist() -> None:
    """NVENC has no derived variant at all: `exists` is never consulted."""
    settings = _settings()
    calls: list[str] = []

    def _exists(img: str) -> bool:
        calls.append(img)
        return True

    assert image_for(settings, GpuVendor.NVENC, exists=_exists) == "arm-transcode:latest"
    assert calls == []


def test_image_for_override_wins_over_derived_variant() -> None:
    settings = _settings(ARM_TRANSCODE_IMAGE_QSV="custom-qsv:latest")
    assert image_for(settings, GpuVendor.QSV, exists=lambda _img: True) == "custom-qsv:latest"


def test_image_for_nvenc_override() -> None:
    settings = _settings(ARM_TRANSCODE_IMAGE_NVENC="custom-nvenc:latest")
    assert image_for(settings, GpuVendor.NVENC, exists=lambda _img: True) == "custom-nvenc:latest"


def test_image_for_override_does_not_call_exists() -> None:
    settings = _settings(ARM_TRANSCODE_IMAGE_VAAPI="custom-vaapi:latest")
    calls: list[str] = []
    image_for(settings, GpuVendor.VAAPI, exists=lambda img: calls.append(img) or True)
    assert calls == []


def test_image_for_digest_base_with_no_override_falls_back_to_digest() -> None:
    """A digest-pinned base with no per-vendor override: `variant_image`
    returns None, so `image_for` can't derive anything and must keep the
    base (digest) reference rather than crash or pass None to docker."""
    digest = "arm-transcode@sha256:" + "b" * 64
    settings = _settings(ARM_TRANSCODE_IMAGE=digest)
    assert image_for(settings, GpuVendor.QSV, exists=lambda _img: True) == digest
