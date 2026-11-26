#!/usr/bin/env bash
# services/_common/test-entrypoint-makemkv-home.sh
# Zero-infra unit test for own_makemkv_home. Sources the entrypoint via its
# ARM_ENTRYPOINT_SOURCE_ONLY seam and shadows chown/install with recorders, so
# it runs unprivileged.
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
INSTALL_LOG=()
install() { INSTALL_LOG+=("$*"); mkdir -p "${!#}"; }

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

# --- case 1: files baked into the image (sdf.bin, the .sdf_refreshed
# sentinel) are handed to arm along with the directory. With a PUID remap the
# build-time uid 1000 no longer matches arm, and update_sdf.sh dies touching a
# sentinel it does not own. ---
mkdir -p "${tmp}/.MakeMKV"
: >"${tmp}/.MakeMKV/sdf.bin"
: >"${tmp}/.MakeMKV/.sdf_refreshed"
own_makemkv_home "${tmp}"
[[ ${#INSTALL_LOG[@]} -eq 0 ]] || fail "existing dir must not be re-created: ${INSTALL_LOG[*]}"
[[ " ${CHOWN_LOG[*]} " == *" arm:arm ${tmp} "* ]] || fail "home not chowned: ${CHOWN_LOG[*]}"
[[ " ${CHOWN_LOG[*]} " == *" -R arm:arm ${tmp}/.MakeMKV "* ]] \
    || fail "MakeMKV dir must be chowned recursively: ${CHOWN_LOG[*]}"

# --- case 2: a missing MakeMKV dir is created arm-owned ---
CHOWN_LOG=(); INSTALL_LOG=()
rm -rf "${tmp}/.MakeMKV"
own_makemkv_home "${tmp}"
[[ "${INSTALL_LOG[0]:-}" == "-d -o arm -g arm ${tmp}/.MakeMKV" ]] || fail "install: ${INSTALL_LOG[*]}"

echo "test-entrypoint-makemkv-home: OK"
