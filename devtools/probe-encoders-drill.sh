#!/usr/bin/env bash
# Integration drill (NOT part of the zero-infra suite): run the per-device
# encoder probe (`--probe-device`, a real 2-second test encode per catalog
# encoder) against the real transcode image for every GPU on this host, the
# same way the backend's probe runner spawns it. Prints one JSON result line
# per device. Requires the built image(s) + a GPU/render node on this host.
#
# Usage: bash devtools/probe-encoders-drill.sh [IMAGE]
#   IMAGE defaults to arm-transcode:latest. Intel (qsv) devices use
#   IMAGE's -intel variant and AMD (vaapi) devices its -amd variant when that
#   image exists locally, else IMAGE itself (the backend's fallback).
set -euo pipefail
IMAGE="${1:-arm-transcode:latest}"

# <image> <suffix> -> the tag-suffixed variant name (arm-transcode:latest ->
# arm-transcode:latest-intel; an untagged name gets latest-<suffix>).
variant_image() {
    local image="$1" suffix="$2"
    if [[ "${image##*/}" == *:* ]]; then
        printf '%s-%s' "${image}" "${suffix}"
    else
        printf '%s:latest-%s' "${image}" "${suffix}"
    fi
}

image_for() {  # image_for <vendor>
    local variant=""
    case "$1" in
        qsv)   variant="$(variant_image "${IMAGE}" intel)" ;;
        vaapi) variant="$(variant_image "${IMAGE}" amd)" ;;
    esac
    if [[ -n "${variant}" ]] && docker image inspect "${variant}" >/dev/null 2>&1; then
        printf '%s' "${variant}"
    else
        printf '%s' "${IMAGE}"
    fi
}

probe() {  # probe <vendor> <device_path> <docker device flags...>
    local vendor="$1" device="$2" image
    shift 2
    image="$(image_for "${vendor}")"
    echo "==> probing ${vendor} ${device} with ${image}" >&2
    docker run --rm --network none \
        -e "ARM_GPU_VENDOR=${vendor}" -e "ARM_GPU_DEVICE=${device}" \
        "$@" "${image}" python -m arm_transcode.main --probe-device \
        || echo "==> probe of ${vendor} ${device} exited $?" >&2
}

found=0
for node in /dev/dri/renderD*; do
    [[ -e "${node}" ]] || continue
    vendor_file="/sys/class/drm/$(basename "${node}")/device/vendor"
    [[ -r "${vendor_file}" ]] || continue
    case "$(tr -d '[:space:]' < "${vendor_file}" | tr '[:upper:]' '[:lower:]')" in
        0x8086) vendor=qsv ;;
        0x1002) vendor=vaapi ;;
        *)      continue ;;
    esac
    # gosu (entrypoint) resets supplementary groups, so pass RENDER_GID for the
    # entrypoint to add before the privilege drop (as the backend does).
    probe "${vendor}" "${node}" --device "${node}:${node}:rwm" -e "RENDER_GID=$(stat -c '%g' "${node}")"
    found=1
done
if command -v nvidia-smi >/dev/null 2>&1; then
    while IFS= read -r idx; do
        [[ -n "${idx}" ]] || continue
        probe nvenc "nvidia://${idx}" --gpus "device=${idx}"
        found=1
    done < <(nvidia-smi -L 2>/dev/null | sed -nE 's/^GPU ([0-9]+):.*/\1/p')
fi
if [[ "${found}" -eq 0 ]]; then
    echo "no Intel/AMD render node or NVIDIA GPU found on this host; nothing to probe" >&2
    exit 1
fi
