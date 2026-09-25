#!/usr/bin/env bash
# Plain-bash unit test for the entrypoint's require_writable() guard.
# No bats — the repo gates shell with shellcheck only. Runs with no Docker,
# no root: it sources the production entrypoint (via ARM_ENTRYPOINT_SOURCE_ONLY)
# and drives require_writable against temp dirs, substituting `test -w` for the
# production `gosu arm test -w` by pre-declaring the WRITE_TEST array.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTRYPOINT="${HERE}/docker-entrypoint.sh"

# --- override the production write test + speed up retries, THEN source ---
# The three vars below are consumed by the sourced entrypoint, not by this
# script, so the linter cannot see their use across the source boundary.
# shellcheck disable=SC2034  # used by the sourced entrypoint
WRITE_TEST=(test -w)          # declare -p guard in the entrypoint respects this
# The temp dirs below are not real mountpoints, so stub MOUNT_TEST to treat
# every present dir as a mount (`true`); case 5 overrides it to exercise the
# not-a-mountpoint skip explicitly.
# shellcheck disable=SC2034  # used by the sourced entrypoint
MOUNT_TEST=(true)
# shellcheck disable=SC2034  # used by the sourced entrypoint
WRITE_CHECK_ATTEMPTS=2        # small so retry-then-fail is fast
# shellcheck disable=SC2034  # used by the sourced entrypoint
WRITE_CHECK_DELAY=0           # no sleeping in tests
# READ_TEST mirrors WRITE_TEST for the read-only-mount path: substitute plain
# `test -r` for the production `gosu arm test -r`. RO_TEST is stubbed per-case
# below (production reads /proc/self/mounts; these temp dirs are never
# actually read-only mounts, so each case overrides RO_TEST directly).
# shellcheck disable=SC2034  # used by the sourced entrypoint
READ_TEST=(test -r)
export ARM_ENTRYPOINT_SOURCE_ONLY=1
# shellcheck disable=SC1090
source "${ENTRYPOINT}"

fail=0
check() {  # check <label> <expected-rc> <actual-rc>
    local label="$1" want="$2" got="$3"
    if [[ "${want}" == "${got}" ]]; then
        echo "ok   - ${label}"
    else
        echo "FAIL - ${label}: expected rc=${want}, got rc=${got}" >&2
        fail=1
    fi
}

# 1. Writable dir -> pass (rc 0), no stderr.
wd="$(mktemp -d)"
rc=0; err="$(require_writable "${wd}" 2>&1 1>/dev/null)" || rc=$?
check "writable dir returns 0" 0 "${rc}"
[[ -z "${err}" ]] || { echo "FAIL - writable dir emitted stderr: ${err}" >&2; fail=1; }
rmdir "${wd}"

# 2. Unwritable dir -> rc 1 + FATAL diagnostic naming dir + PUID:PGID.
ud="$(mktemp -d)"; chmod 000 "${ud}"
rc=0; err="$(require_writable "${ud}" 2>&1 1>/dev/null)" || rc=$?
check "unwritable dir returns 1" 1 "${rc}"
case "${err}" in
    *FATAL*"${ud}"*"${PUID}:${PGID}"*) echo "ok   - diagnostic names dir + PUID:PGID" ;;
    *) echo "FAIL - diagnostic missing FATAL/dir/PUID:PGID: ${err}" >&2; fail=1 ;;
esac
chmod 755 "${ud}"; rmdir "${ud}"

# 3. Nonexistent dir -> skip (rc 0), no stderr.
rc=0; err="$(require_writable /no/such/dir/at/all 2>&1 1>/dev/null)" || rc=$?
check "nonexistent dir returns 0 (skip)" 0 "${rc}"
[[ -z "${err}" ]] || { echo "FAIL - nonexistent dir emitted stderr: ${err}" >&2; fail=1; }

# 4. Retry-then-fail terminates: an always-unwritable dir with ATTEMPTS=2
#    retries then returns 1 (already exercised by case 2 with ATTEMPTS=2, but
#    assert the loop actually ran >1 attempt by counting the "waiting" lines).
ud2="$(mktemp -d)"; chmod 000 "${ud2}"
rc=0; err="$(require_writable "${ud2}" 2>&1 1>/dev/null)" || rc=$?
waits="$(grep -c 'waiting for' <<<"${err}" || true)"
check "retry-then-fail returns 1" 1 "${rc}"
if [[ "${waits}" -ge 1 ]]; then
    echo "ok   - retried before failing (${waits} wait line(s))"
else
    echo "FAIL - expected >=1 retry wait line, got ${waits}" >&2; fail=1
fi
chmod 755 "${ud2}"; rmdir "${ud2}"

# 5. Present but NOT a mountpoint -> skip (rc 0), no stderr, even when unwritable.
#    Guards the ripper's incidental root-owned /media (never mounted) from
#    tripping the gate. Override MOUNT_TEST to report "not a mount" (rc 1).
nm="$(mktemp -d)"; chmod 000 "${nm}"
rc=0
err="$(
    # shellcheck disable=SC2034  # consumed by require_writable in the sourced entrypoint
    MOUNT_TEST=(false)
    require_writable "${nm}" 2>&1 1>/dev/null
)" || rc=$?
check "non-mountpoint dir returns 0 (skip)" 0 "${rc}"
[[ -z "${err}" ]] || { echo "FAIL - non-mountpoint dir emitted stderr: ${err}" >&2; fail=1; }
chmod 755 "${nm}"; rmdir "${nm}"

# 6. RO mount, dir readable -> returns 0 (no FATAL). Override RO_TEST to
#    report "this dir is a read-only mount" (rc 0).
rod="$(mktemp -d)"
rc=0
err="$(
    # shellcheck disable=SC2034  # consumed by require_writable in the sourced entrypoint
    RO_TEST=(true)
    require_writable "${rod}" 2>&1 1>/dev/null
)" || rc=$?
check "RO mount, readable dir returns 0" 0 "${rc}"
[[ -z "${err}" ]] || { echo "FAIL - RO readable dir emitted stderr: ${err}" >&2; fail=1; }
rmdir "${rod}"

# 7. RO mount, dir NOT readable -> rc 1 + read-only FATAL text. chmod 000
#    only blocks reads for non-root; running as root would read anything, so
#    skip with a note rather than produce a false pass/fail.
if [[ "$(id -u)" -eq 0 ]]; then
    echo "skip - RO mount, unreadable dir (running as root; chmod 000 is not enforced)"
else
    rou="$(mktemp -d)"; chmod 000 "${rou}"
    rc=0
    err="$(
        # shellcheck disable=SC2034  # consumed by require_writable in the sourced entrypoint
        RO_TEST=(true)
        require_writable "${rou}" 2>&1 1>/dev/null
    )" || rc=$?
    check "RO mount, unreadable dir returns 1" 1 "${rc}"
    case "${err}" in
        *FATAL*"not readable by arm (read-only mount)"*) echo "ok   - diagnostic is the read-only FATAL text" ;;
        *) echo "FAIL - diagnostic missing read-only FATAL text: ${err}" >&2; fail=1 ;;
    esac
    chmod 755 "${rou}"; rmdir "${rou}"
fi

# 8. RW mount, dir not writable -> still returns 1 with the ORIGINAL writable
#    FATAL text (regression guard: RO_TEST=(false) must take the write path).
rwu="$(mktemp -d)"; chmod 000 "${rwu}"
rc=0
err="$(
    # shellcheck disable=SC2034  # consumed by require_writable in the sourced entrypoint
    RO_TEST=(false)
    require_writable "${rwu}" 2>&1 1>/dev/null
)" || rc=$?
check "RW mount, unwritable dir returns 1" 1 "${rc}"
case "${err}" in
    *"FATAL: ${rwu} is not writable by arm"*) echo "ok   - diagnostic is the original writable FATAL text" ;;
    *) echo "FAIL - diagnostic missing original writable FATAL text: ${err}" >&2; fail=1 ;;
esac
chmod 755 "${rwu}"; rmdir "${rwu}"

if [[ "${fail}" -eq 0 ]]; then
    echo "PASS - all require_writable guard cases"
else
    echo "FAILED - see above" >&2
fi
exit "${fail}"
