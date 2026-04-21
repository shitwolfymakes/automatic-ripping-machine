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
    echo "==> generating internal CA + leaves"
    bash "${SCRIPT_DIR}/bootstrap-certs.sh"
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

cat <<EOF

done — next:
  docker compose -f ${V3_DIR}/docker-compose.yml up -d --build

IDE: point your interpreter at ${V3_DIR}/.venv/bin/python
EOF
