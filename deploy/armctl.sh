#!/usr/bin/env bash
# shellcheck disable=SC2034 # the settings assigned here are read by the sourced library and modules
# deploy/armctl.sh: the production launcher for ARM v3.
#
# Lives inside a release bundle at <arm>/.armctl/releases/<tag>/armctl.sh and
# is reached through the generated launcher <arm>/armctl, which exports ARM_DIR.
# The lifecycle functions it calls are the ones devtools/setup-dev.sh uses
# (deploy/lib/). See docs/developers/architecture/06-deployment.md.
set -euo pipefail

ARMCTL_RELEASE_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

armctl_usage() {
    cat <<'USAGE'
Usage: armctl <command> [options]

  install            configure this host and start ARM (re-run to change answers)
  up                 pull images, back up the database, (re)start the stack
  down               stop the stack and the rippers/transcoders it spawned
  upgrade            move to the latest stable release (or --version <tag>)
  compose <args...>  run any `docker compose` command against this install

  up and upgrade:
    --force          go ahead even while a rip or transcode is running (kills it)
    --no-backup      skip the database backup
  down:
    --force          stop even while a rip or transcode is running (kills it)

  `armctl install --help` lists the install options.
USAGE
}

for _lib in common detect certs udev lifecycle; do
    # shellcheck source=/dev/null
    source "${ARMCTL_RELEASE_DIR}/lib/${_lib}.sh"
done
for _mod in ui config nvidia offload; do
    # shellcheck source=/dev/null
    source "${ARMCTL_RELEASE_DIR}/install/${_mod}.sh"
done
unset _lib _mod

# Production output style. These replace the setup-dev defaults that
# lib/common.sh defines; the shared lifecycle functions print through them.
arm_say()  { printf '  %s\n' "$*"; }
# The library passes continuation lines with setup-dev's indentation; strip it
# and apply this style's.
arm_sub()  { local line="$1"; line="${line#"${line%%[![:space:]]*}"}"; printf '      %s\n' "${line}"; }
arm_warn() { printf '  ! %s\n' "$*" >&2; }
arm_err()  { printf 'ERROR: %s\n' "$*" >&2; }

current_uid() { id -u; }

# ARM records the installing user as the owner of the media files (PUID/PGID),
# and arm-data-init refuses PUID 0, so a root run can only produce a broken
# install.
refuse_root() {
    if [[ "$(current_uid)" -eq 0 ]]; then
        arm_err "do not run armctl as root or with sudo."
        arm_sub "ARM records the user who runs it as the owner of your media files, and root is not accepted."
        arm_sub "Run it as your normal user; it asks for sudo only when a step needs it."
        exit 1
    fi
}

# use_env_file <path>: the .env the stack is configured from. An upgrade points
# this at a candidate file until it switches over.
use_env_file() {
    ENV_FILE="$1"
    ARM_COMPOSE_CMD=(docker compose
        --project-directory "${ARM_PARENT_DIR}"
        --env-file "${ENV_FILE}"
        -f "${ARMCTL_RELEASE_DIR}/docker-compose.yml.example"
        -f "${ARMCTL_RELEASE_DIR}/docker-compose.release.yml"
        -f "${HOST_OVERLAY}")
}

# The compose template writes its paths as ./arm/..., so compose runs from the
# folder that CONTAINS arm, and that folder must be named arm.
armctl_settings() {
    if [[ -z "${ARM_DIR:-}" ]]; then
        arm_err "ARM_DIR is not set. Run armctl through the launcher in your arm folder (for example ~/arm/armctl)."
        exit 1
    fi
    if [[ "$(basename "${ARM_DIR}")" != "arm" ]]; then
        arm_err "the install folder must be named 'arm' (got ${ARM_DIR})."
        exit 1
    fi
    ARM_PARENT_DIR="$(dirname "${ARM_DIR}")"
    ARM_STATE_DIR="${ARM_DIR}/.armctl"
    HOST_OVERLAY="${ARM_STATE_DIR}/host-overlay.yml"
    ARM_CERTS_DIR="${ARM_DIR}/certs"
    ARM_COMPOSE_CWD="${ARM_PARENT_DIR}"
    DB_SERVICE="arm-db"
    BACKEND_SERVICE="arm-backend"
    UI_SERVICE="arm-ui"
    RIPPER_ONLY=0
    FORCE=0
    NO_BACKUP=0
    NO_PULL=0
    PROFILE="full"
    ARMCTL_CMD="${ARMCTL_CMD:-${ARM_DIR}/armctl}"
    ARM_HINT_FORCE_CMD="${ARMCTL_CMD} up --force"
    ARM_HINT_IMAGES_READY="Images are pulled"
    ARM_HINT_LOGS_CMD="${ARMCTL_CMD} compose logs"
    ARM_HINT_RIPPER_ONLY="ripper-only profile"
    ARM_UDEV_MANAGED_BY="armctl (the ARM installer)"
    use_env_file "${ARM_STATE_DIR}/.env"
}

# One armctl command at a time per install. An upgrade hands the lock to the
# new release's armctl through ARMCTL_LOCK_HELD.
acquire_lock() {
    if [[ -n "${ARMCTL_LOCK_HELD:-}" ]]; then
        return 0
    fi
    mkdir -p "${ARM_STATE_DIR}"
    if ! command -v flock >/dev/null 2>&1; then
        arm_warn "flock not found; cannot guard against two armctl commands running at once"
        return 0
    fi
    exec 9>"${ARM_STATE_DIR}/lock"
    if ! flock -n 9; then
        arm_err "another armctl command is already running for ${ARM_DIR}. Wait for it to finish."
        exit 1
    fi
    export ARMCTL_LOCK_HELD=1
}

require_installed() {
    if [[ ! -f "${ENV_FILE}" ]]; then
        arm_err "no install found in ${ARM_DIR} (missing ${ENV_FILE}). Run: ${ARMCTL_CMD} install"
        exit 1
    fi
}

load_profile() {
    PROFILE="$(env_file_value ARMCTL_PROFILE)"
    PROFILE="${PROFILE:-full}"
    RIPPER_ONLY=0
    if [[ "${PROFILE}" == "ripper-only" ]]; then
        RIPPER_ONLY=1
    fi
}

require_docker_ready() {
    require docker "Install Docker first: https://docs.docker.com/engine/install/"
    require_compose
}

# The services this host pulls and starts, one per line. select_up_services
# leaves UP_SERVICES empty when nothing is skipped.
stack_services() {
    # shellcheck disable=SC2153 # UP_SERVICES is filled by select_up_services in lib/lifecycle.sh
    if [[ ${#UP_SERVICES[@]} -gt 0 ]]; then
        printf '%s\n' "${UP_SERVICES[@]}"
    else
        compose config --services
    fi
}

pull_images() {
    if [[ "${NO_PULL}" -eq 1 ]]; then
        arm_say "skipping the image pull (--no-pull)"
        return 0
    fi
    local rc=0
    if [[ ${#UP_SERVICES[@]} -gt 0 ]]; then
        arm_say "pulling images: ${UP_SERVICES[*]}"
        compose pull "${UP_SERVICES[@]}" || rc=$?
    else
        arm_say "pulling images"
        compose pull || rc=$?
    fi
    if [[ "${rc}" -ne 0 ]]; then
        arm_err "the image pull failed."
        arm_sub "Nothing has been changed; the running stack is untouched."
        exit 1
    fi
}

# compose reports success for a pull that could not fetch an image when the
# service also has a build section (the dev template's services all do). So
# check that every image this host needs is really here before the guard, the
# backup or any removal.
verify_images_present() {
    local cfg svc img missing=()
    cfg="$(compose config)"
    while IFS= read -r svc; do
        [[ -n "${svc}" ]] || continue
        img="$(awk -v s="  ${svc}:" '$0 == s {f=1; next} f && /^  [a-z]/ {exit} f && /^    image:/ {print $2; exit}' <<<"${cfg}")"
        if [[ -z "${img}" ]]; then
            missing+=("${svc} (no release image is set for it)")
        elif ! docker image inspect "${img}" >/dev/null 2>&1; then
            missing+=("${svc} (${img})")
        fi
    done < <(stack_services)
    if [[ ${#missing[@]} -eq 0 ]]; then
        return 0
    fi
    arm_err "these images are not on this host after the pull:"
    for svc in "${missing[@]}"; do
        arm_sub "${svc}"
    done
    arm_sub "Nothing has been changed; the running stack is untouched."
    arm_sub "Check the network and ARM_IMAGE_TAG in ${ENV_FILE}, then run the command again."
    exit 1
}

# Remove what the backend spawned, start from the pulled images, and bring the
# rippers back. Everything before this point leaves the running stack alone.
go_live() {
    local started_before
    started_before="$(backend_started_at)"
    remove_spawned_containers
    remove_retired_services
    arm_say "starting the stack"
    if [[ ${#UP_SERVICES[@]} -gt 0 ]]; then
        compose up -d --no-build "${UP_SERVICES[@]}"
    else
        compose up -d --no-build
    fi
    respawn_rippers_if_needed "${started_before}"
}

# Same order as devtools/setup-dev.sh `up`, with a pull in place of the build.
stack_up() {
    select_up_services
    pull_images
    verify_images_present
    guard_running_spawned
    refresh_arm_gpus
    backup_db
    go_live
}

finish_up() {
    local ui_url
    wait_for_backend
    ui_url="$(published_url "${UI_SERVICE}" 443)"
    ui_url="${ui_url:-https://localhost:8081}"
    arm_say "stack is up; ${HEALTH_RESULT}"
    arm_say "open ${ui_url}"
}

cmd_up() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force)     FORCE=1 ;;
            --no-backup) NO_BACKUP=1 ;;
            --no-pull)   NO_PULL=1 ;;
            *) arm_err "unknown option for up: $1"; exit 2 ;;
        esac
        shift
    done
    require_installed
    load_profile
    ARM_HINT_FORCE_CMD="${ARMCTL_CMD} up --force"
    ARM_HINT_IMAGES_READY="Images are pulled"
    stack_up
    finish_up
}

cmd_down() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force) FORCE=1 ;;
            *) arm_err "unknown option for down: $1"; exit 2 ;;
        esac
        shift
    done
    require_installed
    ARM_HINT_FORCE_CMD="${ARMCTL_CMD} down --force"
    ARM_HINT_IMAGES_READY="The stack is still running"
    guard_running_spawned
    remove_spawned_containers
    remove_retired_services
    arm_say "stopping the stack"
    compose down
}

armctl_main() {
    local cmd="${1:-help}"
    if [[ $# -gt 0 ]]; then
        shift
    fi
    case "${cmd}" in
        -h|--help|help) armctl_usage; return 0 ;;
    esac
    refuse_root
    armctl_settings
    ARMCTL_ARGV=("${cmd}" "$@")
    case "${cmd}" in
        up)      require_docker_ready; acquire_lock; cmd_up "$@" ;;
        down)    require_docker_ready; acquire_lock; cmd_down "$@" ;;
        compose) require_docker_ready; require_installed; compose "$@" ;;
        *)       arm_err "unknown command: ${cmd}"; armctl_usage >&2; exit 2 ;;
    esac
}

# Test seam: lets deploy/tests/test-armctl.sh source the functions above
# without running a command. The sourced-ness check makes a leaked env var
# harmless when the script is executed.
[[ -n "${ARMCTL_SOURCE_ONLY:-}" && "${BASH_SOURCE[0]}" != "$0" ]] && return 0

armctl_main "$@"
