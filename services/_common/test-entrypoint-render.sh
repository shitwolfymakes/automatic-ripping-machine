#!/usr/bin/env bash
# Plain-bash unit test for the entrypoint's render-node access setup.
# No bats — the repo gates shell with shellcheck only. Runs with no Docker,
# no root: it sources docker-entrypoint.sh (via ARM_ENTRYPOINT_SOURCE_ONLY)
# and drives setup_render_access with shadowed groupadd/usermod/getent/stat.
#
# Covers the RENDER_GID fragility: derivation from mounted render nodes
# (device nodes keep their HOST gid inside the container), explicit-override
# precedence, the gid-0 refusal, and the no-node no-op.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTRYPOINT="${HERE}/docker-entrypoint.sh"

# Fail fast if the source-only seam is missing: sourcing without it would run
# groupadd/usermod/exec on this machine.
if ! grep -q 'ARM_ENTRYPOINT_SOURCE_ONLY' "$ENTRYPOINT"; then
    echo "FAIL - docker-entrypoint.sh has no ARM_ENTRYPOINT_SOURCE_ONLY seam; refusing to source it" >&2
    exit 1
fi

export ARM_ENTRYPOINT_SOURCE_ONLY=1
# shellcheck disable=SC1090
source "$ENTRYPOINT"

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

# --- shadows: record group mutations instead of performing them --------------
# Scripted gid per node basename, set by each test via STAT_GIDS.
declare -A STAT_GIDS=()
GROUPADDS=()   # "gid:name"
USERMODS=()    # group names arm was appended to
GETENT_KNOWN=() # gids that "exist" in the image; name is grp<gid>

# shellcheck disable=SC2329
stat() {  # only the entrypoint's `stat -c '%g' <path>` form is exercised
    local path="${3:-${2:-}}"
    local base; base="$(basename "$path")"
    if [[ -n "${STAT_GIDS[$base]:-}" ]]; then
        printf '%s\n' "${STAT_GIDS[$base]}"
        return 0
    fi
    return 1
}
# shellcheck disable=SC2329
getent() {  # `getent group <gid>` → "grp<gid>:x:<gid>:" when known
    local gid="$2" g
    for g in "${GETENT_KNOWN[@]}"; do
        if [[ "$g" == "$gid" ]]; then
            printf 'grp%s:x:%s:\n' "$gid" "$gid"
            return 0
        fi
    done
    return 2
}
# shellcheck disable=SC2329
groupadd() { GROUPADDS+=("${2}:${3}"); }   # called as: groupadd --gid <gid> <name>
# shellcheck disable=SC2329
usermod() { USERMODS+=("${3}"); }          # called as: usermod --append --groups <name> arm

run_fn() {  # run setup_render_access in THIS shell; capture output to files.
    # (Command substitution would subshell the call and lose the shadow
    # functions' array mutations — capture via redirection instead.)
    setup_render_access >"$TMP/out" 2>"$TMP/err" || true
}
out() { cat "$TMP/out" 2>/dev/null || true; }
err() { cat "$TMP/err" 2>/dev/null || true; }

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT
_case=0
reset_state() {
    STAT_GIDS=(); GROUPADDS=(); USERMODS=(); GETENT_KNOWN=()
    unset RENDER_GID ARM_GPU_DEVICE 2>/dev/null || true
    _case=$((_case + 1))
    TMP="$TMPROOT/case-$_case"
    mkdir -p "$TMP"
    export ARM_RENDER_NODE_DIR="$TMP"
}

# 1. Explicit RENDER_GID wins; derivation is skipped entirely.
reset_state
touch "$TMP/renderD128"; STAT_GIDS[renderD128]=555   # would derive 555 if consulted
RENDER_GID=993 run_fn
check "explicit: log line" "yes" "$( [[ "$(out)" == *"render access: RENDER_GID=993 (explicit)"* ]] && echo yes || echo no )"
check "explicit: creates legacy render-host name" "993:render-host" "${GROUPADDS[0]:-}"
check "explicit: arm joined" "render-host" "${USERMODS[0]:-}"
check "explicit: derivation skipped" "1" "${#USERMODS[@]}"

# 2. Derivation: single node -> its gid joined, log line names it.
reset_state
touch "$TMP/renderD128"; STAT_GIDS[renderD128]=993
run_fn
check "derive: groupadd render-host-<gid>" "993:render-host-993" "${GROUPADDS[0]:-}"
check "derive: arm joined" "render-host-993" "${USERMODS[0]:-}"
check "derive: log line" "yes" "$( [[ "$(out)" == *"render access: derived gid(s) 993"* ]] && echo yes || echo no )"

# 3. Derivation: two nodes, two distinct gids -> both joined once each.
reset_state
touch "$TMP/renderD128" "$TMP/renderD129"
STAT_GIDS[renderD128]=993; STAT_GIDS[renderD129]=44
run_fn
check "two gids: both joined" "2" "${#USERMODS[@]}"

# 4. Derivation: two nodes, SAME gid -> joined once (dedup).
reset_state
touch "$TMP/renderD128" "$TMP/renderD129"
STAT_GIDS[renderD128]=993; STAT_GIDS[renderD129]=993
run_fn
check "dup gid: joined once" "1" "${#USERMODS[@]}"

# 5. gid 0 -> refused with warning, arm NOT added to root group.
reset_state
touch "$TMP/renderD128"; STAT_GIDS[renderD128]=0
run_fn
check "gid0: refused" "0" "${#USERMODS[@]}"
check "gid0: warning" "yes" "$( [[ "$(err)" == *"refusing to add arm to gid 0"* ]] && echo yes || echo no )"

# 6. No nodes, no ARM_GPU_DEVICE -> silent no-op (backend/ripper/ui/CPU path).
reset_state
run_fn
check "no nodes: no-op" "0" "${#USERMODS[@]}"
check "no nodes: silent" "" "$(out)$(err)"

# 7. No nodes but a render-node ARM_GPU_DEVICE assigned -> distinct FAILED line.
reset_state
ARM_GPU_DEVICE=/dev/dri/renderD128 run_fn
check "assigned-but-missing: FAILED line" "yes" "$( [[ "$(err)" == *"render access: FAILED"* ]] && echo yes || echo no )"

# 8. NVENC assignment (nvidia:// device) with no /dev/dri -> still silent.
reset_state
ARM_GPU_DEVICE="nvidia://0" run_fn
check "nvenc: silent no-op" "" "$(out)$(err)"

# 9. Derived gid already exists as an image group -> adopted, no groupadd.
reset_state
touch "$TMP/renderD128"; STAT_GIDS[renderD128]=44
GETENT_KNOWN=(44)
run_fn
check "adopt: no groupadd" "0" "${#GROUPADDS[@]}"
check "adopt: joined existing group" "grp44" "${USERMODS[0]:-}"

# 10. Unstatable node -> FAILED line, continues (no crash under set -e).
reset_state
touch "$TMP/renderD128"   # no STAT_GIDS entry -> shadow stat returns 1
run_fn
check "unstatable: FAILED line" "yes" "$( [[ "$(err)" == *"render access: FAILED"* ]] && echo yes || echo no )"
check "unstatable: no join" "0" "${#USERMODS[@]}"

exit "$fail"
