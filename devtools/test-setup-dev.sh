#!/usr/bin/env bash
# devtools/test-setup-dev.sh — zero-infra assertions that the dev installer
# and the compose template no longer enumerate drives (drive lifecycle §5).
# Uses `docker compose config` when docker is present, grep otherwise.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"
SETUP="${ROOT}/devtools/setup-dev.sh"
TEMPLATE="${ROOT}/docker-compose.yml.example"

fail=0
check() {  # check <label> <expected-rc> <actual-rc>
    local label="$1" want="$2" got="$3"
    if [[ "${want}" == "${got}" ]]; then echo "ok   - ${label}"; else echo "FAIL - ${label} (want rc=${want}, got rc=${got})"; fail=1; fi
}
absent() {  # absent <label> <pattern> <file>
    local rc=0; grep -qE -- "$2" "$3" || rc=$?
    check "$1" 1 "${rc}"
}
present() {  # present <label> <pattern> <file>
    local rc=0; grep -qE -- "$2" "$3" || rc=$?
    check "$1" 0 "${rc}"
}

# --- setup-dev.sh: no drive enumeration -------------------------------------
absent "setup-dev has no lsscsi"                'lsscsi'                    "${SETUP}"
absent "setup-dev has no ARM_DRIVE_SERIAL"      'ARM_DRIVE_SERIAL'          "${SETUP}"
absent "setup-dev has no ripper sentinel"       'arm-ripper services'       "${SETUP}"
absent "setup-dev has no per-ripper leaf certs" 'arm-ripper-sr'             "${SETUP}"
absent "setup-dev has no detect_optical_drives" 'detect_optical_drives'     "${SETUP}"
absent "setup-dev has no ensure_ripper_certs"   'ensure_ripper_certs'       "${SETUP}"
present "setup-dev udev rule covers every optical drive" 'KERNEL=="sr\[0-9\]\*", ENV\{UDISKS_AUTO\}="0"' "${SETUP}"
absent "setup-dev udev rule no longer scopes by ID_PATH" 'ID_PATH'          "${SETUP}"

# --- compose template -----------------------------------------------------------
absent  "template has no generated region"      'arm-ripper services'       "${TEMPLATE}"
absent  "template has no arm-ripper-srN"        'arm-ripper-sr'             "${TEMPLATE}"
present "template has the arm-ripper service"   '^  arm-ripper:$'           "${TEMPLATE}"
present "arm-ripper image defaults like transcode" 'ARM_RIPPER_IMAGE:-arm-ripper:latest' "${TEMPLATE}"
present "backend gets /dev/disk read-only"      '/dev/disk:/host-disk:ro'   "${TEMPLATE}"
present "backend receives ARM_RIPPER_IMAGE"     'ARM_RIPPER_IMAGE: \$\{ARM_RIPPER_IMAGE' "${TEMPLATE}"
present "backend forwards ripper poll tunable"  'ARM_RIPPER_POLL_INTERVAL_SECONDS' "${TEMPLATE}"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    envfile="$(mktemp)"
    printf 'POSTGRES_USER=a\nPOSTGRES_PASSWORD=b\nPOSTGRES_DB=c\nARM_SERVICE_TOKEN=t\n' > "${envfile}"
    services=""
    services="$(cd "${ROOT}" && docker compose --env-file "${envfile}" -f "${TEMPLATE}" config --services 2>/dev/null)" || true
    rm -f "${envfile}"
    rc=0; grep -qx 'arm-ripper' <<<"${services}" || rc=$?
    check "compose config lists arm-ripper" 0 "${rc}"
    rc=0; grep -q 'arm-ripper-sr' <<<"${services}" || rc=$?
    check "compose config lists no arm-ripper-srN" 1 "${rc}"
    envfile="$(mktemp)"
    printf 'POSTGRES_USER=a\nPOSTGRES_PASSWORD=b\nPOSTGRES_DB=c\nARM_SERVICE_TOKEN=t\n' > "${envfile}"
    replicas=""
    replicas="$(cd "${ROOT}" && docker compose --env-file "${envfile}" -f "${TEMPLATE}" config 2>/dev/null | awk '/^  arm-ripper:$/{f=1} f && /replicas:/{print $2; exit}')" || true
    rm -f "${envfile}"
    check "arm-ripper has replicas: 0" "0" "${replicas:-missing}"
else
    echo "skip - docker compose not available; template checked by grep only"
fi

# --- iso-smoke.sh: register-by-id -------------------------------------------------
SMOKE="${ROOT}/devtools/iso-smoke.sh"
absent  "iso-smoke no longer mounts per-ripper certs" 'arm-ripper-sr0\.(crt|key)' "${SMOKE}"
absent  "iso-smoke has no arm-ripper-sr0 service"     'RIPPER_SERVICE="arm-ripper-sr0"' "${SMOKE}"
present "iso-smoke passes ARM_DRIVE_ID"               '-e ARM_DRIVE_ID=' "${SMOKE}"
present "iso-smoke pauses the managed ripper by label" 'label=arm.drive_id=' "${SMOKE}"
present "iso-smoke uses the arm/ data dirs"           'ROOT_DIR\}/arm/raw:/raw' "${SMOKE}"
rc=0; bash -n "${SMOKE}" || rc=$?
check "iso-smoke parses" 0 "${rc}"

exit "${fail}"
