#!/usr/bin/env bash
# services/_common/test-entrypoint-optical.sh
# Zero-infra unit test for precreate_optical_nodes. Sources the entrypoint via
# its ARM_ENTRYPOINT_SOURCE_ONLY seam and shadows mknod/chgrp with recorders,
# so it runs unprivileged (real mknod of a block device needs CAP_MKNOD).
# shellcheck disable=SC2317,SC2329  # shadow functions are invoked indirectly
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARM_ENTRYPOINT_SOURCE_ONLY=1
export ARM_ENTRYPOINT_SOURCE_ONLY
# shellcheck disable=SC1091
source "${HERE}/docker-entrypoint.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }

# `out="$(precreate_optical_nodes ...)"` would fork a subshell for the command
# substitution, so MKNOD_LOG/CHGRP_LOG appends made by the shadowed mknod/chgrp
# during that call would vanish when the subshell exits — the parent's arrays
# would never see them. Route the summary line through a temp file instead so
# precreate_optical_nodes runs in *this* shell and its log mutations stick.
run_capture() {  # <dev_dir> <sr_max> <sg_max> <group> -> sets $out
    local capfile
    capfile="$(mktemp)"
    precreate_optical_nodes "$1" "$2" "$3" "$4" >"${capfile}"
    out="$(<"${capfile}")"
    rm -f "${capfile}"
}

MKNOD_LOG=()
CHGRP_LOG=()
mknod() {  # -m MODE PATH TYPE MAJOR MINOR
    MKNOD_LOG+=("$*")
    touch "$3"  # so the -e skip in the function sees the node next time
}
chgrp() { CHGRP_LOG+=("$*"); }

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

# --- case 1: fresh /dev creates the full range with the right numbers ---
run_capture "${tmp}" 1 2 cdrom-host
[[ ${#MKNOD_LOG[@]} -eq 5 ]] || fail "expected 5 mknod calls, got ${#MKNOD_LOG[@]}"
[[ "${MKNOD_LOG[0]}" == "-m 0660 ${tmp}/sr0 b 11 0" ]] || fail "sr0: ${MKNOD_LOG[0]}"
[[ "${MKNOD_LOG[1]}" == "-m 0660 ${tmp}/sr1 b 11 1" ]] || fail "sr1: ${MKNOD_LOG[1]}"
[[ "${MKNOD_LOG[2]}" == "-m 0660 ${tmp}/sg0 c 21 0" ]] || fail "sg0: ${MKNOD_LOG[2]}"
[[ "${MKNOD_LOG[4]}" == "-m 0660 ${tmp}/sg2 c 21 2" ]] || fail "sg2: ${MKNOD_LOG[4]}"
[[ ${#CHGRP_LOG[@]} -eq 5 ]] || fail "expected 5 chgrp calls, got ${#CHGRP_LOG[@]}"
[[ "${CHGRP_LOG[0]}" == "cdrom-host ${tmp}/sr0" ]] || fail "chgrp: ${CHGRP_LOG[0]}"
[[ "${out}" == *"created 5"* ]] || fail "summary: ${out}"

# --- case 2: existing nodes are skipped, never recreated ---
MKNOD_LOG=(); CHGRP_LOG=()
run_capture "${tmp}" 1 2 cdrom-host
[[ ${#MKNOD_LOG[@]} -eq 0 ]] || fail "second run must skip existing nodes, made ${#MKNOD_LOG[@]}"
[[ "${out}" == *"created 0"* ]] || fail "summary: ${out}"

# --- case 3: a partially populated /dev only fills the gaps ---
rm -f "${tmp}/sr1" "${tmp}/sg1"
MKNOD_LOG=()
precreate_optical_nodes "${tmp}" 1 2 cdrom-host >/dev/null
[[ ${#MKNOD_LOG[@]} -eq 2 ]] || fail "gap fill: expected 2, got ${#MKNOD_LOG[@]}"
[[ "${MKNOD_LOG[0]}" == *"/sr1 b 11 1" ]] || fail "gap sr1: ${MKNOD_LOG[0]}"
[[ "${MKNOD_LOG[1]}" == *"/sg1 c 21 1" ]] || fail "gap sg1: ${MKNOD_LOG[1]}"

echo "test-entrypoint-optical: OK"
