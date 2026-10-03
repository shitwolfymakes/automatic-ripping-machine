#!/usr/bin/env bash
# shellcheck disable=SC2317,SC2329,SC2034,SC2030,SC2031
# (Stubs below are called indirectly by sourced armctl code, and most checks
# run in subshells on purpose so one check's stubs cannot leak into the next.)
# Zero-infra suite for deploy/armctl.sh and deploy/install/*: no docker, no
# root, no network. Sources armctl.sh through its ARMCTL_SOURCE_ONLY seam.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY="${HERE}/.."

export ARMCTL_SOURCE_ONLY=1
# shellcheck disable=SC1091
source "${DEPLOY}/armctl.sh"

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
has() {  # has <label> <needle> <haystack>
    check "$1" "yes" "$( [[ "$3" == *"$2"* ]] && echo yes || echo no )"
}
lacks() {  # lacks <label> <needle> <haystack>
    check "$1" "no" "$( [[ "$3" == *"$2"* ]] && echo yes || echo no )"
}

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

# new_install <name>: a throwaway arm folder with settings loaded.
new_install() {
    ARM_DIR="${TMPROOT}/$1/arm"
    mkdir -p "${ARM_DIR}/.armctl"
    armctl_settings
    printf 'ARMCTL_PROFILE=full\n' > "${ENV_FILE}"
}

# --- output style -------------------------------------------------------------
check "arm_say: two-space indent" "  hello" "$(arm_say hello)"
check "arm_sub: re-indents the line it is given" "      detail" "$(arm_sub '         detail')"
check "arm_warn: bang, on stderr" "  ! careful" "$(arm_warn careful 2>&1 >/dev/null)"
check "arm_err: ERROR, on stderr" "ERROR: broken" "$(arm_err broken 2>&1 >/dev/null)"

# --- root refusal ---------------------------------------------------------------
out="$( (current_uid() { echo 0; }; refuse_root) 2>&1 || true)"
has "root is refused with the reason" "do not run armctl as root" "$out"
rc=0; (current_uid() { echo 0; }; refuse_root) >/dev/null 2>&1 || rc=$?
check "root refusal exits 1" "1" "$rc"
rc=0; (current_uid() { echo 1000; }; refuse_root) >/dev/null 2>&1 || rc=$?
check "a normal user passes" "0" "$rc"

# --- settings -------------------------------------------------------------------
out="$( (unset ARM_DIR; armctl_settings) 2>&1 || true)"
has "missing ARM_DIR is explained" "ARM_DIR is not set" "$out"
out="$( (ARM_DIR="${TMPROOT}/ripper"; armctl_settings) 2>&1 || true)"
has "a folder not named arm is rejected" "must be named 'arm'" "$out"
new_install settings
check "state dir is under the arm folder" "${ARM_DIR}/.armctl" "${ARM_STATE_DIR}"
check "env file is in the state dir" "${ARM_DIR}/.armctl/.env" "${ENV_FILE}"
check "compose runs from the parent of arm" "${TMPROOT}/settings" "${ARM_COMPOSE_CWD}"
has "compose is told the project directory" "--project-directory ${TMPROOT}/settings" "${ARM_COMPOSE_CMD[*]}"
has "compose reads the template" "-f ${ARMCTL_RELEASE_DIR}/docker-compose.yml.example" "${ARM_COMPOSE_CMD[*]}"
has "compose reads the release overlay" "-f ${ARMCTL_RELEASE_DIR}/docker-compose.release.yml" "${ARM_COMPOSE_CMD[*]}"
joined="${ARM_COMPOSE_CMD[*]}"
has "compose reads the host overlay last" "-f ${ARM_DIR}/.armctl/host-overlay.yml" "${joined##*release.yml}"
use_env_file "${ARM_STATE_DIR}/.env.next"
has "use_env_file switches the env file compose reads" "--env-file ${ARM_STATE_DIR}/.env.next" "${ARM_COMPOSE_CMD[*]}"

# --- profile --------------------------------------------------------------------
new_install profile
printf 'ARMCTL_PROFILE=ripper-only\n' > "${ENV_FILE}"; load_profile
check "ripper-only profile sets RIPPER_ONLY" "1" "${RIPPER_ONLY}"
printf 'ARMCTL_PROFILE=full\n' > "${ENV_FILE}"; load_profile
check "full profile clears RIPPER_ONLY" "0" "${RIPPER_ONLY}"
: > "${ENV_FILE}"; load_profile
check "no saved profile means full" "full" "${PROFILE}"
out="$( (rm -f "${ENV_FILE}"; require_installed) 2>&1 || true)"
has "commands before install say what to run" "armctl install" "$out"

# --- images must be present after the pull (Review Focus 4) ---------------------
# compose tolerates a failed pull for a service that has a build section, so
# armctl checks for itself before it touches the running stack.
images() {  # images <image that is missing, or empty>
    (
        new_install images
        missing_image="$1"
        compose() {
            case "$*" in
                "config --services") printf '%s\n' arm-db arm-backend ;;
                config) printf 'name: armv3\nservices:\n  arm-backend:\n    build:\n      context: /x\n    image: reg/arm-backend:v3.1.0\n  arm-db:\n    image: postgres:18\nvolumes:\n  arm-data: {}\n' ;;
            esac
        }
        docker() { [[ "$1 $2" == "image inspect" && "$3" != "${missing_image}" ]]; }
        UP_SERVICES=()
        verify_images_present
    )
}
rc=0; images "" >/dev/null 2>&1 || rc=$?
check "all images present: passes" "0" "$rc"
rc=0; out="$(images "reg/arm-backend:v3.1.0" 2>&1)" || rc=$?
check "a missing image stops the run" "1" "$rc"
has "the missing image is named" "arm-backend (reg/arm-backend:v3.1.0)" "$out"
has "the user is told nothing changed" "Nothing has been changed" "$out"

# --- up and down ordering ---------------------------------------------------------
STEPS=(select_up_services pull_images verify_images_present guard_running_spawned refresh_arm_gpus backup_db remove_spawned_containers remove_retired_services respawn_rippers_if_needed wait_for_backend)
# run_cmd <install name> <FAIL_AT step or ''> <command> [args...]: run an
# armctl command with every step replaced by a recorder; print the order.
run_cmd() {
    (
        new_install "$1"; fail_at="$2"; shift 2
        log_file="${TMPROOT}/steps.log"; : > "${log_file}"
        for fn in "${STEPS[@]}"; do
            eval "${fn}() { echo ${fn} >> \"\${log_file}\"; if [[ \"\${fail_at}\" == ${fn} ]]; then exit 1; fi; }"
        done
        backend_started_at() { echo T1; }
        published_url() { :; }
        compose() { echo "compose $*" >> "${log_file}"; }
        HEALTH_RESULT="backend healthy"
        UP_SERVICES=()
        # A failing step calls `exit`, so run the command one subshell down and
        # record the flags from its EXIT trap.
        (
            trap 'echo "FORCE=${FORCE} NO_BACKUP=${NO_BACKUP}" >> "${log_file}"' EXIT
            "$@"
        ) >/dev/null 2>&1 || true
        tr '\n' ';' < "${log_file}"
    )
}
check "up: pull and verify come before anything changes" \
    "select_up_services;pull_images;verify_images_present;guard_running_spawned;refresh_arm_gpus;backup_db;remove_spawned_containers;remove_retired_services;compose up -d --no-build;respawn_rippers_if_needed;wait_for_backend;FORCE=0 NO_BACKUP=0;" \
    "$(run_cmd up-ok '' cmd_up)"
check "up: a missing image stops before the guard, backup and removal" \
    "select_up_services;pull_images;verify_images_present;FORCE=0 NO_BACKUP=0;" \
    "$(run_cmd up-noimg verify_images_present cmd_up)"
check "up: active work stops before the backup and removal" \
    "select_up_services;pull_images;verify_images_present;guard_running_spawned;FORCE=0 NO_BACKUP=0;" \
    "$(run_cmd up-busy guard_running_spawned cmd_up)"
has "up: --force and --no-backup reach the library" "FORCE=1 NO_BACKUP=1;" "$(run_cmd up-flags '' cmd_up --force --no-backup)"
check "down: guard, then spawned containers, then the stack" \
    "guard_running_spawned;remove_spawned_containers;remove_retired_services;compose down;FORCE=0 NO_BACKUP=0;" \
    "$(run_cmd down-ok '' cmd_down)"
check "down: active work stops before anything is removed" \
    "guard_running_spawned;FORCE=0 NO_BACKUP=0;" \
    "$(run_cmd down-busy guard_running_spawned cmd_down)"
has "down: --force reaches the guard" "FORCE=1" "$(run_cmd down-force '' cmd_down --force)"
out="$( (new_install hints; guard_running_spawned() { echo "${ARM_HINT_FORCE_CMD}"; }; remove_spawned_containers() { :; }; remove_retired_services() { :; }; compose() { :; }; cmd_down) 2>&1)"
has "down: the refusal names armctl down --force" "armctl down --force" "$out"

# --- lock -------------------------------------------------------------------------
if command -v flock >/dev/null 2>&1; then
    out="$( (new_install lock; acquire_lock; (unset ARMCTL_LOCK_HELD; acquire_lock) 2>&1 || true) )"
    has "a second armctl run is refused" "another armctl command is already running" "$out"
    rc=0; (new_install lock2; acquire_lock; acquire_lock) >/dev/null 2>&1 || rc=$?
    check "the lock holder can re-enter" "0" "$rc"
else
    echo "skip - flock not available"
fi

# --- config: storage paths --------------------------------------------------------
for p in "/mnt/nas/raw" "/media/sam/My Passport/rips"; do
    rc=0; valid_storage_path "$p" || rc=$?
    check "storage path accepted: ${p}" "0" "$rc"
done
# shellcheck disable=SC2016 # literal $ in a rejected path is the case under test
for p in "relative/path" "/a:b" '/a"b' '/a$b' "/a#b" '/a\b' "/a'b"; do
    rc=0; valid_storage_path "$p" || rc=$?
    check "storage path rejected: ${p}" "1" "$rc"
done
new_install storage
check "storage: a flag wins" "/srv/rips" \
    "$(pick_storage "raw rips" "/srv/rips" ARM_HOST_RAW_PATH "${ARM_DIR}/raw" </dev/null)"
check "storage: no terminal takes the default" "${ARM_DIR}/raw" \
    "$(pick_storage "raw rips" "" ARM_HOST_RAW_PATH "${ARM_DIR}/raw" </dev/null)"
printf 'ARM_HOST_RAW_PATH=/mnt/saved\n' > "${ENV_FILE}"
check "storage: a saved answer becomes the default" "/mnt/saved" \
    "$(pick_storage "raw rips" "" ARM_HOST_RAW_PATH "${ARM_DIR}/raw" </dev/null)"
# shellcheck disable=SC2016 # the literal ${PWD} is what .env.example ships
printf 'ARM_HOST_RAW_PATH=${PWD}/arm/raw\n' > "${ENV_FILE}"
check "storage: the template's \${PWD} placeholder is not a saved answer" "${ARM_DIR}/raw" \
    "$(pick_storage "raw rips" "" ARM_HOST_RAW_PATH "${ARM_DIR}/raw" </dev/null)"
out="$( (pick_storage "raw rips" "not/absolute" ARM_HOST_RAW_PATH /x </dev/null) 2>&1 || true)"
has "storage: a bad flag value is rejected" "must be a full path" "$out"
( prepare_storage "${ARM_DIR}/raw" )
check "storage: a folder inside arm is created setgid, group-writable" "2775" "$(stat -c '%a' "${ARM_DIR}/raw")"
ro="${TMPROOT}/readonly"; mkdir -p "$ro"; chmod 555 "$ro"
out="$( (prepare_storage "$ro") 2>&1 || true)"
has "storage: an unwritable folder is an error" "is not writable" "$out"
check "storage: a folder outside arm keeps its mode" "555" "$(stat -c '%a' "$ro")"

# --- config: profile ---------------------------------------------------------------
new_install profile-choice; : > "${ENV_FILE}"
check "profile: a flag wins" "ripper-only" "$( (PROFILE_ARG=ripper-only; choose_profile >/dev/null </dev/null; echo "${PROFILE}") )"
check "profile: ripper-only sets RIPPER_ONLY" "1" "$( (PROFILE_ARG=ripper-only; choose_profile >/dev/null </dev/null; echo "${RIPPER_ONLY}") )"
check "profile: no terminal defaults to full" "full" "$( (PROFILE_ARG=""; choose_profile >/dev/null </dev/null; echo "${PROFILE}") )"
printf 'ARMCTL_PROFILE=offload\n' > "${ENV_FILE}"
check "profile: no terminal keeps the saved profile" "offload" "$( (PROFILE_ARG=""; choose_profile >/dev/null </dev/null; echo "${PROFILE}") )"
out="$( (PROFILE_ARG=everything; choose_profile </dev/null) 2>&1 || true)"
has "profile: an unknown profile is rejected" "must be full, ripper-only or offload" "$out"

# --- config: host overlay (Review Focus 1: a path with spaces) ----------------------
new_install overlay
PROFILE=full; RAW_PATH="/media/sam/My Passport/rips"; MEDIA_PATH="/mnt/nas/media"; write_host_overlay
ov="$(cat "${HOST_OVERLAY}")"
has "overlay quotes a path with spaces" '      - "/media/sam/My Passport/rips:/raw"' "$ov"
has "overlay mounts the media folder" '      - "/mnt/nas/media:/media"' "$ov"
lacks "overlay: no published port without offload" "ports:" "$ov"
PROFILE=offload; REMOTE_BACKEND_URL="https://192.168.0.68:8080"; write_host_overlay
ov="$(cat "${HOST_OVERLAY}")"
has "overlay: offload publishes the callback port" '      - "8080:8443"' "$ov"
has "overlay: offload mounts the ssh folder read-only" "      - \"${ARM_DIR}/ssh:/home/arm/.ssh:ro\"" "$ov"
check "overlay: one ports key after a re-run" "1" "$(grep -c '^    ports:$' "${HOST_OVERLAY}")"

# --- config: .env -------------------------------------------------------------------
REL="${TMPROOT}/rel"; mkdir -p "${REL}"; cp "${DEPLOY}/../.env.example" "${REL}/.env.example"
# env_case <install name> <profile> [keep]: run write_env; print the .env.
# `keep` re-runs on the existing .env instead of starting fresh.
env_case() {
    (
        # Not new_install: that would overwrite the .env a `keep` run re-uses.
        ARM_DIR="${TMPROOT}/$1/arm"; mkdir -p "${ARM_DIR}/.armctl"; armctl_settings
        if [[ "${3:-}" != keep ]]; then rm -f "${ENV_FILE}"; fi
        ARMCTL_RELEASE_DIR="${REL}"
        PROFILE="$2"; RIPPER_ONLY=0
        if [[ "$2" == ripper-only ]]; then RIPPER_ONLY=1; fi
        RAW_PATH="/r"; MEDIA_PATH="/m"; ARM_IMAGE_TAG_DEFAULT="v3.1.0"; IMAGE_PREFIX_ARG=""
        REMOTE_DOCKER_HOST="ssh://sam@192.168.0.92"; REMOTE_BACKEND_URL="https://192.168.0.68:8080"
        REMOTE_TRANSCODE_PUID=1001; REMOTE_TRANSCODE_PGID=1000
        REMOTE_GPUS='[{"vendor":"nvenc","device_path":"nvidia://0","encoder_kinds":[]}]'; REMOTE_RENDER_GID=""
        detect_gpus() { printf '[]'; }
        detect_render_gid() { echo 993; }
        detect_cdrom_gid() { printf 24; }
        DETECTED_GPUS_SET=0
        write_env >/dev/null
        cat "${ENV_FILE}"
        stat -c 'MODE=%a' "${ENV_FILE}"
    )
}
e="$(env_case env-full full)"
lacks "env: placeholders are replaced by generated secrets" "change-me" "$e"
has "env: readable by the owner only" "MODE=600" "$e"
has "env: profile is recorded" "ARMCTL_PROFILE=full" "$e"
has "env: full box is transcode-capable" "ARM_TRANSCODE_CAPABLE=true" "$e"
has "env: raw path is absolute" "ARM_HOST_RAW_PATH=/r" "$e"
has "env: logs path is absolute" "ARM_HOST_LOGS_PATH=${TMPROOT}/env-full/arm/logs" "$e"
has "env: certs path is the local folder" "ARM_HOST_CERTS_PATH=${TMPROOT}/env-full/arm/certs" "$e"
# shellcheck disable=SC2016 # the literal ${PWD} is what must be absent
lacks "env: no \${PWD} paths remain" 'ARM_HOST_RAW_PATH=${PWD}' "$e"
has "env: release tag is pinned" "ARM_IMAGE_TAG=v3.1.0" "$e"
has "env: ripper image is pinned" "ARM_RIPPER_IMAGE=docker.io/automaticrippingmachine/arm-ripper:v3.1.0" "$e"
has "env: base transcode image is pinned" "ARM_TRANSCODE_IMAGE=docker.io/automaticrippingmachine/arm-transcode:v3.1.0" "$e"
has "env: intel variant is pinned" "ARM_TRANSCODE_IMAGE_QSV=docker.io/automaticrippingmachine/arm-transcode:v3.1.0-intel" "$e"
has "env: amd variant is pinned" "ARM_TRANSCODE_IMAGE_VAAPI=docker.io/automaticrippingmachine/arm-transcode:v3.1.0-amd" "$e"
has "env: UI origin is allowed" "ARM_ALLOWED_ORIGINS=https://localhost:8081" "$e"
has "env: cdrom gid is detected" "CDROM_GID=24" "$e"
has "env: render gid is detected" "ARM_RENDER_GID=993" "$e"
lacks "env: no offload keys on a full box" "ARM_TRANSCODE_DOCKER_HOST=" "$(grep -v '^#' <<<"$e")"

e="$(env_case env-ripper ripper-only)"
has "env: ripper-only is not transcode-capable" "ARM_TRANSCODE_CAPABLE=false" "$e"
has "env: ripper-only records no GPUs" "ARM_GPUS=[]" "$e"

e="$(env_case env-offload offload)"
has "env: offload records the remote daemon" "ARM_TRANSCODE_DOCKER_HOST=ssh://sam@192.168.0.92" "$e"
has "env: offload points transcoder certs at the remote path" "ARM_HOST_CERTS_PATH=/home/sam/.arm/certs" "$e"
has "env: offload keeps rippers on the local certs" "ARM_RIPPER_CERTS_PATH=${TMPROOT}/env-offload/arm/certs" "$e"
has "env: offload records the remote GPUs" 'ARM_GPUS=[{"vendor":"nvenc"' "$e"

pw_before="$(env_case env-rerun full | grep '^POSTGRES_PASSWORD=')"
echo 'NEW_SETTING=7' >> "${REL}/.env.example"
e="$(env_case env-rerun full keep)"
check "env: a re-run keeps the database password" "$pw_before" "$(grep '^POSTGRES_PASSWORD=' <<<"$e")"
has "env: a re-run adds settings the new release introduced" "NEW_SETTING=7" "$e"
env_case env-switch offload >/dev/null
e="$(env_case env-switch full keep)"
lacks "env: leaving the offload profile removes its keys" "ARM_TRANSCODE_DOCKER_HOST=" "$(grep -v '^#' <<<"$e")"
lacks "env: leaving the offload profile removes the ripper certs override" "ARM_RIPPER_CERTS_PATH=" "$(grep -v '^#' <<<"$e")"

pin="${TMPROOT}/pin.env"; printf 'ARM_IMAGE_PREFIX=ghcr.io/fork\nARM_IMAGE_TAG=v3.0.0\n' > "$pin"
( IMAGE_PREFIX_ARG=""; write_image_pins v3.2.0 "$pin" )
has "pins: an existing prefix is kept across an upgrade" "ARM_RIPPER_IMAGE=ghcr.io/fork/arm-ripper:v3.2.0" "$(cat "$pin")"
out="$( (write_image_pins "" "$pin") 2>&1 || true)"
has "pins: an empty version is refused" "no release version" "$out"

# --- dispatch -----------------------------------------------------------------------
rc=0; (ARM_DIR="${TMPROOT}/settings/arm"; current_uid() { echo 1000; }; armctl_main frobnicate) >/dev/null 2>&1 || rc=$?
check "an unknown command exits 2" "2" "$rc"
has "help lists the commands" "upgrade" "$(armctl_main help)"

exit "$fail"
