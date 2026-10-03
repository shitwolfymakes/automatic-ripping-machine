#!/usr/bin/env bash
# shellcheck disable=SC2317,SC2329,SC2034,SC2030,SC2031
# Zero-infra suite for the installer bootstrap (root install.sh): no docker,
# no root, no network. Sources install.sh through ARM_INSTALL_SOURCE_ONLY.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="${HERE}/.."
ROOT="$(cd "${DEPLOY}/.." && pwd)"

export ARM_INSTALL_SOURCE_ONLY=1
# shellcheck disable=SC1091
source "${ROOT}/install.sh"

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
has()   { check "$1" "yes" "$( [[ "$3" == *"$2"* ]] && echo yes || echo no )"; }
lacks() { check "$1" "no"  "$( [[ "$3" == *"$2"* ]] && echo yes || echo no )"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# --- where the arm folder goes (Review Focus 2) -----------------------------------
check "prefix names the parent folder" "/srv/arm" "$(bootstrap_arm_dir /srv)"
check "a prefix that already ends in arm is the arm folder itself" "/srv/arm" "$(bootstrap_arm_dir /srv/arm)"
check "a trailing slash changes nothing" "/srv/arm" "$(bootstrap_arm_dir /srv/arm/)"

# --- an existing folder that is not ours (Review Focus 3) -------------------------
rc=0; (bootstrap_check_target "${TMP}/absent/arm") >/dev/null 2>&1 || rc=$?
check "a folder that does not exist yet is fine" "0" "$rc"
mkdir -p "${TMP}/empty/arm"
rc=0; (bootstrap_check_target "${TMP}/empty/arm") >/dev/null 2>&1 || rc=$?
check "an empty folder is fine" "0" "$rc"
mkdir -p "${TMP}/ours/arm/.armctl" "${TMP}/ours/arm/media"
rc=0; (bootstrap_check_target "${TMP}/ours/arm") >/dev/null 2>&1 || rc=$?
check "an existing armctl install is fine (re-run)" "0" "$rc"
mkdir -p "${TMP}/v2/arm/media" "${TMP}/v2/arm/config"
rc=0; out="$( (bootstrap_check_target "${TMP}/v2/arm") 2>&1)" || rc=$?
check "an ARM v2 home is refused" "1" "$rc"
has "the refusal says it was not created by this installer" "was not created by this installer" "$out"
has "the refusal says how to choose another place" "--prefix" "$out"
mkdir -p "${TMP}/oldv3/arm"; echo x > "${TMP}/oldv3/arm/docker-compose.yml"
rc=0; (bootstrap_check_target "${TMP}/oldv3/arm") >/dev/null 2>&1 || rc=$?
check "the old v3 installer's layout is refused" "1" "$rc"
check "a refused folder is left untouched" "x" "$(cat "${TMP}/oldv3/arm/docker-compose.yml")"
mkdir -p "${TMP}/file"; echo x > "${TMP}/file/arm"
rc=0; (bootstrap_check_target "${TMP}/file/arm") >/dev/null 2>&1 || rc=$?
check "a file named arm is refused" "1" "$rc"

# --- picking the release ----------------------------------------------------------
tagfor() {  # tagfor <curl stub body>
    ( eval "curl() { $1; }"; bootstrap_resolve_tag )
}
check "latest stable v3 tag is used" "v3.1.0" "$(tagfor 'echo "{ \"tag_name\": \"v3.1.0\", \"name\": \"x\" }"' 2>/dev/null)"
rc=0; out="$(tagfor 'echo "{ \"tag_name\": \"2.21.5\" }"' 2>&1)" || rc=$?
check "a v2 release is refused" "1" "$rc"
has "the v2 refusal explains" "not a v3 release" "$out"
rc=0; out="$(tagfor 'return 22' 2>&1)" || rc=$?
check "an unreachable GitHub is an error" "1" "$rc"
has "the error says what to try" "--version" "$out"

# --- fetching and verifying a bundle ----------------------------------------------
archive="$(bash "${DEPLOY}/build-bundle.sh" v3.9.9 "${TMP}/out")"
( bootstrap_fetch_bundle v3.9.9 "${TMP}/rel/v3.9.9" "${archive}" ) >/dev/null
check "a good bundle is unpacked" "yes" "$( [[ -x "${TMP}/rel/v3.9.9/armctl.sh" && -f "${TMP}/rel/v3.9.9/lib/common.sh" ]] && echo yes || echo no )"
check "no partial folder is left behind" "no" "$( [[ -e "${TMP}/rel/v3.9.9.partial" ]] && echo yes || echo no )"

# A tag becomes a folder name; one that could name another folder is refused
# before anything is removed or written.
mkdir -p "${TMP}/trav/a/b"; echo keep > "${TMP}/trav/marker"
for badtag in '../..' 'a/b' '.hidden' ''; do
    rc=0; out="$( (bootstrap_fetch_bundle "${badtag}" "${TMP}/trav/a/b/${badtag}" "${archive}") 2>&1)" || rc=$?
    check "tag '${badtag}' is refused" "1" "$rc"
    has "tag '${badtag}': the refusal says nothing was changed" "Nothing was changed" "${out}"
    check "tag '${badtag}': nothing was removed" "keep" "$(cat "${TMP}/trav/marker" 2>/dev/null)"
done
for oktag in drill v3.1.0-rc1; do
    rc=0; ( bootstrap_fetch_bundle "${oktag}" "${TMP}/rel/${oktag}" "${archive}" ) >/dev/null 2>&1 || rc=$?
    check "tag '${oktag}' is accepted" "0" "$rc"
    check "tag '${oktag}' is unpacked" "yes" "$( [[ -x "${TMP}/rel/${oktag}/armctl.sh" ]] && echo yes || echo no )"
done

mkdir -p "${TMP}/bad"; cp "${archive}" "${TMP}/bad/b.tar.gz"
echo "0000000000000000000000000000000000000000000000000000000000000000  b.tar.gz" > "${TMP}/bad/b.tar.gz.sha256"
rc=0; out="$( (bootstrap_fetch_bundle v3.9.9 "${TMP}/rel/tampered" "${TMP}/bad/b.tar.gz") 2>&1)" || rc=$?
check "a checksum mismatch is refused" "1" "$rc"
has "the mismatch is named" "checksum" "$out"
check "nothing is unpacked from a bad bundle" "no" "$( [[ -e "${TMP}/rel/tampered" ]] && echo yes || echo no )"

mkdir -p "${TMP}/evil-src"; echo pwned > "${TMP}/evil-src/evil"
tar -P -C "${TMP}/evil-src" --transform 's|^evil$|../evil|' -czf "${TMP}/bad/e.tar.gz" evil 2>/dev/null
(cd "${TMP}/bad" && sha256sum e.tar.gz > e.tar.gz.sha256)
rc=0; out="$( (bootstrap_fetch_bundle v3.9.9 "${TMP}/rel/escape" "${TMP}/bad/e.tar.gz") 2>&1)" || rc=$?
check "an archive that escapes its folder is refused" "1" "$rc"
check "the escaping file was not written" "no" "$( [[ -e "${TMP}/rel/evil" ]] && echo yes || echo no )"

rc=0; out="$( (curl() { return 22; }; bootstrap_fetch_bundle v3.9.9 "${TMP}/rel/offline") 2>&1)" || rc=$?
check "a failed download is an error" "1" "$rc"
check "a failed download leaves no folder" "no" "$( [[ -e "${TMP}/rel/offline" ]] && echo yes || echo no )"

# An existing release folder is only replaced once the new one is complete.
mkdir -p "${TMP}/rel/keep"; echo old > "${TMP}/rel/keep/marker"
( bootstrap_fetch_bundle v3.9.9 "${TMP}/rel/keep" "${TMP}/bad/b.tar.gz" ) >/dev/null 2>&1 || true
check "a failed fetch leaves an existing release as it was" "old" "$(cat "${TMP}/rel/keep/marker")"

# --- the whole bootstrap, with the handover recorded ------------------------------
# boot <case name> [install.sh args...]
boot() {
    (
        HOME="${TMP}/$1/home"; mkdir -p "${HOME}"; shift
        bootstrap_uid() { echo 1000; }
        bootstrap_handover() { echo "HANDOVER ARM_DIR=${ARM_DIR} ARGS=$*"; }
        bootstrap_main "$@"
    )
}
out="$(boot default --bundle "${archive}" --version v3.9.9 --profile ripper-only --yes)"
arm="${TMP}/default/home/arm"
has "default location is ~/arm" "HANDOVER ARM_DIR=${arm} " "$out"
has "the launcher is what gets run, with install first" "ARGS=${arm}/armctl install " "$out"
has "flags the bootstrap does not own are passed through" "--profile ripper-only --yes" "$out"
lacks "the bootstrap's own flags are not passed through" "--bundle" "$out"
check "the release is unpacked under .armctl" "yes" "$( [[ -f "${arm}/.armctl/releases/v3.9.9/armctl.sh" ]] && echo yes || echo no )"
check "current points at the release" "releases/v3.9.9" "$(readlink "${arm}/.armctl/current")"
check "the launcher is executable" "yes" "$( [[ -x "${arm}/armctl" ]] && echo yes || echo no )"

out="$(boot prefixed --prefix "${TMP}/prefixed/srv" --bundle "${archive}" --version v3.9.9)"
has "--prefix names the parent" "ARM_DIR=${TMP}/prefixed/srv/arm " "$out"
out="$(boot repo --bundle "${archive}" --version v3.9.9 --release-repo me/fork)"
has "--release-repo is also passed on, for upgrades" "--release-repo me/fork" "$out"

# A user named `arm` has HOME=/home/arm; the default must still be ~/arm.
out="$( (HOME="${TMP}/userarm/arm"; mkdir -p "${HOME}"; echo dotfile > "${HOME}/.profile"
         bootstrap_uid() { echo 1000; }; bootstrap_handover() { echo "HANDOVER ARM_DIR=${ARM_DIR}"; }
         bootstrap_main --bundle "${archive}" --version v3.9.9) )"
has "a home folder named arm does not become the install folder" "ARM_DIR=${TMP}/userarm/arm/arm" "$out"

rc=0; out="$( (bootstrap_uid() { echo 0; }; bootstrap_main --bundle "${archive}" --version v3.9.9) 2>&1)" || rc=$?
check "root is refused" "1" "$rc"
has "the root refusal explains" "as root" "$out"
rc=0; out="$( (bootstrap_uid() { echo 1000; }; HOME="${TMP}/nover"; mkdir -p "${HOME}"; cd "${TMP}"; bootstrap_main --bundle "${archive}") 2>&1)" || rc=$?
check "--bundle without --version is refused" "1" "$rc"
has "the refusal says --version is needed" "--bundle needs --version" "$out"
mkdir -p "${TMP}/v2home/home/arm/media"
rc=0; out="$( (HOME="${TMP}/v2home/home"; bootstrap_uid() { echo 1000; }; bootstrap_handover() { echo HANDOVER; }
              bootstrap_main --bundle "${archive}" --version v3.9.9) 2>&1)" || rc=$?
check "a foreign arm folder stops the bootstrap" "1" "$rc"
lacks "nothing is handed over" "HANDOVER" "$out"
check "nothing was added to the foreign folder" "media" "$(cd "${TMP}/v2home/home/arm" && echo *)"

# --- a failed bootstrap leaves the target as it was -------------------------------
# failboot <case> : run bootstrap_main with a tampered bundle (checksum mismatch), report "rc=<n> <output>"
failboot() {
    local rc=0 o
    o="$( (HOME="${TMP}/$1/home"; bootstrap_uid() { echo 1000; }; bootstrap_handover() { echo HANDOVER; }
           bootstrap_main --bundle "${TMP}/bad/b.tar.gz" --version v3.9.9) 2>&1)" || rc=$?
    echo "rc=${rc} ${o}"
}
mkdir -p "${TMP}/ff/home"
out="$(failboot ff)"
has "a failed fresh bootstrap exits 1" "rc=1 " "$out"
lacks "a failed fresh bootstrap hands nothing over" "HANDOVER" "$out"
check "a failed fresh bootstrap leaves no arm folder" "no" "$( [[ -e "${TMP}/ff/home/arm" ]] && echo yes || echo no )"
mkdir -p "${TMP}/fe/home/arm"
out="$(failboot fe)"
has "a failed bootstrap into an empty folder exits 1" "rc=1 " "$out"
lacks "that hands nothing over" "HANDOVER" "$out"
check "the empty arm folder is still empty" "" "$(ls -A "${TMP}/fe/home/arm")"
mkdir -p "${TMP}/fx/home/arm/.armctl/releases/v1"; echo keep > "${TMP}/fx/home/arm/.armctl/marker"
ln -s releases/v1 "${TMP}/fx/home/arm/.armctl/current"
out="$(failboot fx)"
has "a failed bootstrap over an install exits 1" "rc=1 " "$out"
lacks "that hands nothing over" "HANDOVER" "$out"
check "the existing install's marker is intact" "keep" "$(cat "${TMP}/fx/home/arm/.armctl/marker")"
check "current is unchanged" "releases/v1" "$(readlink "${TMP}/fx/home/arm/.armctl/current")"
check "no release or partial folder was added" "v1" "$(ls "${TMP}/fx/home/arm/.armctl/releases")"

# --- the generated launcher -------------------------------------------------------
L="${TMP}/launch/arm"; mkdir -p "${L}/.armctl/releases/v1"
# shellcheck disable=SC2016 # the fake armctl.sh must expand these itself, at run time
printf '#!/usr/bin/env bash\necho "ARM_DIR=${ARM_DIR} ARGS=$*"\n' > "${L}/.armctl/releases/v1/armctl.sh"
chmod 755 "${L}/.armctl/releases/v1/armctl.sh"
ln -s releases/v1 "${L}/.armctl/current"
bootstrap_write_launcher "${L}"
check "the launcher runs the current release with ARM_DIR set" "ARM_DIR=${L} ARGS=up --force" "$("${L}/armctl" up --force)"
mkdir -p "${TMP}/bin"; ln -s "${L}/armctl" "${TMP}/bin/armctl"
check "the launcher works through a PATH link" "ARM_DIR=${L} ARGS=down" "$(cd / && "${TMP}/bin/armctl" down)"

# --- usage and the install drill ----------------------------------------------------
usage="$(bootstrap_usage)"
has "usage shows how to pass options through the pipe" "| bash -s -- --version <tag>" "${usage}"
has "usage shows --prefix through the pipe" "| bash -s -- --prefix /srv --version <tag>" "${usage}"
# The drill runs the bootstrap from a terminal, which the bootstrap re-attaches:
# every question must be answered by a flag, or the drill stops at a prompt.
drill="$(cat "${ROOT}/devtools/install-drill.sh")"
for flag in --profile --raw-path --media-path --no-host-changes; do
    has "the install drill answers ${flag} by flag" "${flag} " "${drill}"
done

exit "$fail"
