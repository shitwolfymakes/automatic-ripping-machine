#!/usr/bin/env bash
# shellcheck disable=SC2317,SC2329
# (Shadow functions below are invoked indirectly by sourced install.sh code —
# newer shellcheck flags them unreachable; this is the documented
# "ignore if invoked indirectly" case.)
# Plain-bash unit test for install.sh's remote-offload walkthrough machinery:
# output helpers, input validators, paste-block generators, verify-step
# classification, and the completion table. Sources install.sh via
# ARM_INSTALL_SOURCE_ONLY; no docker, no root, no network.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL="${HERE}/../install.sh"

if ! grep -q 'ARM_INSTALL_SOURCE_ONLY' "$INSTALL"; then
    echo "FAIL - install.sh has no ARM_INSTALL_SOURCE_ONLY seam; refusing to source it" >&2
    exit 1
fi

export ARM_INSTALL_SOURCE_ONLY=1
# shellcheck disable=SC1090
source "$INSTALL"

fail=0
check() {  # check <label> <expected> <actual>
    local label="$1" want="$2" got="$3"
    if [[ "$want" == "$got" ]]; then
        echo "ok   - ${label}"
    else
        echo "FAIL - ${label}: expected '${want}', got '${got}'" >&2
        fail=1
    fi
}

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

# --- output helpers ----------------------------------------------------------

out="$(log "hello world")"
check "log: plain two-space indent, no marker" "  hello world" "$out"

out="$(section 2 6 "Remote transcode offload")"
check "section: ruled header" "yes" "$( [[ "$out" == *"── [2/6] Remote transcode offload ──"* ]] && echo yes || echo no )"

out="$(okline "docker reachable")"
check "okline: check mark" "  ✓ docker reachable" "$out"
out="$(failline "not authorized")"
check "failline: cross mark" "  ✗ not authorized" "$out"
out="$(warnline "udev skipped")"
check "warnline: bang" "  ! udev skipped" "$out"

out="$(fence_open "paste EVERYTHING between the lines, on 192.168.0.92 (as sam)")"
check "fence_open: labeled rule" "yes" "$( [[ "$out" == *"──── paste EVERYTHING between the lines, on 192.168.0.92 (as sam) ────"* ]] && echo yes || echo no )"
out="$(fence_close)"
check "fence_close: bare rule" "yes" "$( [[ "$out" == ──────* ]] && echo yes || echo no )"

# run_quiet: silent on success, replays captured output on failure
out="$(run_quiet true 2>&1)"
check "run_quiet: silent on success" "" "$out"
rc=0; out="$(run_quiet sh -c 'echo boom-detail >&2; exit 3' 2>&1)" || rc=$?
check "run_quiet: rc passthrough" "3" "$rc"
check "run_quiet: replays output on failure" "yes" "$( [[ "$out" == *boom-detail* ]] && echo yes || echo no )"

exit "$fail"
