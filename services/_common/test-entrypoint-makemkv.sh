#!/usr/bin/env bash
# services/_common/test-entrypoint-makemkv.sh
# Zero-infra unit test for seed_makemkv_sdf / prepare_makemkv_dir. Sources the
# entrypoint via its ARM_ENTRYPOINT_SOURCE_ONLY seam and shadows chown with a
# recorder, so it runs unprivileged.
# shellcheck disable=SC2317,SC2329  # shadow functions are invoked indirectly
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARM_ENTRYPOINT_SOURCE_ONLY=1
export ARM_ENTRYPOINT_SOURCE_ONLY
# shellcheck disable=SC1091
source "${HERE}/docker-entrypoint.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }

CHOWN_LOG=()
chown() { CHOWN_LOG+=("$*"); }

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT
seed="${tmp}/seed"
home="${tmp}/home/arm"
vol="${home}/.MakeMKV"
mkdir -p "${seed}"
printf 'seed-sdf' >"${seed}/sdf.bin"
touch -d '2026-01-02' "${seed}/.sdf_refreshed"

# --- no seed baked (non-ripper image or failed bake): nothing happens ---
seed_makemkv_sdf "${tmp}/absent" "${vol}"
[[ ! -e "${vol}" ]] || fail "absent seed must not create the volume dir"

# --- case 1: empty volume is seeded, sentinel mtime copied ---
mkdir -p "${vol}"
seed_makemkv_sdf "${seed}" "${vol}"
[[ "$(<"${vol}/sdf.bin")" == "seed-sdf" ]] || fail "empty volume not seeded"
[[ "${vol}/.sdf_refreshed" -nt "${seed}/.sdf_refreshed" ]] && fail "sentinel mtime not copied"
[[ "${seed}/.sdf_refreshed" -nt "${vol}/.sdf_refreshed" ]] && fail "sentinel mtime not copied"

# --- case 2: a fresher volume (runtime refresh) is kept ---
printf 'fresh-sdf' >"${vol}/sdf.bin"
touch -d '2026-06-01' "${vol}/.sdf_refreshed"
seed_makemkv_sdf "${seed}" "${vol}"
[[ "$(<"${vol}/sdf.bin")" == "fresh-sdf" ]] || fail "fresher volume was overwritten"

# --- case 3: a newer seed (new image) replaces an older volume copy ---
touch -d '2026-12-01' "${seed}/.sdf_refreshed"
printf 'new-seed' >"${seed}/sdf.bin"
seed_makemkv_sdf "${seed}" "${vol}"
[[ "$(<"${vol}/sdf.bin")" == "new-seed" ]] || fail "newer seed not applied"

# --- case 4: sentinel missing re-seeds even over an existing sdf.bin ---
rm -f "${vol}/.sdf_refreshed"
printf 'stale' >"${vol}/sdf.bin"
seed_makemkv_sdf "${seed}" "${vol}"
[[ "$(<"${vol}/sdf.bin")" == "new-seed" ]] || fail "missing sentinel must re-seed"

# --- prepare_makemkv_dir: creates, seeds-independent, chowns recursively ---
rm -rf "${home}"
mkdir -p "${home}"
CHOWN_LOG=()
prepare_makemkv_dir "${vol}"
[[ -d "${vol}" ]] || fail "dir not created"
[[ "${CHOWN_LOG[0]}" == "arm:arm ${home}" ]] || fail "home chown: ${CHOWN_LOG[0]}"
[[ "${CHOWN_LOG[1]}" == "-R arm:arm ${vol}" ]] || fail "recursive chown: ${CHOWN_LOG[1]}"

echo "test-entrypoint-makemkv: OK"
