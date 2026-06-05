#!/usr/bin/env bash
# One-shot dev-environment setup for the v3 walking skeleton.
# Idempotent — rerunning skips work already done and leaves existing .env alone.
#
# Usage:  bash v3/devtools/setup-dev.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
V3_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

require() {
    local bin="$1"
    local hint="$2"
    if ! command -v "${bin}" >/dev/null 2>&1; then
        echo "ERROR: '${bin}' not found. ${hint}" >&2
        exit 1
    fi
}

require uv      "install: curl -LsSf https://astral.sh/uv/install.sh | sh"
require docker  "install: https://docs.docker.com/engine/install/"
require openssl "openssl should be present on any linux system"

if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: 'docker compose' (v2 plugin) not available" >&2
    exit 1
fi

echo "==> syncing host venv via uv"
( cd "${V3_DIR}" && uv sync )

if [[ -f "${V3_DIR}/certs/arm-ca.crt" ]]; then
    echo "==> certs already present in v3/certs/ — skipping bootstrap"
else
    echo "==> generating internal CA + leaves via install.sh --certs-only"
    bash "${V3_DIR}/install.sh" \
        --prefix "${V3_DIR}" \
        --certs-only \
        --no-env \
        --no-compose \
        --no-udev
fi

ENV_FILE="${V3_DIR}/.env"
if [[ -f "${ENV_FILE}" ]]; then
    echo "==> ${ENV_FILE} exists — leaving untouched"
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
        "${V3_DIR}/.env.example" > "${ENV_FILE}"
    chmod 600 "${ENV_FILE}"
fi

# Prevent the host's udisks2/gvfs from auto-mounting optical drives ARM
# wants to drive. Without this, post-rip `eject` from the ripper
# container fails with EBUSY because the host mount holds /dev/srN.
# Per-drive scope by ID_PATH so we don't disturb other optical drives
# on the host. See v3/docs/arch/06-deployment.md.
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
# Managed by v3/devtools/setup-dev.sh — do not edit by hand.
# Disables host auto-mount for ARM-managed optical drives so the ripper
# container can eject after a rip. See:
#   v3/docs/arch/06-deployment.md#host-side-auto-mount-must-be-disabled
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
  docker compose -f ${V3_DIR}/docker-compose.yml up -d --build

IDE: point your interpreter at ${V3_DIR}/.venv/bin/python
EOF
