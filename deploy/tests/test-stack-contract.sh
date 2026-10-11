#!/usr/bin/env bash
# shellcheck disable=SC2317,SC2329,SC2034
# The production stack contract: the committed compose template layered with
# the release overlay and a host overlay. Text checks always run; the
# `docker compose config` checks run when docker is present.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="${HERE}/.."
ROOT="${DEPLOY}/.."
TEMPLATE="${ROOT}/docker-compose.yml.example"
OVERLAY="${DEPLOY}/docker-compose.release.yml"

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
# image_of <service> <compose yaml>: the service's image, or nothing.
image_of() {
    awk -v s="  $1:" '$0 == s {f=1; next} f && /^  [a-z]/ {exit} f && /^    image:/ {sub(/^    image: */, ""); print; exit}' <<<"$2"
}

# --- text: every service the template only builds gets a release image -----------
# This is the one thing a new built-from-source service needs: a line in the
# release overlay. Everything else in the template reaches production as is.
built_only="$(awk '
    /^  [a-z][a-z0-9-]*:$/ { svc=$1; sub(":", "", svc); order[++n]=svc; next }
    /^    image:/ { img[svc]=1 }
    /^    build:/ { bld[svc]=1 }
    END { for (i = 1; i <= n; i++) if (bld[order[i]] && !img[order[i]]) print order[i] }
' "${TEMPLATE}")"
check "the template's build-only services are the three we expect" \
    "arm-backend arm-data-init arm-ui" "$(tr '\n' ' ' <<<"${built_only}" | sed 's/ $//')"
overlay_text="$(cat "${OVERLAY}")"
while IFS= read -r svc; do
    [[ -n "${svc}" ]] || continue
    got="$(image_of "${svc}" "${overlay_text}")"
    # shellcheck disable=SC2016  # the literal ${...} text is what we look for
    check "release overlay names an image for ${svc}" "yes" "$( [[ "${got}" == *'${ARM_IMAGE_PREFIX'*'${ARM_IMAGE_TAG'* ]] && echo yes || echo no )"
done <<<"${built_only}"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo "skip - docker compose not available; contract checked by text only"
    exit "$fail"
fi

# --- docker compose config: the layered stack as armctl runs it -------------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
archive="$(bash "${DEPLOY}/build-bundle.sh" v3.9.9 "${TMP}/out")"
ARM_DIR="${TMP}/home/arm"
REL="${ARM_DIR}/.armctl/releases/v3.9.9"
mkdir -p "${REL}"; tar -xzf "${archive}" -C "${REL}"

export ARMCTL_SOURCE_ONLY=1
# shellcheck disable=SC1091
source "${REL}/armctl.sh"
armctl_settings

# A storage folder with a space in its name (Review Focus 1).
PROFILE=full; RIPPER_ONLY=0
RAW_PATH="${TMP}/My Passport/rips"; MEDIA_PATH="${TMP}/nas/media"
mkdir -p "${RAW_PATH}" "${MEDIA_PATH}"
ARM_IMAGE_TAG_DEFAULT="v3.9.9"; IMAGE_PREFIX_ARG=""
detect_gpus() { printf '[]'; }
detect_render_gid() { :; }
write_env >/dev/null
write_host_overlay

rc=0; cfg="$(compose config 2>"${TMP}/config.err")" || rc=$?
check "layered config is valid" "0" "$rc"
if [[ "$rc" -ne 0 ]]; then cat "${TMP}/config.err" >&2; exit 1; fi

check "project name is armv3" "armv3" "$(sed -n 's/^name: //p' <<<"${cfg}" | head -n 1)"
while IFS= read -r svc; do
    img="$(image_of "${svc}" "${cfg}")"
    case "${img}" in
        postgres:*|docker.io/automaticrippingmachine/arm-*:v3.9.9|docker.io/automaticrippingmachine/arm-*:v3.9.9-intel|docker.io/automaticrippingmachine/arm-*:v3.9.9-amd)
            check "${svc} runs a release image" "yes" "yes" ;;
        *)  check "${svc} runs a release image" "a registry image at v3.9.9" "${img:-none}" ;;
    esac
done < <(compose config --services)

# Mounts: the backend's /raw and /media come from the chosen folders, and
# every other host path is inside the arm folder or a system path the template
# names on purpose.
mounts="$(awk '
    /^  [a-z][a-z0-9-]*:$/ { svc=$1; sub(":", "", svc) }
    /^ *source: / { src=$0; sub(/^ *source: /, "", src) }
    /^ *target: / { if (src != "") { t=$0; sub(/^ *target: /, "", t); print svc "|" src "|" t; src="" } }
' <<<"${cfg}")"
check "backend /raw is the chosen folder, spaces and all" "arm-backend|${RAW_PATH}|/raw" "$(grep '^arm-backend|.*|/raw$' <<<"${mounts}")"
check "backend /media is the chosen folder" "arm-backend|${MEDIA_PATH}|/media" "$(grep '^arm-backend|.*|/media$' <<<"${mounts}")"
stray=""
while IFS='|' read -r svc src target; do
    case "${src}" in
        "${ARM_DIR}"/*|"${RAW_PATH}"|"${MEDIA_PATH}"|/var/run/docker.sock|/dev/disk) ;;
        /*) stray+="${svc}:${src} " ;;
        *)  ;;   # a named volume
    esac
done <<<"${mounts}"
check "no host path escapes the arm folder" "" "${stray}"

env_raw="$(awk '/^  arm-backend:$/ {f=1} f && /ARM_HOST_RAW_PATH:/ {sub(/^ *ARM_HOST_RAW_PATH: /, ""); print; exit}' <<<"${cfg}")"
check "backend is told the raw folder for spawned containers" "${RAW_PATH}" "${env_raw}"

exit "$fail"
