#!/usr/bin/env bash
# deploy/lib/common.sh: helpers shared by devtools/setup-dev.sh (dev) and
# deploy/armctl.sh (production). Sourced, never executed.
#
# Callers set, before calling anything here:
#   ARM_COMPOSE_CWD   folder `docker compose` runs from
#   ARM_COMPOSE_CMD   array: the compose command plus any fixed flags
#   ENV_FILE          path of the stack's .env

# Output helpers. These defaults print devtools/setup-dev.sh's style, byte for
# byte what it printed before the helpers existed. deploy/armctl.sh redefines
# all four after sourcing this file.
arm_say()  { echo "==> $*"; }
# One continuation line; the caller passes it with its indentation.
arm_sub()  { printf '%s\n' "$1"; }
arm_warn() { echo "WARNING: $*" >&2; }
# Prints only. The caller decides whether to exit.
arm_err()  { echo "ERROR: $*" >&2; }

require() {
    local bin="$1"
    local hint="$2"
    if ! command -v "${bin}" >/dev/null 2>&1; then
        arm_err "'${bin}' not found. ${hint}"
        exit 1
    fi
}

compose() {
    (cd "${ARM_COMPOSE_CWD}" && "${ARM_COMPOSE_CMD[@]}" "$@")
}

require_compose() {
    if ! docker compose version >/dev/null 2>&1; then
        arm_err "'docker compose' (v2 plugin) not available"
        exit 1
    fi
}

# Print KEY's value from ENV_FILE (last uncommented assignment, one layer of
# surrounding quotes stripped), or nothing if it is absent.
env_file_value() {
    local key="$1" val
    [[ -f "${ENV_FILE}" ]] || return 0
    val="$(sed -nE "s/^${key}=(.*)$/\\1/p" "${ENV_FILE}" | tail -n1)"
    val="${val%\"}"; val="${val#\"}"
    val="${val%\'}"; val="${val#\'}"
    printf '%s' "${val}"
}

# Set KEY=VALUE in a .env file (default: ENV_FILE). Delete-then-append rather
# than `sed s|...|value|`: the value may be free text (a URL, a path), and a
# `&` or `|` in it would corrupt a sed replacement. The file is rewritten in
# place so its mode is kept.
env_set() {
    local key="$1" value="$2" file="${3:-${ENV_FILE}}" rest
    if grep -q "^${key}=" "${file}" 2>/dev/null; then
        rest="$(grep -v "^${key}=" "${file}" || true)"
        if [[ -n "${rest}" ]]; then printf '%s\n' "${rest}" > "${file}"; else : > "${file}"; fi
    fi
    printf '%s=%s\n' "${key}" "${value}" >> "${file}"
}

env_unset() {
    local key="$1" file="${2:-${ENV_FILE}}" rest
    grep -q "^${key}=" "${file}" 2>/dev/null || return 0
    rest="$(grep -v "^${key}=" "${file}" || true)"
    if [[ -n "${rest}" ]]; then printf '%s\n' "${rest}" > "${file}"; else : > "${file}"; fi
}

# Run a command silently; replay its captured output only when it fails.
run_quiet() {
    local out rc=0
    out="$("$@" 2>&1)" || rc=$?
    if (( rc != 0 )); then
        printf '%s\n' "$out"
    fi
    return "$rc"
}
