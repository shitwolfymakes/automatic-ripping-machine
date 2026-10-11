#!/usr/bin/env bash
# deploy/build-bundle.sh <tag> <out-dir>: pack the release bundle.
#
# The bundle is what the bootstrap (install.sh) downloads into
# <arm>/.armctl/releases/<tag>/: the launcher, the shared library, the install
# modules, the release overlay, and the compose template and .env.example
# exactly as committed. Nothing in it is generated except VERSION.
# Prints the archive path. Used by release.yml, CI and devtools/install-drill.sh.
set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: build-bundle.sh <tag> <out-dir>" >&2
    exit 2
fi
tag="$1"
out="$2"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"

stage="$(mktemp -d)"
trap 'rm -rf "${stage}"' EXIT

mkdir -p "${stage}/lib" "${stage}/install"
cp "${HERE}/armctl.sh" "${stage}/armctl.sh"
cp "${HERE}"/lib/*.sh "${stage}/lib/"
cp "${HERE}"/install/*.sh "${stage}/install/"
cp "${HERE}/docker-compose.release.yml" "${stage}/docker-compose.release.yml"
cp "${ROOT}/docker-compose.yml.example" "${stage}/docker-compose.yml.example"
cp "${ROOT}/.env.example" "${stage}/.env.example"
cp "${ROOT}/install.sh" "${stage}/install.sh"
printf '%s\n' "${tag}" > "${stage}/VERSION"
chmod 755 "${stage}/armctl.sh" "${stage}/install.sh"
chmod 644 "${stage}"/lib/*.sh "${stage}"/install/*.sh "${stage}/docker-compose.release.yml" \
    "${stage}/docker-compose.yml.example" "${stage}/.env.example" "${stage}/VERSION"

mkdir -p "${out}"
out="$(cd "${out}" && pwd)"
name="arm-installer-${tag}.tar.gz"
# Fixed order, owner and timestamps, and no gzip header time, so the same
# commit always produces the same archive and checksum.
tar -C "${stage}" --sort=name --owner=0 --group=0 --numeric-owner \
    --mtime='2000-01-01 00:00:00Z' -cf - . | gzip -n > "${out}/${name}"
(cd "${out}" && sha256sum "${name}" > "${name}.sha256")
printf '%s\n' "${out}/${name}"
