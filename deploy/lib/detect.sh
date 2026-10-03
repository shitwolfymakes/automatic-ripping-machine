#!/usr/bin/env bash
# deploy/lib/detect.sh: GPU discovery, NVENC driver floor, render and cdrom group ids, `ARM_GPUS` refresh.
# Shared by devtools/setup-dev.sh and deploy/armctl.sh. Sourced, never executed.
# Needs deploy/lib/common.sh loaded first.

# Minimum NVIDIA driver major version whose NVENC API satisfies the HandBrake
# build in services/transcode/Dockerfile. That Dockerfile pins nv-codec-headers
# to NVCODEC_VERSION 12.1.14.0, whose floor is driver 530.41.03. A host below
# this advertises NVENC via nvidia-smi but every GPU encode dies `rc=3` at
# `avcodec_open` ("Driver does not support the required nvenc API version");
# gating here makes such a host fall back to CPU instead. Keep in lockstep with
# the Dockerfile's NVCODEC_VERSION driver floor. This is the only shell copy;
# devtools/setup-dev.sh and deploy/armctl.sh both load it.
ARM_NVENC_MIN_DRIVER=530

# Echo `0` (advertise NVENC) or `1` (skip it) for the host's nvidia-smi driver.
# Warns to stderr — NOT stdout — so it never pollutes detect_gpus' JSON.
nvenc_driver_ok() {
    local drv major
    drv="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)"
    major="${drv%%.*}"
    if [[ -z "${major}" || ! "${major}" =~ ^[0-9]+$ ]]; then
        arm_warn "could not read NVIDIA driver version; advertising NVENC anyway"
        echo 0; return
    fi
    if (( major < ARM_NVENC_MIN_DRIVER )); then
        arm_warn "NVIDIA driver ${drv} is too old for this build's NVENC (needs >= ${ARM_NVENC_MIN_DRIVER}.x); skipping NVENC so transcodes fall back to CPU. Upgrade the driver to enable HW encode."
        echo 1; return
    fi
    arm_say "NVIDIA driver ${drv} detected (>= ${ARM_NVENC_MIN_DRIVER}.x); advertising NVENC" >&2
    echo 0
}

# Phase 7b: enumerate GPUs host-side so the GPU-free backend can fill the `gpus`
# table from ARM_GPUS instead of probing hardware. Prints a compact JSON array
# (empty `[]` if none). Every entry carries `"encoder_kinds":[]`: the backend
# probes each device itself with a real test encode, so this only reports which
# devices exist, never which codecs they can run. Needs no built image.
# Mirrors services/backend/arm_backend/gpu_probe.py (the single shell copy).
detect_gpus() {
    local entries=() node vendor_file vid vendor idx
    if [[ -d /dev/dri ]]; then
        for node in /dev/dri/renderD*; do
            [[ -e "${node}" ]] || continue
            vendor_file="/sys/class/drm/$(basename "${node}")/device/vendor"
            [[ -r "${vendor_file}" ]] || continue
            vid="$(tr -d '[:space:]' < "${vendor_file}" | tr '[:upper:]' '[:lower:]')"
            case "${vid}" in
                0x8086) vendor=qsv ;;
                0x1002) vendor=vaapi ;;
                *)      continue ;;
            esac
            entries+=("{\"vendor\":\"${vendor}\",\"device_path\":\"${node}\",\"encoder_kinds\":[]}")
        done
    fi
    if command -v nvidia-smi >/dev/null 2>&1 && [[ "$(nvenc_driver_ok)" == 0 ]]; then
        while IFS= read -r idx; do
            [[ -n "${idx}" ]] || continue
            entries+=("{\"vendor\":\"nvenc\",\"device_path\":\"nvidia://${idx}\",\"encoder_kinds\":[]}")
        done < <(nvidia-smi -L 2>/dev/null | sed -nE 's/^GPU ([0-9]+):.*/\1/p')
    fi
    local IFS=,
    printf '[%s]' "${entries[*]:-}"
}

# GID of the /dev/dri render-node group. The dispatcher adds this to VAAPI/QSV
# transcoders so the PUID-dropped process can open the node (root:render 0660).
# Empty if there's no render node (CPU / NVENC-only host).
detect_render_gid() {
    local node
    for node in /dev/dri/renderD*; do
        [[ -e "${node}" ]] || continue
        stat -c '%g' "${node}"
        return 0
    done
}

# The host's cdrom group id, or 44 (the Debian/Ubuntu default) when the group
# does not exist.
detect_cdrom_gid() {
    local gid
    gid="$(getent group cdrom | cut -d: -f3 || true)"
    printf '%s' "${gid:-44}"
}

# Host GPU list for this run, detected once and shared by the variant-build
# filter (select_up_services, before the build) and the .env write
# (refresh_arm_gpus, after the active-work guard). Detection only reads sysfs
# and nvidia-smi, so it never writes .env: a refused `up` leaves .env untouched.
DETECTED_GPUS=""
DETECTED_GPUS_SET=0
detect_gpus_once() {
    if [[ "${DETECTED_GPUS_SET}" -eq 0 ]]; then
        DETECTED_GPUS="$(detect_gpus)"
        DETECTED_GPUS_SET=1
    fi
}

# Refresh ARM_GPUS from host detection (it's derived, not a secret), UNLESS the
# transcode dispatcher is pointed at a remote docker host: then ARM_GPUS
# describes the REMOTE machine's GPUs (the dispatcher injects device access
# where the container actually runs), and detecting this host's GPUs would
# overwrite a hand-set remote GPU list with the wrong hardware.
# --ripper-only also skips detection: a ripper-only install never spawns a
# local transcoder, so there's nothing to advertise GPUs for.
refresh_arm_gpus() {
    local value
    if grep -qE '^ARM_TRANSCODE_DOCKER_HOST=..*' "${ENV_FILE}"; then
        arm_say "ARM_TRANSCODE_DOCKER_HOST set — keeping .env's ARM_GPUS (remote transcode host owns the GPUs)"
        return 0
    elif [[ "${RIPPER_ONLY}" -eq 1 ]]; then
        value="[]"
    else
        detect_gpus_once
        value="${DETECTED_GPUS}"
    fi
    if grep -q '^ARM_GPUS=' "${ENV_FILE}"; then
        sed -i "s|^ARM_GPUS=.*|ARM_GPUS=${value}|" "${ENV_FILE}"
    else
        printf 'ARM_GPUS=%s\n' "${value}" >> "${ENV_FILE}"
    fi
    if [[ "${RIPPER_ONLY}" -eq 1 ]]; then
        arm_say "${ARM_HINT_RIPPER_ONLY}: skipping GPU detection, ARM_GPUS=[]"
    else
        arm_say "detected GPU(s) for ARM_GPUS: ${value}"
    fi
}
