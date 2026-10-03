#!/usr/bin/env bash
# deploy/install/docker.sh: Docker diagnosis and setup.
# Sourced by deploy/armctl.sh; needs deploy/install/ui.sh loaded first.
#
# `armctl install` fixes what it can (ensure_docker), with consent. Every
# other command only checks (require_docker_ready), except that it restarts
# itself under the docker group when the only problem is a login session that
# predates the user's membership.

OS_RELEASE_FILE="${OS_RELEASE_FILE:-/etc/os-release}"
DOCKER_DOCS_URL="https://docs.docker.com/engine/install/"

# Only Debian and Ubuntu themselves are automated. A derivative (Mint, Pop!_OS)
# has its own release codenames, which Docker's apt repository does not carry,
# so it is treated like any other distro: a link, no automation.
os_family() {
    local id=""
    if [[ -r "${OS_RELEASE_FILE}" ]]; then
        id="$(sed -nE 's/^ID=//p' "${OS_RELEASE_FILE}" | tr -d '"' | head -n 1)"
    fi
    case "${id}" in
        debian|ubuntu) printf '%s' "${id}" ;;
        *)             printf 'other' ;;
    esac
}

os_codename() {
    [[ -r "${OS_RELEASE_FILE}" ]] || return 0
    sed -nE 's/^VERSION_CODENAME=//p' "${OS_RELEASE_FILE}" | tr -d '"' | head -n 1
}

# Print one of: ok | missing | old:<version> | no-compose | daemon-down | no-group
docker_state() {
    local ver info_err
    if ! command -v docker >/dev/null 2>&1; then
        printf 'missing'; return 0
    fi
    ver="$(docker --version 2>/dev/null | sed -E 's/^Docker version ([0-9.]+).*/\1/')"
    if [[ -z "${ver}" ]] || ! vercmp_ge "${ver}" "24.0.0"; then
        printf 'old:%s' "${ver:-unknown}"; return 0
    fi
    if ! docker compose version >/dev/null 2>&1; then
        printf 'no-compose'; return 0
    fi
    if info_err="$(docker info 2>&1 >/dev/null)"; then
        printf 'ok'; return 0
    fi
    if [[ "${info_err}" == *"permission denied"* ]]; then
        printf 'no-group'
    else
        printf 'daemon-down'
    fi
}

# True when the group database lists this user in `docker`, whatever groups
# the current login session happens to have.
user_in_docker_group_file() {
    local members
    members="$(getent group docker | cut -d: -f4)"
    [[ ",${members}," == *",$(id -un),"* ]]
}

# Its own function so tests can replace it: `exec` cannot be stubbed.
run_sg_exec() {
    exec sg docker -c "$1"
}

relogin_needed() {
    arm_err "this login session cannot use Docker yet."
    arm_sub "Your user is in the docker group, but that only applies to new logins."
    arm_sub "Log out and back in (or reboot), then run: ${ARMCTL_CMD} ${ARMCTL_ARGV[*]}"
    exit 1
}

# Restart this armctl command under the docker group, once. ARMCTL_SG_REEXEC
# marks the restarted process so a restart that did not help cannot loop.
reexec_under_docker_group() {
    local cmd
    if [[ -n "${ARMCTL_SG_REEXEC:-}" ]]; then
        relogin_needed
    fi
    if command -v sg >/dev/null 2>&1 && user_in_docker_group_file && sg docker -c true >/dev/null 2>&1; then
        log "restarting under the docker group (this login predates your membership)"
        printf -v cmd '%q ' "${ARMCTL_CMD}" "${ARMCTL_ARGV[@]}"
        run_sg_exec "ARMCTL_SG_REEXEC=1 ${cmd}"
    fi
    relogin_needed
}

# Docker's own apt repository steps, for Debian and Ubuntu.
docker_apt_install() {
    local family="$1" codename arch
    codename="$(os_codename)"
    [[ -n "${codename}" ]] \
        || err "cannot read this system's release codename from ${OS_RELEASE_FILE}. Install Docker by hand: ${DOCKER_DOCS_URL}"
    arch="$(dpkg --print-architecture)"
    log "installing Docker Engine and the compose plugin from download.docker.com (sudo)"
    sudo apt-get update || err "Docker install failed at: sudo step. See ${DOCKER_DOCS_URL}"
    sudo apt-get install -y ca-certificates curl || err "Docker install failed at: sudo step. See ${DOCKER_DOCS_URL}"
    sudo install -m 0755 -d /etc/apt/keyrings || err "Docker install failed at: sudo step. See ${DOCKER_DOCS_URL}"
    sudo curl -fsSL "https://download.docker.com/linux/${family}/gpg" -o /etc/apt/keyrings/docker.asc || err "Docker install failed at: sudo step. See ${DOCKER_DOCS_URL}"
    sudo chmod a+r /etc/apt/keyrings/docker.asc || err "Docker install failed at: sudo step. See ${DOCKER_DOCS_URL}"
    printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/%s %s stable\n' \
        "${arch}" "${family}" "${codename}" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null \
        || err "Docker install failed writing the apt source. See ${DOCKER_DOCS_URL}"
    sudo apt-get update || err "Docker install failed at: sudo step. See ${DOCKER_DOCS_URL}"
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin || err "Docker install failed at: sudo step. See ${DOCKER_DOCS_URL}"
}

fix_docker_group() {
    local me
    me="$(id -un)"
    if ! user_in_docker_group_file; then
        consent "docker group" "Add ${me} to the docker group so ARM can use Docker without sudo (needs sudo)?" \
            || err "ARM needs ${me} to be in the docker group. Add it with: sudo usermod -aG docker ${me}"
        sudo usermod -aG docker "${me}" || err "could not add ${me} to the docker group"
    fi
    reexec_under_docker_group
}

# Install-time: diagnose Docker and fix what can be fixed, each fix with consent.
ensure_docker() {
    local state family
    state="$(docker_state)"
    case "${state}" in
        ok)
            okline "Docker is ready"
            return 0 ;;
        no-group)
            fix_docker_group ;;
        daemon-down)
            failline "Docker is installed but its service is not running"
            consent "start Docker" "Start the Docker service now (needs sudo)?" \
                || err "Docker must be running. Start it with: sudo systemctl enable --now docker"
            sudo systemctl enable --now docker || err "could not start Docker" ;;
        missing|old:*|no-compose)
            case "${state}" in
                missing)    failline "Docker is not installed" ;;
                old:*)      failline "Docker ${state#old:} is too old (ARM needs Engine 24 or newer)" ;;
                no-compose) failline "the Docker Compose v2 plugin is missing" ;;
            esac
            family="$(os_family)"
            if [[ "${family}" == other ]]; then
                err "this installer sets Docker up only on Debian and Ubuntu. Install Docker Engine 24 or newer with the compose plugin for your distro (${DOCKER_DOCS_URL}), then run the installer again."
            fi
            consent "install Docker" "Install Docker Engine and the compose plugin from Docker's apt repository (needs sudo; replaces the distro's docker.io package if present)?" \
                || err "ARM needs Docker Engine 24 or newer with the compose plugin. Install it (${DOCKER_DOCS_URL}), then run the installer again."
            docker_apt_install "${family}" ;;
    esac
    state="$(docker_state)"
    case "${state}" in
        ok)       okline "Docker is ready" ;;
        no-group) fix_docker_group ;;
        *)        err "Docker is still not usable (${state}). See ${DOCKER_DOCS_URL}" ;;
    esac
}

# Every command other than install: check, never change the host.
require_docker_ready() {
    local state
    state="$(docker_state)"
    case "${state}" in
        ok) return 0 ;;
        no-group)
            if user_in_docker_group_file; then
                reexec_under_docker_group
            fi
            arm_err "your user cannot use Docker. Run: ${ARMCTL_CMD} install"
            exit 1 ;;
        *)
            arm_err "Docker is not usable (${state}). Run: ${ARMCTL_CMD} install"
            exit 1 ;;
    esac
}
