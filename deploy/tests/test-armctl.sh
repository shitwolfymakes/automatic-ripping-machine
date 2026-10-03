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

# --- docker diagnosis ---------------------------------------------------------------
# dstate <stub code>: run docker_state with `command -v docker` succeeding and
# `docker` replaced by the given stub body.
dstate() {
    (
        command() { if [[ "$1" == -v && "$2" == docker ]]; then return 0; fi; builtin command "$@"; }
        eval "docker() { $1; }"
        docker_state
    )
}
check "docker: not installed" "missing" \
    "$( (command() { if [[ "$1" == -v && "$2" == docker ]]; then return 1; fi; builtin command "$@"; }; docker_state) )"
# shellcheck disable=SC2016 # the stub body is evaluated later, single quotes are intended
check "docker: too old" "old:20.10.24" \
    "$(dstate 'case "$1" in --version) echo "Docker version 20.10.24+dfsg1, build 297e128" ;; esac')"
# shellcheck disable=SC2016 # the stub body is evaluated later, single quotes are intended
check "docker: no compose plugin" "no-compose" \
    "$(dstate 'case "$1" in --version) echo "Docker version 27.3.1, build ce12230" ;; compose) return 1 ;; esac')"
# shellcheck disable=SC2016 # the stub body is evaluated later, single quotes are intended
check "docker: daemon not running" "daemon-down" \
    "$(dstate 'case "$1" in --version) echo "Docker version 27.3.1, build x" ;; compose) return 0 ;; info) echo "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?" >&2; return 1 ;; esac')"
# shellcheck disable=SC2016 # the stub body is evaluated later, single quotes are intended
check "docker: session lacks the docker group" "no-group" \
    "$(dstate 'case "$1" in --version) echo "Docker version 27.3.1, build x" ;; compose) return 0 ;; info) echo "permission denied while trying to connect to the Docker daemon socket" >&2; return 1 ;; esac')"
# shellcheck disable=SC2016 # the stub body is evaluated later, single quotes are intended
check "docker: ready" "ok" \
    "$(dstate 'case "$1" in --version) echo "Docker version 27.3.1, build x" ;; *) return 0 ;; esac')"

osr="${TMPROOT}/os-release"
printf 'ID=debian\nVERSION_CODENAME=trixie\n' > "$osr"
check "os: debian" "debian" "$(OS_RELEASE_FILE="$osr" os_family)"
check "os: codename" "trixie" "$(OS_RELEASE_FILE="$osr" os_codename)"
printf 'ID=ubuntu\nVERSION_CODENAME=noble\n' > "$osr"
check "os: ubuntu" "ubuntu" "$(OS_RELEASE_FILE="$osr" os_family)"
printf 'ID=linuxmint\nID_LIKE="ubuntu debian"\n' > "$osr"
check "os: a derivative is not automated" "other" "$(OS_RELEASE_FILE="$osr" os_family)"
check "os: no os-release file" "other" "$(OS_RELEASE_FILE="${TMPROOT}/absent" os_family)"

# --- docker group restart (Review Focus 5) --------------------------------------------
# regroup <ARMCTL_SG_REEXEC value> <sg available: yes|no>
regroup() {
    (
        new_install regroup
        ARMCTL_ARGV=(up --force); ARMCTL_SG_REEXEC="$1"
        me="$(id -un)"
        getent() { echo "docker:x:998:someone,${me}"; }
        if [[ "$2" == yes ]]; then
            command() { if [[ "$1" == -v && "$2" == sg ]]; then return 0; fi; builtin command "$@"; }
            sg() { return 0; }
        else
            command() { if [[ "$1" == -v && "$2" == sg ]]; then return 1; fi; builtin command "$@"; }
        fi
        run_sg_exec() { echo "EXEC $1"; exit 0; }
        reexec_under_docker_group
    )
}
out="$(regroup "" yes 2>&1)"
has "regroup: restarts the same command under the docker group" "EXEC ARMCTL_SG_REEXEC=1 " "$out"
has "regroup: the restart carries the original arguments" "armctl up --force" "$out"
rc=0; out="$(regroup 1 yes 2>&1)" || rc=$?
check "regroup: never restarts twice" "1" "$rc"
lacks "regroup: a second attempt does not exec" "EXEC" "$out"
has "regroup: a second attempt asks for a new login" "Log out and back in" "$out"
rc=0; out="$(regroup "" no 2>&1)" || rc=$?
check "regroup: without sg it stops" "1" "$rc"
has "regroup: without sg it names the command to run after login" "armctl up --force" "$out"

# --- ensure_docker -----------------------------------------------------------------
# edocker <first state> <os id> <ARMCTL_ASSUME>
edocker() {
    (
        new_install edocker
        statefile="${TMPROOT}/dstate"; echo "$1" > "${statefile}"
        printf 'ID=%s\nVERSION_CODENAME=trixie\n' "$2" > "${TMPROOT}/osr"; OS_RELEASE_FILE="${TMPROOT}/osr"
        ARMCTL_ASSUME="$3"; SKIPPED=()
        docker_state() { cat "${statefile}"; }
        docker_apt_install() { echo "APT $1"; echo ok > "${statefile}"; }
        ensure_docker </dev/null
    )
}
out="$(edocker ok debian ask 2>&1)"
has "ensure_docker: nothing to do when ready" "Docker is ready" "$out"
out="$(edocker missing debian yes 2>&1)"
has "ensure_docker: installs on debian with consent" "APT debian" "$out"
has "ensure_docker: ready after the install" "Docker is ready" "$out"
rc=0; out="$(edocker missing debian ask 2>&1)" || rc=$?
check "ensure_docker: no terminal and no --yes stops" "1" "$rc"
lacks "ensure_docker: nothing is installed without consent" "APT" "$out"
has "ensure_docker: the docs are linked" "docs.docker.com/engine/install" "$out"
rc=0; out="$(edocker old:20.10.24 fedora yes 2>&1)" || rc=$?
check "ensure_docker: another distro stops even with --yes" "1" "$rc"
lacks "ensure_docker: another distro is never automated" "APT" "$out"
has "ensure_docker: another distro gets the docs link" "docs.docker.com/engine/install" "$out"
has "ensure_docker: the reason is stated" "too old" "$out"

# --- PATH link ---------------------------------------------------------------------
# plink <case name> <PATH has ~/.local/bin: yes|no> <ARMCTL_ASSUME> [pre-existing: foreign|own]
plink() {
    (
        new_install "plink-$1"
        ARMCTL_CMD="${ARM_DIR}/armctl"  # armctl_settings keeps the first value it saw in this process
        HOME="${TMPROOT}/plink-$1/home"; mkdir -p "${HOME}/.local/bin"
        ARMCTL_SYSTEM_BIN="${TMPROOT}/plink-$1/sysbin"; mkdir -p "${ARMCTL_SYSTEM_BIN}"
        printf '#!/bin/sh\n' > "${ARM_DIR}/armctl"
        if [[ "$2" == yes ]]; then PATH="${HOME}/.local/bin:${PATH}"; dest="${HOME}/.local/bin/armctl"; else dest="${ARMCTL_SYSTEM_BIN}/armctl"; fi
        case "${4:-}" in
            foreign) echo other > "${dest}" ;;
            own)     ln -s "${ARM_DIR}/armctl" "${dest}" ;;
        esac
        ARMCTL_ASSUME="$3"; SKIPPED=()
        sudo() { if [[ "${PLINK_SUDO_FAILS:-}" == 1 ]]; then return 1; fi; "$@"; }
        if [[ "${PLINK_LN_FAILS:-}" == 1 ]]; then chmod 555 "$(dirname "${dest}")"; fi
        link_armctl </dev/null >/dev/null 2>&1
        if [[ -L "${dest}" ]]; then echo "LINK=$(readlink "${dest}")"; else echo "LINK=none"; fi
        echo "CMD=${ARMCTL_CMD}"
        echo "SKIPPED=${SKIPPED[*]:-}"
        if [[ -f "${dest}" && ! -L "${dest}" ]]; then echo "FOREIGN=$(cat "${dest}")"; fi
    )
}
out="$(plink local yes ask)"
has "path link: ~/.local/bin on the PATH gets the link, no sudo, no question" "LINK=${TMPROOT}/plink-local/arm/armctl" "$out"
has "path link: the short command is advertised" "CMD=armctl" "$out"
out="$(plink sys-yes no yes)"
has "path link: the system folder is used with consent" "LINK=${TMPROOT}/plink-sys-yes/arm/armctl" "$out"
out="$(plink sys-ask no ask)"
has "path link: no terminal skips the sudo link" "LINK=none" "$out"
has "path link: the full path is advertised when skipped" "CMD=${TMPROOT}/plink-sys-ask/arm/armctl" "$out"
has "path link: the skip is recorded" "armctl on the PATH" "$out"
out="$(plink foreign yes ask foreign)"
has "path link: a file we did not create is left alone" "FOREIGN=other" "$out"
has "path link: the full path is advertised when blocked" "CMD=${TMPROOT}/plink-foreign/arm/armctl" "$out"
out="$(plink own yes ask own)"
has "path link: our own link is kept" "CMD=armctl" "$out"
out="$(PLINK_SUDO_FAILS=1 plink sudofail no yes)"
has "path link: a failed sudo link makes no link" "LINK=none" "$out"
has "path link: a failed sudo link keeps the full path" "CMD=${TMPROOT}/plink-sudofail/arm/armctl" "$out"
has "path link: a failed sudo link is recorded" "could not create" "$out"
out="$(PLINK_LN_FAILS=1 plink lnfail yes ask)"
has "path link: a failed ln makes no link" "LINK=none" "$out"
has "path link: a failed ln keeps the full path" "CMD=${TMPROOT}/plink-lnfail/arm/armctl" "$out"
has "path link: a failed ln is recorded" "could not create" "$out"
chmod -R u+w "${TMPROOT}/plink-lnfail" 2>/dev/null || true

# --- install flow ----------------------------------------------------------------------
echo v3.1.0 > "${REL}/VERSION"
FLOW_STEPS=(ensure_docker acquire_lock ensure_layout choose_storage ensure_ca write_host_overlay ensure_nvidia_container_toolkit install_udev_rule link_armctl stack_up finish_up offload_completion_report)
# flow <install name> [install args...]: run cmd_install with every stage
# replaced by a recorder; print the order, then the parsed answers.
flow() {
    (
        ARM_DIR="${TMPROOT}/$1/arm"; mkdir -p "${ARM_DIR}/.armctl"; armctl_settings; rm -f "${ENV_FILE}"
        shift
        ARMCTL_RELEASE_DIR="${REL}"
        log_file="${TMPROOT}/flow.log"; : > "${log_file}"
        for fn in "${FLOW_STEPS[@]}"; do
            eval "${fn}() { echo ${fn} >> \"\${log_file}\"; }"
        done
        choose_profile() { PROFILE="${PROFILE_ARG:-full}"; echo "choose_profile ${PROFILE}" >> "${log_file}"; }
        setup_remote_offload() { REMOTE_BACKEND_SAN="192.168.0.68"; echo setup_remote_offload >> "${log_file}"; }
        write_env() { echo write_env >> "${log_file}"; if [[ "${PROFILE}" == offload ]]; then echo 'ARM_TRANSCODE_DOCKER_HOST=ssh://sam@h' > "${ENV_FILE}"; else : > "${ENV_FILE}"; fi; }
        make_leaf() { echo "make_leaf $*" >> "${log_file}"; }
        offload_remote_run_init() { :; }
        hostname() { echo testhost; }
        ARMCTL_ARGV=(install "$@")
        cmd_install "$@" </dev/null >/dev/null 2>&1
        echo "ASSUME=${ARMCTL_ASSUME} RAW=${RAW_ARG} MEDIA=${MEDIA_ARG} PREFIX=${IMAGE_PREFIX_ARG} TAG=${ARM_IMAGE_TAG_DEFAULT}" >> "${log_file}"
        echo "ARGV=${ARMCTL_ARGV[*]}" >> "${log_file}"
        tr '\n' ';' < "${log_file}"
    )
}
check "install: full box runs every stage in order" \
    "choose_profile full;ensure_docker;acquire_lock;ensure_layout;choose_storage;ensure_ca;make_leaf arm-backend;make_leaf arm-db;make_leaf arm-ui localhost testhost;write_env;write_host_overlay;ensure_nvidia_container_toolkit;install_udev_rule;link_armctl;stack_up;finish_up;ASSUME=ask RAW= MEDIA= PREFIX= TAG=v3.1.0;ARGV=install --profile full;" \
    "$(flow flow-full)"
out="$(flow flow-offload --profile offload)"
has "install: offload runs the walkthrough after storage" "choose_storage;setup_remote_offload;ensure_ca;" "$out"
has "install: offload puts the callback address on the backend certificate" "make_leaf arm-backend 192.168.0.68;" "$out"
lacks "install: offload does not offer the local NVIDIA toolkit" "ensure_nvidia_container_toolkit" "$out"
has "install: offload ends with the verification table" "finish_up;offload_completion_report;" "$out"
has "install: a profile given by flag is not repeated in the restart arguments" "ARGV=install --profile offload;" "$out"
out="$(flow flow-ripper --profile ripper-only)"
lacks "install: ripper-only does not offer the NVIDIA toolkit" "ensure_nvidia_container_toolkit" "$out"
lacks "install: ripper-only has no offload walkthrough" "setup_remote_offload" "$out"
out="$(flow flow-nostart --no-start)"
lacks "install: --no-start does not start the stack" "stack_up" "$out"
has "install: --no-start still configures" "write_env;write_host_overlay;" "$out"
out="$(flow flow-flags --yes --raw-path /r --media-path=/m --image-prefix ghcr.io/fork)"
has "install: flags are parsed in both --x v and --x=v forms" "ASSUME=yes RAW=/r MEDIA=/m PREFIX=ghcr.io/fork TAG=v3.1.0;" "$out"
out="$(flow flow-decline --no-host-changes)"
has "install: --no-host-changes declines host changes" "ASSUME=no " "$out"
out="$( (new_install flow-bad; ARMCTL_RELEASE_DIR="${REL}"; ARMCTL_ARGV=(install); cmd_install --bogus) 2>&1 || true)"
has "install: an unknown option is rejected" "unknown option for install: --bogus" "$out"
out="$( (new_install flow-noval; ARMCTL_RELEASE_DIR="${REL}"; ARMCTL_ARGV=(install); cmd_install --raw-path) 2>&1 || true)"
has "install: an option without its value is rejected" "--raw-path needs a value" "$out"
out="$( (new_install flow-nover; ARMCTL_RELEASE_DIR="${TMPROOT}/empty-rel"; mkdir -p "${ARMCTL_RELEASE_DIR}"; ARMCTL_ARGV=(install); cmd_install) 2>&1 || true)"
has "install: a bundle without VERSION is rejected" "no VERSION file" "$out"
has "install: --help lists the options" "--offload-backend-url" "$(install_usage)"

# Unattended offload install, configure only, through the real flow: profile,
# storage, the offload walkthrough, certificates, .env, overlay and the
# completion table. Only the host and the remote are stubbed; the remote is
# unreachable, so every remote check fails. Nothing may wait on stdin and the
# run must reach the end with the failures in the completion table.
unattended_offload_install() {
    ARM_DIR="${TMPROOT}/unattended-$1/arm"; mkdir -p "${ARM_DIR}"; armctl_settings
    ARMCTL_RELEASE_DIR="${REL}"
    ensure_docker() { :; }; acquire_lock() { :; }; link_armctl() { :; }
    docker() { return 1; }
    hostname() { echo testhost; }
    ssh-keygen() { local f=""; while [[ $# -gt 0 ]]; do [[ "$1" == -f ]] && f="$2"; shift; done; : > "$f"; echo "ssh-ed25519 AAAA test" > "$f.pub"; }
    ssh-keyscan() { return 1; }
    ssh() { cat >/dev/null; return 255; }
    REMOTE_RUN=(false)
    BACKEND_RUNNING_TEST=(false)
    ARMCTL_ARGV=(install)
    cmd_install --profile offload --offload-host ssh://sam@192.168.0.92 \
        --offload-backend-url https://192.168.0.68:8080 --no-host-changes --no-start
    echo "INSTALL REACHED THE END"
}
set +e
out="$( ( set -e; unattended_offload_install eof ) </dev/null 2>&1 )"
rc=$?
set -e
check "unattended offload install, stdin at end-of-input: exits 0" "0" "$rc"
has "unattended offload install: reaches the end" "INSTALL REACHED THE END" "$out"
has "unattended offload install: the completion table runs" "Remote offload verification (ssh://sam@192.168.0.92)" "$out"
has "unattended offload install: the table shows the failed ssh row" "ssh + docker access ......... FAIL" "$out"
has "unattended offload install: the table shows the failed CA row" "CA fingerprint .............. FAIL" "$out"
has "unattended offload install: the table shows the failed image row" "transcode image ............. FAIL" "$out"
has "unattended offload install: the summary lists the skipped host changes" "skipped during this install" "$out"
has "unattended offload install: .env records the offload host" "ARM_TRANSCODE_DOCKER_HOST=ssh://sam@192.168.0.92" "$(cat "${TMPROOT}/unattended-eof/arm/.armctl/.env")"
# stdin an open pipe that never reaches end-of-input (a FIFO opened read-write).
mkfifo "${TMPROOT}/install.fifo"
exec 7<>"${TMPROOT}/install.fifo"
( set -e; unattended_offload_install pipe ) <&7 >"${TMPROOT}/install-pipe.out" 2>&1 &
pid=$!
waited=0
while kill -0 "${pid}" 2>/dev/null && (( waited < 300 )); do sleep 0.1; waited=$(( waited + 1 )); done
if kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}" 2>/dev/null || true
    rc="blocked"
else
    set +e; wait "${pid}"; rc=$?; set -e
fi
exec 7>&-
check "unattended offload install, stdin an open pipe: does not block" "0" "${rc}"
has "unattended offload install, open pipe: the completion table shows the failures" "ssh + docker access ......... FAIL" "$(cat "${TMPROOT}/install-pipe.out")"

# layout and summary, for real
new_install layout; ( ensure_layout )
check "layout: certs folder is private" "700" "$(stat -c '%a' "${ARM_DIR}/certs")"
check "layout: state folder is private" "700" "$(stat -c '%a' "${ARM_STATE_DIR}")"
check "layout: logs folder is setgid, group-writable" "2775" "$(stat -c '%a' "${ARM_DIR}/logs")"
for d in db backups scripts iso-library; do
    check "layout: ${d} exists" "yes" "$( [[ -d "${ARM_DIR}/${d}" ]] && echo yes || echo no )"
done
out="$( (SKIPPED=("udev rule (no terminal to ask on)"); print_install_summary 1) )"
has "summary: names the URL" "https://localhost:8081" "$out"
has "summary: lists what was skipped" "udev rule (no terminal to ask on)" "$out"
has "summary: says how to revisit skipped steps" "armctl install" "$out"
out="$( (SKIPPED=(); print_install_summary 0) )"
has "summary: --no-start says how to start" "armctl up" "$out"
lacks "summary: nothing skipped, no skipped section" "skipped during this install" "$out"

# udev: consent gates the write; a current rule asks nothing
udev_case() {  # udev_case <rule current: yes|no> <ARMCTL_ASSUME>
    (
        command() { if [[ "$1" == -v && "$2" == udevadm ]]; then return 0; fi; builtin command "$@"; }
        # eval, so the helper's own $1 is baked into the stub.
        eval "udev_rule_current() { [[ $1 == yes ]]; }"
        ensure_udev_rule() { echo WROTE; }
        sudo() { return 0; }
        ARMCTL_ASSUME="$2"; SKIPPED=()
        install_udev_rule </dev/null
        echo "SKIPPED=${SKIPPED[*]:-}"
    )
}
lacks "udev: a current rule is not rewritten" "WROTE" "$(udev_case yes yes)"
has "udev: with consent the rule is written" "WROTE" "$(udev_case no yes)"
out="$(udev_case no ask)"
lacks "udev: no terminal does not write" "WROTE" "$out"
has "udev: the skip is recorded" "SKIPPED=udev rule" "$out"

# udev: consent given (--yes) but sudo cannot run without a password. The
# library's paste block is not used; the rule is left in the state folder with
# three plain commands, and the step is listed as skipped.
udev_nosudo() {
    (
        new_install udev-nosudo
        command() { if [[ "$1" == -v && "$2" == udevadm ]]; then return 0; fi; builtin command "$@"; }
        udev_rule_current() { return 1; }
        ensure_udev_rule() { echo WROTE; }
        sudo() { return 1; }
        ARMCTL_ASSUME=yes; SKIPPED=()
        install_udev_rule </dev/null
        echo "SKIPPED=${SKIPPED[*]:-}"
        if cmp -s "${ARM_STATE_DIR}/99-arm-no-automount.rules" <(printf '%s' "$(build_udev_rule_content)"); then
            echo "RULEFILE=same"
        fi
    ) 2>&1
}
out="$(udev_nosudo)"
lacks "udev, no sudo: the library's paste block is not used" "WROTE" "$out"
has "udev, no sudo: the step is listed as skipped" "SKIPPED=udev rule (sudo was not available" "$out"
has "udev, no sudo: the rule is left in the state folder, as the installed bytes" "RULEFILE=same" "$out"
has "udev, no sudo: command to install the file" "sudo install -m 0644 ${TMPROOT}/udev-nosudo/arm/.armctl/99-arm-no-automount.rules /etc/udev/rules.d/99-arm-no-automount.rules" "$out"
has "udev, no sudo: command to reload the rules" "sudo udevadm control --reload-rules" "$out"
has "udev, no sudo: command to trigger the block subsystem" "sudo udevadm trigger --subsystem-match=block" "$out"
lacks "udev, no sudo: no heredoc to paste" "<<'RULE'" "$out"

# --- NVIDIA container toolkit -----------------------------------------------------------
# nv_case: an NVIDIA GPU on an apt host. NV_* variables shape docker and curl.
# Run standalone with errexit live, as in armctl, then report what was called.
nv_case() {
    (
        nvlog="${TMPROOT}/nv.log"; : > "${nvlog}"
        command() {
            if [[ "$1" == -v ]]; then
                case "$2" in
                    lspci|apt-get) return 0 ;;
                    nvidia-ctk) return "${NV_CTK:-1}" ;;
                esac
            fi
            builtin command "$@"
        }
        lspci() { echo "01:00.0 VGA compatible controller: NVIDIA Corporation GA102"; }
        docker() {
            case "$1" in
                info) printf '%s\n' "${NV_INFO:-}"; return "${NV_INFO_RC:-0}" ;;
                ps) if [[ "$*" == *label=* ]]; then printf '%s' "${NV_SPAWNED:-}"; else printf '%s\n' "${NV_NAMES:-}"; fi ;;
            esac
        }
        curl() { echo "curl" >> "${nvlog}"; [[ "${NV_CURL:-ok}" == ok ]] && echo DATA; }
        sudo() { echo "sudo $*" >> "${nvlog}"; if [[ "$1" == gpg || "$1" == tee ]]; then cat >/dev/null; fi; return 0; }
        ARMCTL_ASSUME=yes; SKIPPED=(); ARMCTL_CMD=/x/arm/armctl
        set +e
        ( set -e; ensure_nvidia_container_toolkit; echo "CONTINUED SKIPPED=${SKIPPED[*]:-}" ) </dev/null
        echo "rc=$?"
        set -e
        echo "CALLS=$(tr '\n' ';' < "${nvlog}")"
    ) 2>&1
}
# docker can exit non-zero after printing the runtime list (SIGPIPE when a
# reader stops early); the output, not the exit code, says the toolkit is there.
out="$(NV_CTK=0 NV_INFO=" Runtimes: io.containerd.runc.v2 nvidia runc" NV_INFO_RC=141 nv_case)"
has "nvidia: an installed toolkit is recognised from docker info's output" "CALLS=" "$out"
lacks "nvidia: an installed toolkit installs nothing" "sudo " "$out"
lacks "nvidia: an installed toolkit downloads nothing" "curl" "$out"
out="$(NV_NAMES="armv3-backend" nv_case)"
lacks "nvidia: the ARM stack running, nothing is installed (it restarts Docker)" "sudo " "$out"
has "nvidia: the ARM stack running, the skip says to stop ARM first" "run '/x/arm/armctl down', then '/x/arm/armctl install' again" "$out"
has "nvidia: the ARM stack running, the install carries on" "CONTINUED" "$out"
out="$(NV_NAMES="someone-else" NV_SPAWNED="0123abcd" nv_case)"
lacks "nvidia: a spawned ripper or transcoder running, nothing is installed" "sudo " "$out"
out="$(NV_CURL=fail nv_case)"
has "nvidia: a failed install does not end the install" "CONTINUED" "$out"
has "nvidia: a failed install exits 0" "rc=0" "$out"
has "nvidia: a failed install is listed as skipped" "NVIDIA container toolkit (the install failed" "$out"
lacks "nvidia: a failed install does not restart Docker" "systemctl restart docker" "$out"
out="$(nv_case)"
has "nvidia: the install runs every step and restarts Docker last" "sudo nvidia-ctk runtime configure --runtime=docker;sudo systemctl restart docker;" "$out"
has "nvidia: the keyring is written without an overwrite question" "sudo gpg --batch --yes --dearmor" "$out"
has "nvidia: a good install skips nothing" "CONTINUED SKIPPED=" "$out"
lacks "nvidia: a good install skips nothing (no entry)" "CONTINUED SKIPPED=NVIDIA" "$out"

# --- upgrade: the old release fetches, then hands over ------------------------------
# upgrade_case <name> <resolved tag> <fetch: ok|fail> [upgrade args...]
upgrade_case() {
    (
        ARM_DIR="${TMPROOT}/$1/arm"; mkdir -p "${ARM_DIR}/.armctl/releases/v3.1.0"; armctl_settings
        ln -sfn releases/v3.1.0 "${ARM_STATE_DIR}/current"
        printf 'ARMCTL_PROFILE=full\nARM_IMAGE_TAG=v3.1.0\n' > "${ENV_FILE}"
        resolved="$2"; fetch="$3"; shift 3
        ARMCTL_RELEASE_DIR="${TMPROOT}/fake-rel"; mkdir -p "${ARMCTL_RELEASE_DIR}"
        log_file="${TMPROOT}/upgrade.log"; : > "${log_file}"
        # The release's own install.sh, as a stub.
        cat > "${ARMCTL_RELEASE_DIR}/install.sh" <<'STUB'
bootstrap_resolve_tag() { printf '%s' "${resolved}"; }
bootstrap_fetch_bundle() {
    echo "fetch $1 [${3:-}]" >> "${log_file}"
    if [[ "${fetch}" == fail ]]; then echo "ERROR: download failed" >&2; exit 1; fi
    mkdir -p "$2"
}
STUB
        run_new_release() { echo "handover $*" >> "${log_file}"; }
        rc=0; ( cmd_upgrade "$@" ) > "${TMPROOT}/upgrade.out" 2>&1 || rc=$?
        {
            echo "rc=${rc}"
            echo "TAG=$(grep '^ARM_IMAGE_TAG=' "${ENV_FILE}" | cut -d= -f2)"
            echo "CURRENT=$(readlink "${ARM_STATE_DIR}/current")"
        } >> "${log_file}"
        tr '\n' ';' < "${log_file}"
        cat "${TMPROOT}/upgrade.out"
    )
}
out="$(upgrade_case upg-same v3.1.0 ok)"
has "upgrade: already on the latest does nothing" "already on v3.1.0" "$out"
lacks "upgrade: already on the latest fetches nothing" "fetch " "$out"
out="$(upgrade_case upg-new v3.2.0 ok --force)"
has "upgrade: the new bundle is fetched" "fetch v3.2.0 []" "$out"
has "upgrade: the NEW release carries out the upgrade" "handover ${TMPROOT}/upg-new/arm/.armctl/releases/v3.2.0/armctl.sh apply-upgrade --from v3.1.0 --to v3.2.0 --force" "$out"
has "upgrade: the old release changes nothing itself" "TAG=v3.1.0;CURRENT=releases/v3.1.0;" "$out"
out="$(upgrade_case upg-named v3.2.0 ok --version v3.1.5)"
has "upgrade: --version names the target" "fetch v3.1.5 []" "$out"
out="$(upgrade_case upg-offline v3.2.0 fail)"
has "upgrade: a failed download stops" "rc=1" "$out"
lacks "upgrade: a failed download hands nothing over" "handover" "$out"
has "upgrade: a failed download leaves the install as it was" "TAG=v3.1.0;CURRENT=releases/v3.1.0;" "$out"
out="$(upgrade_case upg-bundle v3.2.0 ok --bundle /tmp/b.tar.gz)"
has "upgrade: --bundle without --version is refused" "--bundle needs --version" "$out"

# --- upgrade: the new release applies it ----------------------------------------------
# apply_case <name> <FAIL_AT step or ''> [<setup code> [apply-upgrade args...]]
apply_case() {
    (
        ARM_DIR="${TMPROOT}/$1/arm"; state="${ARM_DIR}/.armctl"
        mkdir -p "${state}/releases/v3.0.0" "${state}/releases/v3.1.0" "${state}/releases/v3.2.0"
        armctl_settings
        ln -sfn releases/v3.1.0 "${ARM_STATE_DIR}/current"
        printf 'ARMCTL_PROFILE=full\nARM_IMAGE_PREFIX=reg\nARM_IMAGE_TAG=v3.1.0\nARM_RIPPER_IMAGE=reg/arm-ripper:v3.1.0\n' > "${ENV_FILE}"
        chmod 600 "${ENV_FILE}"
        ARMCTL_RELEASE_DIR="${REL}"; IMAGE_PREFIX_ARG=""
        fail_at="$2"; extra="${3:-}"; extra_args=("${@:4}")
        log_file="${TMPROOT}/apply.log"; : > "${log_file}"
        for fn in "${STEPS[@]}"; do
            eval "${fn}() { echo ${fn} >> \"\${log_file}\"; if [[ \"\${fail_at}\" == ${fn} ]]; then exit 1; fi; }"
        done
        backend_started_at() { echo T1; }
        published_url() { :; }
        compose() { echo "compose $*" >> "${log_file}"; }
        HEALTH_RESULT="backend healthy"
        eval "${extra}"
        # Standalone, not after `||` or in an `if`: errexit is ignored in any
        # conditional context, which would hide the very failures under test.
        set +e
        ( set -e; cmd_apply_upgrade --from v3.1.0 --to v3.2.0 "${extra_args[@]+"${extra_args[@]}"}" ) > "${TMPROOT}/apply.out" 2>&1
        rc=$?
        set -e
        {
            echo "rc=${rc}"
            echo "TAG=$(grep '^ARM_IMAGE_TAG=' "${ARM_STATE_DIR}/.env" | cut -d= -f2)"
            echo "RIPPER=$(grep '^ARM_RIPPER_IMAGE=' "${ARM_STATE_DIR}/.env" | cut -d= -f2)"
            echo "CURRENT=$(readlink "${ARM_STATE_DIR}/current")"
            echo "RELEASES=$(cd "${ARM_STATE_DIR}/releases" && echo *)"
            echo "MODE=$(stat -c '%a' "${ARM_STATE_DIR}/.env")"
        } >> "${log_file}"
        tr '\n' ';' < "${log_file}"
        cat "${TMPROOT}/apply.out"
    )
}
out="$(apply_case apply-ok '')"
has "apply: pull, verify, guard and backup all come before the switch" \
    "select_up_services;pull_images;verify_images_present;guard_running_spawned;refresh_arm_gpus;backup_db;remove_spawned_containers;remove_retired_services;compose up -d --no-build;respawn_rippers_if_needed;wait_for_backend;rc=0;" "$out"
has "apply: .env is on the new release" "TAG=v3.2.0;RIPPER=reg/arm-ripper:v3.2.0;" "$out"
has "apply: current points at the new release" "CURRENT=releases/v3.2.0;" "$out"
has "apply: the previous release is kept, older ones pruned" "RELEASES=v3.1.0 v3.2.0;" "$out"
has "apply: .env stays private" "MODE=600;" "$out"
has "apply: the switch is announced" "switched to v3.2.0" "$out"

for step in pull_images verify_images_present guard_running_spawned backup_db; do
    out="$(apply_case "apply-${step}" "${step}")"
    has "apply: a failure at ${step} stops the upgrade" "rc=1;" "$out"
    has "apply: a failure at ${step} leaves .env on the old release" "TAG=v3.1.0;RIPPER=reg/arm-ripper:v3.1.0;" "$out"
    has "apply: a failure at ${step} leaves current on the old release" "CURRENT=releases/v3.1.0;" "$out"
    lacks "apply: a failure at ${step} removes no container" "remove_spawned_containers" "$out"
done

out="$(apply_case apply-unhealthy wait_for_backend)"
has "apply: an unhealthy backend after the switch is an error" "rc=1;" "$out"
has "apply: the install stays on the new release" "TAG=v3.2.0;" "$out"
has "apply: the user is told it was not rolled back, and why" "not rolled back" "$out"
has "apply: the previous release is still there for a manual rollback" "RELEASES=v3.0.0 v3.1.0 v3.2.0;" "$out"
has "apply: the user is told where the previous release is" "releases/v3.1.0" "$out"

# A failed start after the switch is reported like an unhealthy backend.
# The real go_live, with only `compose up` failing: it must stop right there.
# shellcheck disable=SC2016  # evaluated inside apply_case, on purpose
out="$(apply_case apply-start-fails '' 'compose() { echo "compose $*" >> "${log_file}"; [[ "$1" != up ]]; }')"
has "apply: a failed compose up stops go_live before the respawn" "compose up -d --no-build;rc=1;" "$out"
lacks "apply: a failed compose up does not respawn rippers" "respawn_rippers_if_needed" "$out"
has "apply: a failed start after the switch is an error" "rc=1;" "$out"
has "apply: a failed start is reported as not rolled back" "not rolled back" "$out"
has "apply: a failed start names the previous release" "releases/v3.1.0" "$out"
has "apply: a failed start stays on the new release" "TAG=v3.2.0;RIPPER=reg/arm-ripper:v3.2.0;CURRENT=releases/v3.2.0;" "$out"
has "apply: a failed start prunes nothing" "RELEASES=v3.0.0 v3.1.0 v3.2.0;" "$out"
lacks "apply: a failed start does not wait for the backend" "wait_for_backend" "$out"

# The backup named in the report is the one taken in this run, never a stale one.
# shellcheck disable=SC2016  # evaluated inside apply_case, on purpose
stale='mkdir -p "${ARM_DIR}/backups"; : > "${ARM_DIR}/backups/pg-backup-20200101T000000Z.sql.gz"'
out="$(apply_case apply-nobackup wait_for_backend "${stale}" --no-backup)"
has "apply: --no-backup, the report says no backup was taken" "No database backup was taken (--no-backup)" "$out"
lacks "apply: --no-backup, a stale backup is not named" "pg-backup-20200101T000000Z" "$out"
out="$(apply_case apply-ownbackup wait_for_backend "${stale}; backup_db() { echo backup_db >> \"\${log_file}\"; BACKUP_FILE=\"\${ARM_DIR}/backups/pg-backup-20260101T000000Z.sql.gz\"; }")"
has "apply: the report names the backup taken in this run" "Database backup from before the switch: ${TMPROOT}/apply-ownbackup/arm/backups/pg-backup-20260101T000000Z.sql.gz" "$out"
lacks "apply: the report does not name the stale backup" "pg-backup-20200101T000000Z" "$out"

# --version becomes a folder name, so it must not name another folder.
out="$(upgrade_case upg-badver v3.2.0 ok --version ../.. --bundle /tmp/b.tar.gz)"
has "upgrade: a path-like --version is refused" "is not a valid release tag" "$out"
has "upgrade: a path-like --version exits 2" "rc=2" "$out"
lacks "upgrade: a path-like --version fetches nothing" "fetch " "$out"

# --- dispatch -----------------------------------------------------------------------
rc=0; (ARM_DIR="${TMPROOT}/settings/arm"; current_uid() { echo 1000; }; armctl_main frobnicate) >/dev/null 2>&1 || rc=$?
check "an unknown command exits 2" "2" "$rc"
has "help lists the commands" "upgrade" "$(armctl_main help)"

exit "$fail"
