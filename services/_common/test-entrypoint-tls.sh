#!/usr/bin/env bash
# Plain-bash unit test for the entrypoint's private_tls_key(). No Docker, no
# root: it sources the production entrypoint (ARM_ENTRYPOINT_SOURCE_ONLY) and
# drives private_tls_key against temp files, substituting a stub for the
# production `gosu arm test -r` (READ_TEST) and the current user for the copy's
# owner (TLS_KEY_OWNER), since the test cannot chown to `arm`.
#
# READ_TEST, TLS_KEY_OWNER, TLS_KEY_COPY_DIR and TLS_KEY_PATH are read by the
# sourced function, which the linter cannot see across the source boundary.
# shellcheck disable=SC2034
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTRYPOINT="${HERE}/docker-entrypoint.sh"

READ_TEST=(test -r)
TLS_KEY_OWNER="$(id -u):$(id -g)"
export ARM_ENTRYPOINT_SOURCE_ONLY=1
# shellcheck disable=SC1090
source "${ENTRYPOINT}"

fail=0
expect() {  # expect <label> <command...>: the command must succeed
    local label="$1"; shift
    if "$@"; then
        echo "ok   - ${label}"
    else
        echo "FAIL - ${label}" >&2
        fail=1
    fi
}
mode_of() { stat -c %a "$1"; }

work="$(mktemp -d)"
trap 'chmod -R u+rwx "${work}" 2>/dev/null || true; rm -rf "${work}"' EXIT
key="${work}/tls.key"
printf 'PRIVATE KEY BYTES\n' > "${key}"
chmod 0440 "${key}"

# 1. A key the arm user can read is used as mounted: no copy, nothing said.
TLS_KEY_PATH="${key}"; TLS_KEY_COPY_DIR="${work}/copy1"
private_tls_key 2>"${work}/err1"
expect "readable key: path unchanged" test "${TLS_KEY_PATH}" = "${key}"
expect "readable key: no copy made" test ! -e "${work}/copy1"
expect "readable key: silent" test ! -s "${work}/err1"

# 2. A key the arm user cannot read (its group is not PGID): a private copy,
#    owned by the arm user, 0400 inside a 0700 dir, and TLS_KEY_PATH points at it.
READ_TEST=(false)
TLS_KEY_PATH="${key}"; TLS_KEY_COPY_DIR="${work}/copy2"
private_tls_key 2>"${work}/err2"
copy="${work}/copy2/tls.key"
expect "unreadable key: TLS_KEY_PATH points at the copy" test "${TLS_KEY_PATH}" = "${copy}"
expect "unreadable key: the copy has the same bytes" cmp -s "${key}" "${copy}"
expect "unreadable key: the copy is 0400" test "$(mode_of "${copy}")" = 400
expect "unreadable key: its dir is 0700" test "$(mode_of "${work}/copy2")" = 700
expect "unreadable key: says why, naming the key and PUID:PGID" \
    grep -q "${key} is not readable by PUID:PGID=" "${work}/err2"

# 3. No TLS_KEY_PATH (the ripper and transcoder): nothing to do.
unset TLS_KEY_PATH
TLS_KEY_COPY_DIR="${work}/copy3"
private_tls_key 2>/dev/null
expect "no TLS_KEY_PATH: still unset" test -z "${TLS_KEY_PATH:-}"
expect "no TLS_KEY_PATH: no copy made" test ! -e "${work}/copy3"

# 4. The copy cannot be made: keep the mounted path (the service then reports
#    the unreadable key itself) and warn.
mkdir "${work}/locked"; chmod 0500 "${work}/locked"
TLS_KEY_PATH="${key}"; TLS_KEY_COPY_DIR="${work}/locked/copy"
private_tls_key 2>"${work}/err4"
expect "failed copy: mounted path kept" test "${TLS_KEY_PATH}" = "${key}"
expect "failed copy: warns" grep -q "^WARN: TLS key ${key}" "${work}/err4"

exit "${fail}"
