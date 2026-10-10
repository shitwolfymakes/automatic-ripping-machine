#!/usr/bin/env bash
# One-shot dev-environment setup for the walking skeleton.
# Idempotent — rerunning skips work already done and leaves existing .env alone.
#
# Usage:  bash devtools/setup-dev.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Runtime/data dirs (db, raw, media, logs, certs) live under ./arm/ to keep the
# repo root tidy — the dev mirror of production's ~/arm prefix. The compose file
# and .env still live in the repo root (dev builds from `context: .`).
ARM_DIR="${ROOT_DIR}/arm"

require() {
    local bin="$1"
    local hint="$2"
    if ! command -v "${bin}" >/dev/null 2>&1; then
        echo "ERROR: '${bin}' not found. ${hint}" >&2
        exit 1
    fi
}

# Load nvm if the user manages Node that way. nvm only wires `node`/`npm` onto
# PATH in interactive shells, so a non-interactive `bash devtools/setup-dev.sh`
# wouldn't see them; sourcing nvm.sh here fixes that and pins the version to
# services/ui/.nvmrc so the host toolchain matches the container build.
load_nvm() {
    local nvm_sh="${NVM_DIR:-${HOME}/.nvm}/nvm.sh"
    [[ -s "${nvm_sh}" ]] || return 0   # no nvm install — fall through to PATH + require
    echo "==> nvm detected — loading Node from services/ui/.nvmrc"
    local want
    want="$(cat "${ROOT_DIR}/services/ui/.nvmrc" 2>/dev/null || true)"
    # nvm.sh isn't written for `set -eu`; relax around the load + select, then restore.
    set +eu
    # shellcheck disable=SC1090
    . "${nvm_sh}"
    if [[ -n "${want}" ]]; then
        nvm install "${want}" && nvm use "${want}"
    fi
    set -eu
}

# Minimum NVIDIA driver major version whose NVENC API satisfies the HandBrake
# build in services/transcode/Dockerfile. That Dockerfile pins nv-codec-headers
# to NVCODEC_VERSION 12.1.14.0, whose floor is driver 530.41.03. A host below
# this advertises NVENC via nvidia-smi but every GPU encode dies `rc=3` at
# `avcodec_open` ("Driver does not support the required nvenc API version");
# gating here makes such a host fall back to CPU instead. Keep in lockstep with
# the Dockerfile's NVCODEC_VERSION driver floor. Mirror any change in install.sh.
ARM_NVENC_MIN_DRIVER=530

# Echo `0` (advertise NVENC) or `1` (skip it) for the host's nvidia-smi driver.
# Warns to stderr — NOT stdout — so it never pollutes detect_gpus' JSON.
nvenc_driver_ok() {
    local drv major
    drv="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)"
    major="${drv%%.*}"
    if [[ -z "${major}" || ! "${major}" =~ ^[0-9]+$ ]]; then
        echo "WARNING: could not read NVIDIA driver version; advertising NVENC anyway" >&2
        echo 0; return
    fi
    if (( major < ARM_NVENC_MIN_DRIVER )); then
        echo "WARNING: NVIDIA driver ${drv} is too old for this build's NVENC (needs >= ${ARM_NVENC_MIN_DRIVER}.x); skipping NVENC so transcodes fall back to CPU. Upgrade the driver to enable HW encode." >&2
        echo 1; return
    fi
    echo "==> NVIDIA driver ${drv} detected (>= ${ARM_NVENC_MIN_DRIVER}.x); advertising NVENC" >&2
    echo 0
}

# Probe the transcode image for the HW encoders HandBrake can actually run.
# Prints the raw JSON ({"qsv":["h264"],...}) on success, nothing on failure.
# Best-effort only: on a fresh install this runs before images are pulled, so
# a missing image is expected and the caller treats empty output as "fall back
# to h264+h265" — never blocks install. Mirrors install.sh.
#
# The `arm-transcode:latest` default is correct HERE (unlike install.sh, which
# must qualify it as ${ARM_IMAGE_PREFIX}/arm-transcode:${ARM_IMAGE_TAG}): the dev
# docker-compose.yml.example BUILDS + tags the transcode image as exactly
# `arm-transcode:latest`, so that unqualified name is the real local image.
probe_encoder_caps() {
    local image="${ARM_TRANSCODE_IMAGE:-arm-transcode:latest}"
    local devflags=()
    if [[ -d /dev/dri ]]; then
        devflags+=(--device /dev/dri)
        # gosu (entrypoint) RESETS supplementary groups, so a docker --group-add
        # render_gid would not survive into the `arm` process → HandBrake could
        # not open the render node → QSV/VAAPI init fails → probe falsely reports
        # {}. Pass RENDER_GID env instead: the entrypoint adds `arm` to it BEFORE
        # the gosu drop (same as the transcode dispatcher). Mirrors install.sh.
        local render_gid
        render_gid="$(detect_render_gid || true)"
        [[ -n "${render_gid}" ]] && devflags+=(-e "RENDER_GID=${render_gid}")
    fi
    command -v nvidia-smi >/dev/null 2>&1 && devflags+=(--gpus all)
    # Print the probe's JSON on stdout and RETURN ITS EXIT STATUS (no `|| true`).
    # The caller treats exit 0 as authoritative — even a `{}` result means
    # "checked, this device has no working HW encoder" and MUST NOT be overridden
    # with the h264+h265 default. Only a non-zero exit is a genuine probe failure.
    timeout 60 docker run --rm "${devflags[@]}" "${image}" \
        python -m arm_transcode.main --probe-encoders 2>/dev/null
}

# Phase 7b: enumerate GPUs host-side so the GPU-free backend can fill the `gpus`
# table from ARM_GPUS instead of probing hardware. Prints a compact JSON array
# (empty `[]` if none). Mirrors services/backend/arm_backend/gpu_probe.py and the
# detect_gpus in install.sh.
detect_gpus() {
    local entries=() node vendor_file vid vendor idx
    local caps_json probe_ok
    # Capture BOTH the probe output and whether it ran authoritatively. `&& ... ||`
    # keeps the non-zero exit from aborting under `set -e`. probe_ok=1 means the
    # probe ran and its JSON is the truth (even `{}`); probe_ok=0 means it failed
    # (image missing/timeout/docker error) and we fall back to the safe default.
    caps_json="$(probe_encoder_caps)" && probe_ok=1 || probe_ok=0
    # kinds_for <vendor> -> JSON array string, e.g. ["h264","h265"], ["h264"], or [].
    # When the probe RAN (probe_ok=1), its answer is authoritative: a vendor absent
    # from the JSON (or present as []) means "no working HW encoder" -> [] (do NOT
    # over-claim). Only a probe FAILURE falls back to h264+h265.
    kinds_for() {
        local vendor="$1" kinds=""
        if [[ -n "${caps_json}" ]] && command -v jq >/dev/null 2>&1; then
            kinds="$(printf '%s' "${caps_json}" | jq -c --arg v "${vendor}" '.[$v] // empty' 2>/dev/null)"
        elif [[ -n "${caps_json}" ]]; then
            kinds="$(printf '%s' "${caps_json}" | grep -oE "\"${vendor}\":\[[^]]*\]" | sed -E "s/\"${vendor}\"://")"
        fi
        if [[ -n "${kinds}" ]]; then
            printf '%s' "${kinds}"        # probe reported real codecs for this vendor
        elif [[ "${probe_ok}" == "1" ]]; then
            printf '[]'                   # probe ran, vendor has no HW encoder -> honest empty
        else
            printf '["h264","h265"]'      # probe failed -> safe (pre-probe) default
        fi
    }
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
            entries+=("{\"vendor\":\"${vendor}\",\"device_path\":\"${node}\",\"encoder_kinds\":$(kinds_for "${vendor}")}")
        done
    fi
    if command -v nvidia-smi >/dev/null 2>&1 && [[ "$(nvenc_driver_ok)" == 0 ]]; then
        while IFS= read -r idx; do
            [[ -n "${idx}" ]] || continue
            entries+=("{\"vendor\":\"nvenc\",\"device_path\":\"nvidia://${idx}\",\"encoder_kinds\":$(kinds_for nvenc)}")
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

require uv      "install: curl -LsSf https://astral.sh/uv/install.sh | sh"
require docker  "install: https://docs.docker.com/engine/install/"
require openssl "openssl should be present on any linux system"

# nvm users: pull Node onto PATH (and pin it to .nvmrc) before the checks below.
load_nvm

require node    "install Node 22 (matches services/ui/.nvmrc / Dockerfile): https://nodejs.org/ — or 'nvm install' if you use nvm"
require npm     "npm ships with Node — reinstall Node, or run 'nvm use', if it's missing"

if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: 'docker compose' (v2 plugin) not available" >&2
    exit 1
fi

echo "==> syncing host venv via uv"
( cd "${ROOT_DIR}" && uv sync )

# UI deps from the committed lockfile (same as services/ui/Dockerfile, which
# builds on node:22). npm ci wipes node_modules and reinstalls exactly what
# package-lock.json pins, so guard it: npm writes node_modules/.package-lock.json
# on install, and a `git pull` that updates the lockfile makes it newer again.
UI_DIR="${ROOT_DIR}/services/ui"
if [[ -d "${UI_DIR}/node_modules" \
      && "${UI_DIR}/node_modules/.package-lock.json" -nt "${UI_DIR}/package-lock.json" ]]; then
    echo "==> UI deps already current — skipping npm ci"
else
    echo "==> installing UI deps via npm ci"
    ( cd "${UI_DIR}" && npm ci --no-audit --no-fund )
fi

# Create the data-dir tree under ./arm/ (mirrors install.sh's ensure_prefix:
# setgid + group-writable on the ARM-written dirs so spawned containers inherit
# the group). Idempotent; pre-creating avoids docker bind-mounting root-owned
# source dirs into the PUID-dropped containers.
echo "==> ensuring data dirs under ${ARM_DIR}"
mkdir -p "${ARM_DIR}"/{certs,raw,media,logs,db}
chmod 700 "${ARM_DIR}/certs"
chmod 2775 "${ARM_DIR}/raw" "${ARM_DIR}/media" "${ARM_DIR}/logs"

if [[ -f "${ARM_DIR}/certs/arm-ca.crt" ]]; then
    echo "==> certs already present in arm/certs/ — skipping bootstrap"
else
    echo "==> generating internal CA + leaves via install.sh --certs-only"
    bash "${ROOT_DIR}/install.sh" \
        --prefix "${ARM_DIR}" \
        --certs-only \
        --no-env \
        --no-compose \
        --no-udev
fi

# docker-compose.yml is generated per host (gitignored, like .env): bootstrap
# it from the committed docker-compose.yml.example template. Drives are NOT
# enumerated here: the backend's scanner finds them and the operator enrolls
# from the UI (drive lifecycle spec §5).
COMPOSE_FILE_PATH="${ROOT_DIR}/docker-compose.yml"
COMPOSE_TEMPLATE_PATH="${ROOT_DIR}/docker-compose.yml.example"

generate_compose() {
    # The dev compose is a generated artifact (gitignored, like .env): always
    # regenerate it from the committed template so static services stay in
    # sync — knobs live in .env, so there are no hand-edits to preserve.
    # Drives are NOT enumerated here: the backend's scanner finds them and the
    # operator enrolls from the UI (drive lifecycle spec §5).
    if [[ ! -f "${COMPOSE_TEMPLATE_PATH}" ]]; then
        echo "ERROR: ${COMPOSE_TEMPLATE_PATH} missing; cannot create docker-compose.yml." >&2
        exit 1
    fi
    echo "==> generating docker-compose.yml from docker-compose.yml.example"
    cp "${COMPOSE_TEMPLATE_PATH}" "${COMPOSE_FILE_PATH}"
}

generate_compose

ENV_FILE="${ROOT_DIR}/.env"
if [[ -f "${ENV_FILE}" ]]; then
    echo "==> ${ENV_FILE} exists — preserving secrets, refreshing ARM_GPUS"
else
    echo "==> creating .env from .env.example with generated secrets"
    pg_pass="$(openssl rand -hex 24)"
    arm_tok="$(openssl rand -hex 32)"
    puid="$(id -u)"
    pgid="$(id -g)"
    cdrom_gid="$(getent group cdrom | cut -d: -f3 || true)"
    cdrom_gid="${cdrom_gid:-44}"

    sed \
        -e "s|change-me-openssl-rand-hex-24|${pg_pass}|" \
        -e "s|change-me-openssl-rand-hex-32|${arm_tok}|" \
        -e "s|^PUID=.*|PUID=${puid}|" \
        -e "s|^PGID=.*|PGID=${pgid}|" \
        -e "s|^CDROM_GID=.*|CDROM_GID=${cdrom_gid}|" \
        "${ROOT_DIR}/.env.example" > "${ENV_FILE}"
    chmod 600 "${ENV_FILE}"
fi

# Refresh ARM_GPUS from host detection in both cases (it's derived, not a secret).
ARM_GPUS_VALUE="$(detect_gpus)"
if grep -q '^ARM_GPUS=' "${ENV_FILE}"; then
    sed -i "s|^ARM_GPUS=.*|ARM_GPUS=${ARM_GPUS_VALUE}|" "${ENV_FILE}"
else
    printf 'ARM_GPUS=%s\n' "${ARM_GPUS_VALUE}" >> "${ENV_FILE}"
fi
echo "==> detected GPU(s) for ARM_GPUS: ${ARM_GPUS_VALUE}"

# Render-node group for VAAPI/QSV device access (set-or-append, like ARM_GPUS).
RENDER_GID_VALUE="$(detect_render_gid || true)"
if grep -q '^ARM_RENDER_GID=' "${ENV_FILE}"; then
    sed -i "s|^ARM_RENDER_GID=.*|ARM_RENDER_GID=${RENDER_GID_VALUE}|" "${ENV_FILE}"
else
    printf 'ARM_RENDER_GID=%s\n' "${RENDER_GID_VALUE}" >> "${ENV_FILE}"
fi
echo "==> detected render group GID for ARM_RENDER_GID: ${RENDER_GID_VALUE:-(none)}"

# The transcode image is built by `docker compose up -d --build` like every other
# service (the arm-transcode service has deploy.replicas:0 — built, never run), so
# there's no separate build step here.

# Prevent the host's udisks2/gvfs from auto-mounting optical drives ARM
# wants to drive. Without this, post-rip `eject` from the ripper
# container fails with EBUSY because the host mount holds /dev/srN.
# See docs/arch/06-deployment.md.
UDEV_RULE_PATH="/etc/udev/rules.d/99-arm-no-automount.rules"
build_udev_rule_content() {
    cat <<'RULE'
# Managed by devtools/setup-dev.sh — do not edit by hand.
# Disables host auto-mount for optical drives so an ARM ripper container can
# eject after a rip. Drives are hot-plugged and enrolled from the UI after
# install, so the rule is not scoped per drive: ARM owns the optical drives
# on this host. See docs/arch/06-deployment.md#host-side-auto-mount-must-be-disabled
SUBSYSTEM=="block", KERNEL=="sr[0-9]*", ENV{UDISKS_AUTO}="0"
RULE
}

ensure_udev_rule() {
    if ! command -v udevadm >/dev/null 2>&1; then
        echo "==> udevadm not on PATH — skipping host udev rule (non-Linux host?)"
        return 0
    fi

    local desired
    desired="$(build_udev_rule_content)"

    if [[ -r "${UDEV_RULE_PATH}" ]] && diff -q "${UDEV_RULE_PATH}" <(printf '%s' "${desired}") >/dev/null 2>&1; then
        echo "==> host udev rule already current at ${UDEV_RULE_PATH}"
        return 0
    fi

    if ! sudo -n true 2>/dev/null; then
        echo "==> sudo needs a password; to install the udev rule run:"
        echo "    printf '%s' \"\$(cat <<'RULE'"
        printf '%s\n' "${desired}"
        echo "RULE"
        echo "    )\" | sudo tee ${UDEV_RULE_PATH}"
        echo "    sudo udevadm control --reload-rules"
        echo "    sudo udevadm trigger --subsystem-match=block"
        return 0
    fi

    echo "==> writing host udev rule at ${UDEV_RULE_PATH} (sudo)"
    printf '%s' "${desired}" | sudo tee "${UDEV_RULE_PATH}" >/dev/null
    sudo udevadm control --reload-rules
    sudo udevadm trigger --subsystem-match=block 2>/dev/null || sudo udevadm trigger
    echo "==> udev rule installed; udisks2 will skip auto-mount for ARM drives"
}

ensure_udev_rule

cat <<EOF

done — next:
  docker compose -f ${ROOT_DIR}/docker-compose.yml up -d --build
  then open https://localhost:8081 → Drives → Enroll each drive you want ARM to use

  optional — trust the local CA so browsers/curl skip the self-signed warning:
    bash devtools/trust-ca.sh

IDE: point your interpreter at ${ROOT_DIR}/.venv/bin/python
EOF
