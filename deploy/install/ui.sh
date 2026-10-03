#!/usr/bin/env bash
# deploy/install/ui.sh: production output style, prompts and consent.
# Sourced by deploy/armctl.sh; needs deploy/lib/common.sh loaded first.

# Output vocabulary: plain indented detail lines; marks only for verification
# results and warnings. Everything else is plain.
log()      { printf '  %s\n' "$*"; }
okline()   { printf '  ✓ %s\n' "$*"; }
failline() { printf '  ✗ %s\n' "$*"; }
warnline() { printf '  ! %s\n' "$*"; }
warn()     { printf 'WARN: %s\n' "$*" >&2; }
err()      { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

_RULE="────────────────────────────────────────────────────────────────────────"
section() {
    local n="$1" total="$2" title="$3" head
    head="── [${n}/${total}] ${title} "
    printf '\n%s%s\n' "$head" "${_RULE:0:$(( ${#_RULE} - ${#head} > 0 ? ${#_RULE} - ${#head} : 4 ))}"
}
# step <title>: the next numbered section of `armctl install`.
STEP=0
STEP_TOTAL=7
step() {
    STEP=$(( STEP + 1 ))
    section "${STEP}" "${STEP_TOTAL}" "$1"
}
fence_open() {
    local label="$1" head
    head="──── ${label} "
    printf '\n%s%s\n' "$head" "${_RULE:0:$(( ${#_RULE} - ${#head} > 0 ? ${#_RULE} - ${#head} : 4 ))}"
}
fence_close() { printf '%s\n\n' "$_RULE"; }

# vercmp_ge <a> <b>: true when version a >= version b.
vercmp_ge() {
    local lower
    lower="$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n 1)"
    [[ "$lower" = "$2" ]]
}

# confirm <prompt>: yes/no question. Without a terminal it reads one line from
# stdin (so tests and pipes can answer) and treats end-of-input as "no".
confirm() {
    local prompt="$1" reply
    if [[ ! -t 0 ]]; then
        read -r reply || reply="n"
    else
        read -rp "$prompt [y/N] " reply
    fi
    [[ "$reply" =~ ^[yY]([eE][sS])?$ ]]
}

# prompt_valid <prompt> <validator> <shape-hint>: loop until valid; echo value.
prompt_valid() {
    local prompt="$1" validator="$2" hint="$3" value
    while true; do
        read -rp "${prompt} (${hint}): " value
        if "$validator" "$value"; then
            printf '%s' "$value"
            return 0
        fi
        printf '    ! expected shape: %s   (you entered: %s)\n' "$hint" "$value" >&2
    done
}

# Host changes (Docker, NVIDIA toolkit, udev rule, a PATH link that needs sudo)
# go through consent. ARMCTL_ASSUME is `yes` (--yes), `no` (--no-host-changes)
# or `ask`. With `ask` and no terminal the step is declined, never left hanging.
# Every declined step is recorded in SKIPPED for the end-of-install summary.
ARMCTL_ASSUME="ask"
SKIPPED=()
consent() {  # consent <what, for the summary> <prompt>
    local what="$1" prompt="$2"
    case "${ARMCTL_ASSUME}" in
        yes) return 0 ;;
        no)  SKIPPED+=("${what} (declined by --no-host-changes)"); return 1 ;;
    esac
    if [[ ! -t 0 ]]; then
        SKIPPED+=("${what} (no terminal to ask on)")
        return 1
    fi
    if confirm "${prompt}"; then
        return 0
    fi
    SKIPPED+=("${what} (declined)")
    return 1
}
