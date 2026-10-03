#!/usr/bin/env bash
# devtools/install-drill.sh: end-to-end drill of the production installer
# against images built from this checkout. Manual, not in CI.
#
# It installs into a throwaway folder with the ripper-only profile, starts the
# stack, checks the backend's health, runs `armctl down`, and removes what it
# created. No host changes are made (--no-host-changes).
#
# Run it on a host that has NO ARM v3 stack: the stack's container names and
# its data volume are fixed (armv3-*, armv3_arm-data), so a drill beside a dev
# stack or a real install would collide with it. The script refuses if it
# finds either.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PFX="arm-drill"
TAG="drill"

# Captured first: with pipefail, `docker ... | grep -q` can report failure when
# grep matches and exits early, which would skip this guard.
containers="$(docker ps -a --format '{{.Names}}')"
volumes="$(docker volume ls -q)"
if grep -q '^armv3-' <<<"${containers}" || grep -qx 'armv3_arm-data' <<<"${volumes}"; then
    echo "ERROR: an ARM v3 stack or its data volume already exists on this host." >&2
    echo "       Run the drill on a host without one (bash devtools/setup-dev.sh down does not remove the volume)." >&2
    exit 1
fi

WORK="$(mktemp -d)"
cleanup() {
    echo "==> cleaning up"
    if [[ -x "${WORK}/arm/armctl" ]]; then
        "${WORK}/arm/armctl" down --force >/dev/null 2>&1 || true
    fi
    docker volume rm armv3_arm-data >/dev/null 2>&1 || true
    # The database folder is written by the postgres container's user.
    docker run --rm -v "${WORK}:/w" postgres:18 sh -c 'rm -rf /w/arm' >/dev/null 2>&1 || true
    rm -rf "${WORK}"
}
trap cleanup EXIT

echo "==> building images from this checkout as ${PFX}/arm-*:${TAG}"
docker build -q -f "${ROOT}/services/backend/Dockerfile" -t "${PFX}/arm-backend:${TAG}" "${ROOT}"
docker build -q -f "${ROOT}/services/ripper/Dockerfile"  -t "${PFX}/arm-ripper:${TAG}"  "${ROOT}"
docker build -q -f "${ROOT}/services/ui-neu/Dockerfile"  -t "${PFX}/arm-ui:${TAG}"      "${ROOT}"
docker pull -q postgres:18

echo "==> packing the bundle"
bundle="$(bash "${ROOT}/deploy/build-bundle.sh" "${TAG}" "${WORK}/bundle")"

echo "==> installing into ${WORK}/arm (ripper-only, no host changes, not started)"
bash "${ROOT}/install.sh" --prefix "${WORK}" --bundle "${bundle}" --version "${TAG}" \
    --profile ripper-only --image-prefix "${PFX}" --no-host-changes --no-start </dev/null

echo "==> starting from the local images"
"${WORK}/arm/armctl" up --no-pull --no-backup

echo "==> checks"
"${WORK}/arm/armctl" compose ps
test -f "${WORK}/arm/certs/arm-ca.crt"
test "$(stat -c '%a' "${WORK}/arm/.armctl/.env")" = "600"
grep -q '^ARM_TRANSCODE_CAPABLE=false$' "${WORK}/arm/.armctl/.env"

echo "==> a second up, to exercise the backup and the ripper cleanup"
"${WORK}/arm/armctl" up --no-pull
ls "${WORK}/arm/backups"/pg-backup-*.sql.gz >/dev/null

echo "==> down"
"${WORK}/arm/armctl" down

echo "DRILL PASSED"
