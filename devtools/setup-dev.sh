#!/usr/bin/env bash
# One-shot dev-environment setup for the walking skeleton.
# Idempotent — rerunning skips work already done and leaves existing .env alone.
#
# Usage:  bash devtools/setup-dev.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

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

# Phase 7b: enumerate GPUs host-side so the GPU-free backend can fill the `gpus`
# table from ARM_GPUS instead of probing hardware. Prints a compact JSON array
# (empty `[]` if none). Mirrors services/backend/arm_backend/gpu_probe.py and the
# detect_gpus in install.sh.
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
            entries+=("{\"vendor\":\"${vendor}\",\"device_path\":\"${node}\",\"encoder_kinds\":[\"h264\",\"h265\"]}")
        done
    fi
    if command -v nvidia-smi >/dev/null 2>&1; then
        while IFS= read -r idx; do
            [[ -n "${idx}" ]] || continue
            entries+=("{\"vendor\":\"nvenc\",\"device_path\":\"nvidia://${idx}\",\"encoder_kinds\":[\"h264\",\"h265\"]}")
        done < <(nvidia-smi -L 2>/dev/null | sed -nE 's/^GPU ([0-9]+):.*/\1/p')
    fi
    local IFS=,
    printf '[%s]' "${entries[*]:-}"
}

require uv      "install: curl -LsSf https://astral.sh/uv/install.sh | sh"
require docker  "install: https://docs.docker.com/engine/install/"
require openssl "openssl should be present on any linux system"
require lsscsi  "drive enumeration needs lsscsi: 'apt-get install lsscsi' (Debian/Ubuntu), 'dnf install lsscsi' (Fedora), 'pacman -S lsscsi' (Arch)"

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

if [[ -f "${ROOT_DIR}/certs/arm-ca.crt" ]]; then
    echo "==> certs already present in certs/ — skipping bootstrap"
else
    echo "==> generating internal CA + leaves via install.sh --certs-only"
    bash "${ROOT_DIR}/install.sh" \
        --prefix "${ROOT_DIR}" \
        --certs-only \
        --no-env \
        --no-compose \
        --no-udev
fi

# docker-compose.yml is generated per host (gitignored, like .env): bootstrap it
# from the committed docker-compose.yml.example template, then splice one
# arm-ripper-srN service per optical drive into its GENERATED region (between the
# `>>>/<<< arm-ripper services` sentinels). Static services (db/backend/ui/
# transcode) live in the template above the sentinels; only the ripper blocks
# below them are machine-written.
#
# `lsscsi -g` is the reliable source for the /dev/srN ↔ /dev/sgM pairing:
# MakeMKV enumerates drives via SCSI-generic ioctls, and that node is NOT
# lexicographically tied to the block device (sr0 may pair with sg2, sr1 with
# sg6) — so we read the pairing straight out of lsscsi's last two columns.
COMPOSE_FILE_PATH="${ROOT_DIR}/docker-compose.yml"
COMPOSE_TEMPLATE_PATH="${ROOT_DIR}/docker-compose.yml.example"
RIPPER_BEGIN_MARK="# >>> arm-ripper services"

DRIVES_SR=()   # bare drive numbers, e.g. (0 1)
DRIVES_SG=()   # matching sg node names, index-aligned, e.g. (sg2 sg6)

detect_optical_drives() {
    DRIVES_SR=()
    DRIVES_SG=()
    local line srdev sgdev
    while IFS= read -r line; do
        [[ -z "${line}" ]] && continue
        srdev="${line%% *}"   # /dev/srN
        sgdev="${line##* }"   # /dev/sgM
        DRIVES_SR+=("${srdev#/dev/sr}")
        DRIVES_SG+=("${sgdev#/dev/}")
    done < <(
        lsscsi -g 2>/dev/null | awk '
            $2 == "cd/dvd" {
                blk = ""; gen = ""
                for (i = 1; i <= NF; i++) {
                    if ($i ~ /^\/dev\/sr[0-9]+$/)      blk = $i
                    else if ($i ~ /^\/dev\/sg[0-9]+$/) gen = $i
                }
                if (blk != "" && gen != "") print blk, gen
            }' | sort -V || true
    )
}

emit_ripper_block() {
    local n="$1" sg="$2"
    cat <<EOF

  arm-ripper-sr${n}:
    build:
      context: .
      dockerfile: services/ripper/Dockerfile
    container_name: armv3-ripper-sr${n}
    hostname: arm-ripper-sr${n}
    restart: unless-stopped
    depends_on:
      - arm-backend
    devices:
      - "/dev/sr${n}:/dev/sr${n}"
      # MakeMKV reads the disc via SCSI-generic ioctls, not the block device.
      # /dev/${sg} is the sg node paired with /dev/sr${n} by \`lsscsi -g\` (NOT
      # lexicographically). Re-run devtools/setup-dev.sh if the pairing moves.
      - "/dev/${sg}:/dev/${sg}"
    # Unprivileged: MakeMKV (SCSI generic) + the pydvdid CRC64 off the block
    # device (PyCdlib) both need only \`cdrom\` group membership. No mount, so
    # no CAP_SYS_ADMIN and no AppArmor exception.
    group_add:
      - "\${CDROM_GID:-44}"
    environment:
      ARM_DRIVE_DEV: /dev/sr${n}
      ARM_BACKEND_URL: https://arm-backend:8443
      ARM_SERVICE_TOKEN: \${ARM_SERVICE_TOKEN}
      ARM_LOG_LEVEL: \${ARM_LOG_LEVEL:-info}
      PUID: \${PUID:-1000}
      PGID: \${PGID:-1000}
      CDROM_GID: \${CDROM_GID:-44}
    volumes:
      - ./raw:/raw
      - ./logs:/logs
      - ./certs/arm-ca.crt:/etc/ssl/arm/arm-ca.crt:ro
      - ./certs/arm-ripper-sr${n}.crt:/etc/ssl/arm/tls.crt:ro
      - ./certs/arm-ripper-sr${n}.key:/etc/ssl/arm/tls.key:ro
EOF
}

# A drive attached after the initial cert bootstrap (when the certs/ dir
# already existed, so the block above was skipped) won't have a leaf cert.
# install.sh --certs-only regenerates every leaf, including the new drive.
ensure_ripper_certs() {
    local i n missing=0
    for i in "${!DRIVES_SR[@]}"; do
        n="${DRIVES_SR[$i]}"
        if [[ ! -f "${ROOT_DIR}/certs/arm-ripper-sr${n}.crt" \
           || ! -f "${ROOT_DIR}/certs/arm-ripper-sr${n}.key" ]]; then
            missing=1
        fi
    done
    if [[ ${missing} -eq 1 ]]; then
        echo "==> a detected drive is missing its leaf cert — regenerating via install.sh --certs-only"
        bash "${ROOT_DIR}/install.sh" \
            --prefix "${ROOT_DIR}" --certs-only --no-env --no-compose --no-udev
    fi
}

generate_ripper_services() {
    # Bootstrap the gitignored dev compose from the committed template the first
    # time (same copy-if-missing semantics as .env from .env.example). Existing
    # files are left alone so local tweaks survive; delete docker-compose.yml and
    # re-run to refresh the static services from the template.
    if [[ ! -f "${COMPOSE_FILE_PATH}" ]]; then
        if [[ ! -f "${COMPOSE_TEMPLATE_PATH}" ]]; then
            echo "ERROR: ${COMPOSE_TEMPLATE_PATH} missing; cannot create docker-compose.yml." >&2
            exit 1
        fi
        echo "==> creating docker-compose.yml from docker-compose.yml.example"
        cp "${COMPOSE_TEMPLATE_PATH}" "${COMPOSE_FILE_PATH}"
    fi

    if ! grep -qF "${RIPPER_BEGIN_MARK}" "${COMPOSE_FILE_PATH}"; then
        echo "ERROR: ${COMPOSE_FILE_PATH} lacks the '${RIPPER_BEGIN_MARK}' sentinel; cannot splice rippers." >&2
        exit 1
    fi

    detect_optical_drives

    local blocks_file
    blocks_file="$(mktemp)"
    {
        echo "  # Re-run \`bash devtools/setup-dev.sh\` after attaching or removing a drive —"
        echo "  # this region is regenerated from \`lsscsi -g\`, so don't hand-edit it."
    } >> "${blocks_file}"

    if [[ ${#DRIVES_SR[@]} -eq 0 ]]; then
        echo "==> no optical drives found via lsscsi — ripper region left empty"
        echo "  # (no optical drives detected on this host)" >> "${blocks_file}"
    else
        ensure_ripper_certs
        local i summary=""
        for i in "${!DRIVES_SR[@]}"; do
            summary+="sr${DRIVES_SR[$i]}↔${DRIVES_SG[$i]} "
            emit_ripper_block "${DRIVES_SR[$i]}" "${DRIVES_SG[$i]}" >> "${blocks_file}"
        done
        echo "==> detected ${#DRIVES_SR[@]} optical drive(s): ${summary}"
    fi

    local tmp
    tmp="$(mktemp)"
    awk -v blockfile="${blocks_file}" '
        index($0, "# >>> arm-ripper services") {
            print
            while ((getline line < blockfile) > 0) print line
            close(blockfile)
            skip = 1
            next
        }
        index($0, "# <<< arm-ripper services") { skip = 0; print; next }
        skip { next }
        { print }
    ' "${COMPOSE_FILE_PATH}" > "${tmp}"
    mv "${tmp}" "${COMPOSE_FILE_PATH}"
    rm -f "${blocks_file}"
    echo "==> wrote ${#DRIVES_SR[@]} ripper service(s) into ${COMPOSE_FILE_PATH}"
}

generate_ripper_services

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

# Build the fat HW transcode image locally (dev never pulls it). The dispatcher
# spawns it ephemerally per task; it lives behind the `build-transcode` profile
# so a plain `docker compose up` never starts it. Without this build the
# dispatcher would try to pull `arm-transcode:latest` and every transcode fails
# on a fresh dev box. Always rebuild so it tracks local source changes.
echo "==> building arm-transcode:latest locally (fat multi-vendor HW image)"
( cd "${ROOT_DIR}" && docker compose --profile build-transcode build arm-transcode-builder )

# Prevent the host's udisks2/gvfs from auto-mounting optical drives ARM
# wants to drive. Without this, post-rip `eject` from the ripper
# container fails with EBUSY because the host mount holds /dev/srN.
# Per-drive scope by ID_PATH so we don't disturb other optical drives
# on the host. See docs/arch/06-deployment.md.
UDEV_RULE_PATH="/etc/udev/rules.d/99-arm-no-automount.rules"
build_udev_rule_content() {
    local drives=()
    shopt -s nullglob
    drives=(/dev/sr[0-9]*)
    shopt -u nullglob
    if [[ ${#drives[@]} -eq 0 ]]; then
        return 1
    fi

    local rule_lines=()
    for dev in "${drives[@]}"; do
        local id_path
        id_path="$(udevadm info "${dev}" 2>/dev/null | sed -nE 's|^E: ID_PATH=(.*)|\1|p' | head -n 1)"
        if [[ -n "${id_path}" ]]; then
            rule_lines+=("SUBSYSTEM==\"block\", KERNEL==\"sr[0-9]*\", ENV{ID_PATH}==\"${id_path}\", ENV{UDISKS_AUTO}=\"0\"")
        else
            echo "WARN: ${dev} has no ID_PATH — skipping (rule scoping needs a stable identifier)" >&2
        fi
    done

    if [[ ${#rule_lines[@]} -eq 0 ]]; then
        return 1
    fi

    cat <<HEADER
# Managed by devtools/setup-dev.sh — do not edit by hand.
# Disables host auto-mount for ARM-managed optical drives so the ripper
# container can eject after a rip. See:
#   docs/arch/06-deployment.md#host-side-auto-mount-must-be-disabled
HEADER
    printf '%s\n' "${rule_lines[@]}"
}

ensure_udev_rule() {
    if ! command -v udevadm >/dev/null 2>&1; then
        echo "==> udevadm not on PATH — skipping host udev rule (non-Linux host?)"
        return 0
    fi

    local desired
    if ! desired="$(build_udev_rule_content)"; then
        echo "==> no usable optical drives detected — skipping host udev rule"
        return 0
    fi

    if [[ -r "${UDEV_RULE_PATH}" ]] && diff -q "${UDEV_RULE_PATH}" <(printf '%s' "${desired}") >/dev/null 2>&1; then
        echo "==> host udev rule already current at ${UDEV_RULE_PATH}"
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

IDE: point your interpreter at ${ROOT_DIR}/.venv/bin/python
EOF
