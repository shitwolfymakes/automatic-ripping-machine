#!/usr/bin/env bash
# Zero-infra suite: the release bundle has the expected files and carries the
# compose template unchanged.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="${HERE}/.."
ROOT="${DEPLOY}/.."

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

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

archive="$(bash "${DEPLOY}/build-bundle.sh" v3.9.9 "${TMP}/out")"
check "archive is named after the tag" "${TMP}/out/arm-installer-v3.9.9.tar.gz" "${archive}"
rc=0; (cd "${TMP}/out" && sha256sum -c "arm-installer-v3.9.9.tar.gz.sha256" >/dev/null 2>&1) || rc=$?
check "checksum file verifies the archive" "0" "$rc"

listing="$(tar -tzf "${archive}")"
for f in armctl.sh install.sh docker-compose.yml.example docker-compose.release.yml .env.example VERSION; do
    rc=0; grep -qx "./${f}" <<<"${listing}" || rc=$?
    check "bundle has ${f}" "0" "$rc"
done
# Every library and install module in the checkout must be in the bundle.
while IFS= read -r f; do
    rc=0; grep -qx "./${f}" <<<"${listing}" || rc=$?
    check "bundle has ${f}" "0" "$rc"
done < <(cd "${DEPLOY}" && find lib install -type f -name '*.sh' | sort)
rc=0; grep -qE '(^|/)(tests|build-bundle\.sh)' <<<"${listing}" || rc=$?
check "bundle leaves out tests and the bundler" "1" "$rc"
rc=0; grep -qE '(^/|(^|/)\.\.(/|$))' <<<"${listing}" || rc=$?
check "no absolute or parent paths in the archive" "1" "$rc"

mkdir -p "${TMP}/x"; tar -xzf "${archive}" -C "${TMP}/x"
rc=0; cmp -s "${ROOT}/docker-compose.yml.example" "${TMP}/x/docker-compose.yml.example" || rc=$?
check "compose template is byte-identical to the committed one" "0" "$rc"
rc=0; cmp -s "${ROOT}/.env.example" "${TMP}/x/.env.example" || rc=$?
check ".env.example is byte-identical to the committed one" "0" "$rc"
check "VERSION holds the tag" "v3.9.9" "$(cat "${TMP}/x/VERSION")"
check "armctl.sh is executable" "yes" "$( [[ -x "${TMP}/x/armctl.sh" ]] && echo yes || echo no )"

bash "${DEPLOY}/build-bundle.sh" v3.9.9 "${TMP}/out2" >/dev/null
check "the bundle is reproducible" \
    "$(cut -d' ' -f1 "${TMP}/out/arm-installer-v3.9.9.tar.gz.sha256")" \
    "$(cut -d' ' -f1 "${TMP}/out2/arm-installer-v3.9.9.tar.gz.sha256")"

rc=0; bash "${DEPLOY}/build-bundle.sh" >/dev/null 2>&1 || rc=$?
check "a missing tag is a usage error" "2" "$rc"

exit "$fail"
