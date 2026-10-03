"""Per-vendor transcode image selection.

The transcode image is built as three Dockerfile targets. `base`
(`ARM_TRANSCODE_IMAGE`) carries the CPU encoders and the HW-enabled
HandBrakeCLI but no vendor VAAPI/QSV drivers; `intel` and `amd` add those
drivers and are tagged `<repo>:<tag>-intel` / `<repo>:<tag>-amd`. For a
QSV/VAAPI GPU claim the dispatcher uses the matching variant when it is
available on the docker host (present, or pulled on demand), and falls back
to the base image otherwise. NVENC and CPU spawns always use the base image:
NVENC needs nothing baked in beyond the HandBrake build, because the host's
NVIDIA Container Toolkit injects `libnvidia-encode` at run time, so there is
no NVENC variant to derive.

An explicit `ARM_TRANSCODE_IMAGE_QSV` / `_VAAPI` / `_NVENC` override always
wins over the derived name, for a differently-named or differently-tagged
build, or a registry reference the derivation can't express (a digest).
"""

from __future__ import annotations

from collections.abc import Callable

from arm_common import GpuVendor

from arm_backend.config import Settings

# Tag suffix for each vendor's derived variant image. NVENC has no entry:
# it only ever comes from an explicit ARM_TRANSCODE_IMAGE_NVENC override.
VARIANT_SUFFIX: dict[GpuVendor, str] = {
    GpuVendor.QSV: "intel",
    GpuVendor.VAAPI: "amd",
}


def split_reference(ref: str) -> tuple[str, str] | None:
    """Split an image reference into (repository, tag) for a pull.

    The tag separator is the LAST ':' that comes after the last '/', so a
    registry host:port (e.g. "reg:5000/arm-transcode") is never mistaken for
    a tag. A bare repository with no tag at all gets "latest", matching
    docker's own default. A digest reference ("name@sha256:...") has no tag,
    so this returns None.
    """
    if "@" in ref:
        return None
    slash = ref.rfind("/")
    colon = ref.rfind(":")
    if colon > slash:
        return ref[:colon], ref[colon + 1 :]
    return ref, "latest"


def variant_image(base: str, suffix: str) -> str | None:
    """Derive a variant reference by suffixing `base`'s TAG (never the
    repository) with `-<suffix>`.

    The tag separator is the LAST ':' that comes after the last '/', so a
    registry host:port (e.g. "reg:5000/arm-transcode") is never mistaken for
    a tag. A bare repository with no tag at all is treated as ":latest",
    matching docker's own default. A digest reference ("name@sha256:...")
    pins an immutable image with no tag to suffix, so this returns None;
    the caller needs an explicit override instead.
    """
    parts = split_reference(base)
    if parts is None:
        return None
    repo, tag = parts
    return f"{repo}:{tag}-{suffix}"


def vendor_override(settings: Settings, vendor: GpuVendor) -> str:
    """The explicit per-vendor override setting, or "" if unset."""
    return {
        GpuVendor.QSV: settings.ARM_TRANSCODE_IMAGE_QSV,
        GpuVendor.VAAPI: settings.ARM_TRANSCODE_IMAGE_VAAPI,
        GpuVendor.NVENC: settings.ARM_TRANSCODE_IMAGE_NVENC,
    }.get(vendor, "")


def image_for(settings: Settings, vendor: GpuVendor | None, *, exists: Callable[[str], bool]) -> str:
    """Pick the image the dispatcher should spawn for a claim on `vendor`
    (None for a CPU spawn).

    An explicit override always wins. Otherwise QSV/VAAPI use their derived
    variant when `exists(variant)` is true; every other case (NVENC, CPU, or
    a variant `exists` rejects) uses the base image. `exists` is only ever
    called with a derived variant, never with the base image.
    """
    if vendor is None:
        return settings.ARM_TRANSCODE_IMAGE
    override = vendor_override(settings, vendor)
    if override:
        return override
    suffix = VARIANT_SUFFIX.get(vendor)
    if suffix is not None:
        candidate = variant_image(settings.ARM_TRANSCODE_IMAGE, suffix)
        if candidate is not None and exists(candidate):
            return candidate
    return settings.ARM_TRANSCODE_IMAGE
