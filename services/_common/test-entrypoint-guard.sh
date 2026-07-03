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
# shellcheck disable=SC2034  # used by the sourced entrypoint
WRITE_CHECK_ATTEMPTS=2        # small so retry-then-fail is fast
# shellcheck disable=SC2034  # used by the sourced entrypoint
WRITE_CHECK_DELAY=0           # no sleeping in tests
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

if [[ "${fail}" -eq 0 ]]; then
    echo "PASS - all require_writable guard cases"
else
    echo "FAILED - see above" >&2
fi
exit "${fail}"
