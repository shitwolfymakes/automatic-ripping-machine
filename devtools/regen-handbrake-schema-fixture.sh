#!/usr/bin/env bash
# Regenerate packages/arm_common/tests/fixtures/handbrake-schema-<tag>.json.
#
# The transcode image's handbrake-builder stage dumps the HandBrake schema from
# libhb (services/transcode/schema/hb_schema_dump.c) to
# /usr/share/arm/handbrake-schema.json. The tests load a committed copy of that
# dump, so rerun this after bumping HANDBRAKE_VERSION or changing the helper,
# and commit the new fixture. Needs Docker; the HandBrake compile layers are
# cached after the first build.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." &>/dev/null && pwd)"
DOCKERFILE="services/transcode/Dockerfile"
IMAGE="arm-hb-builder"

cd "${ROOT_DIR}"

HANDBRAKE_VERSION="$(sed -n 's/^ARG HANDBRAKE_VERSION=//p' "${DOCKERFILE}")"
if [[ -z "${HANDBRAKE_VERSION}" ]]; then
    echo "regen-handbrake-schema-fixture: no HANDBRAKE_VERSION in ${DOCKERFILE}" >&2
    exit 1
fi
FIXTURE="packages/arm_common/tests/fixtures/handbrake-schema-${HANDBRAKE_VERSION}.json"

# The build context is the repo root, as in docker-compose.yml.example.
docker build -f "${DOCKERFILE}" --target handbrake-builder -t "${IMAGE}" .

# Write through a temp file so a failed run never leaves a truncated fixture.
mkdir -p "$(dirname -- "${FIXTURE}")"
tmp="$(mktemp)"
trap 'rm -f "${tmp}"' EXIT
docker run --rm "${IMAGE}" cat /usr/share/arm/handbrake-schema.json > "${tmp}"
chmod 644 "${tmp}"
mv "${tmp}" "${FIXTURE}"
echo "wrote ${FIXTURE}"
