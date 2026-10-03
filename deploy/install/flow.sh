#!/usr/bin/env bash
# shellcheck disable=SC2034 # the flag values assigned here are read by the other modules
# deploy/install/flow.sh: `armctl install`, the staged install.
# Sourced by deploy/armctl.sh after every other module.

install_usage() {
    cat <<'USAGE'
Usage: armctl install [options]

Run with no options to be asked. Every question has a flag, so an install
can also run unattended.

  --profile <full|ripper-only|offload>
                          full: rip and transcode on this host (default)
                          ripper-only: rip here, never transcode here
                          offload: rip here, transcode on another host over ssh
  --raw-path <dir>        folder for raw rips (default: <arm>/raw)
  --media-path <dir>      folder for finished media (default: <arm>/media)
  --yes                   accept every host change: Docker, the NVIDIA toolkit,
                          the udev rule, the armctl link in /usr/local/bin
  --no-host-changes       decline every host change
  --no-start              configure only; do not start the stack
  --rotate-ca             replace the CA and every certificate
  --image-prefix <registry/namespace>
                          pull images from another registry (forks)
  --release-repo <owner/repo>
                          GitHub repo that `armctl upgrade` takes releases from

  Offload profile, for an unattended install:
  --offload-host <ssh://user@host[:port]>
  --offload-backend-url <https://host:port>
  --offload-uidgid <uid:gid>
USAGE
}

# The folders the stack expects. raw/ and media/ are created by choose_storage
# because they may live elsewhere.
ensure_layout() {
    mkdir -p "${ARM_DIR}"/{certs,db,logs,backups,scripts,iso-library} "${ARM_STATE_DIR}" || return 1
    chmod 700 "${ARM_DIR}/certs" "${ARM_STATE_DIR}" || return 1
    # setgid + group-writable: files ARM creates inherit the folder's group.
    chmod 2775 "${ARM_DIR}/logs" || return 1
}

# The host-wide rule that stops a desktop session auto-mounting discs, which
# makes eject fail after a rip. Writing it needs sudo, so it needs consent.
install_udev_rule() {
    if ! command -v udevadm >/dev/null 2>&1; then
        log "udevadm not found; skipping the disc auto-mount rule"
        return 0
    fi
    if udev_rule_current; then
        okline "disc auto-mount rule already in place"
        return 0
    fi
    if consent "udev rule" "Write a udev rule so the desktop stops auto-mounting discs ARM is ripping (needs sudo)?"; then
        # Ask for the sudo password now, so ensure_udev_rule's non-interactive
        # check passes. Without a terminal this fails and ensure_udev_rule
        # prints the commands to run by hand.
        sudo -v || true
        ensure_udev_rule
    else
        warnline "without the rule, a desktop session can hold the disc and block eject after a rip"
    fi
}

print_install_summary() {  # print_install_summary <started 0|1>
    local started="$1" s
    printf '\n'
    if [[ "${started}" -eq 1 ]]; then
        log "ARM is running. Open https://localhost:8081 and follow the setup walkthrough."
    else
        log "ARM is configured but not started. Start it with: ${ARMCTL_CMD} up"
    fi
    log "First-login credentials (you will be asked to change the password):"
    log "  docker exec armv3-backend cat /logs/first-boot.log"
    log "To stop the browser's certificate warning, import ${ARM_CERTS_DIR}/arm-ca.crt"
    log "into your browser or OS trust store."
    log "Everyday commands: ${ARMCTL_CMD} up | down | upgrade | compose ps"
    if [[ ${#SKIPPED[@]} -gt 0 ]]; then
        printf '\n'
        warnline "skipped during this install:"
        for s in "${SKIPPED[@]}"; do
            log "  ${s}"
        done
        log "Run '${ARMCTL_CMD} install' again to revisit them."
    fi
}

cmd_install() {
    local start=1 rotate_ca=0 release_repo="" backend_san args=() a
    OFFLOAD_HOST_ARG=""; OFFLOAD_URL_ARG=""; OFFLOAD_UIDGID_ARG=""
    REMOTE_OFFLOAD=0; REMOTE_DOCKER_HOST=""; REMOTE_BACKEND_URL=""; REMOTE_BACKEND_SAN=""
    REMOTE_TRANSCODE_PUID=""; REMOTE_TRANSCODE_PGID=""; REMOTE_GPUS=""; REMOTE_RENDER_GID=""

    # Accept --key=value as well as --key value.
    for a in "$@"; do
        if [[ "${a}" == --*=* ]]; then
            args+=("${a%%=*}" "${a#*=}")
        else
            args+=("${a}")
        fi
    done
    set -- "${args[@]+"${args[@]}"}"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --profile|--raw-path|--media-path|--image-prefix|--release-repo|--offload-host|--offload-backend-url|--offload-uidgid)
                [[ $# -ge 2 ]] || err "$1 needs a value"
                case "$1" in
                    --profile)             PROFILE_ARG="$2" ;;
                    --raw-path)            RAW_ARG="$2" ;;
                    --media-path)          MEDIA_ARG="$2" ;;
                    --image-prefix)        IMAGE_PREFIX_ARG="$2" ;;
                    --release-repo)        release_repo="$2" ;;
                    --offload-host)        OFFLOAD_HOST_ARG="$2" ;;
                    --offload-backend-url) OFFLOAD_URL_ARG="$2" ;;
                    --offload-uidgid)      OFFLOAD_UIDGID_ARG="$2" ;;
                esac
                shift 2 ;;
            --yes)             ARMCTL_ASSUME=yes; shift ;;
            --no-host-changes) ARMCTL_ASSUME=no; shift ;;
            --no-start)        start=0; shift ;;
            --rotate-ca)       rotate_ca=1; shift ;;
            -h|--help)         install_usage; return 0 ;;
            *) err "unknown option for install: $1 (see: ${ARMCTL_CMD} install --help)" ;;
        esac
    done

    ARM_IMAGE_TAG_DEFAULT="$(cat "${ARMCTL_RELEASE_DIR}/VERSION" 2>/dev/null || true)"
    [[ -n "${ARM_IMAGE_TAG_DEFAULT}" ]] \
        || err "this release bundle has no VERSION file; download the installer again"

    STEP=0; STEP_TOTAL=8
    step "Profile"
    choose_profile
    # ensure_docker may restart this command under the docker group; carry the
    # answer across so the question is not asked twice.
    if [[ -z "${PROFILE_ARG}" ]]; then
        ARMCTL_ARGV+=(--profile "${PROFILE}")
    fi

    step "Host"
    ensure_docker
    acquire_lock
    require openssl "openssl is needed to generate certificates and secrets; install it and run the installer again"
    ensure_layout

    step "Storage"
    choose_storage

    step "Remote transcode offload"
    if [[ "${PROFILE}" == offload ]]; then
        setup_remote_offload
    else
        log "not used by the ${PROFILE} profile"
    fi

    step "Certificates"
    if [[ "${rotate_ca}" -eq 1 ]]; then
        warnline "--rotate-ca replaces the CA: every browser and device that trusted the old one must import the new arm-ca.crt"
        if [[ "${ARMCTL_ASSUME}" != yes ]]; then
            confirm "Replace the CA?" || err "kept the existing CA; nothing was changed"
        fi
        rm -f "${ARM_CERTS_DIR}/arm-ca.key" "${ARM_CERTS_DIR}/arm-ca.crt"
    fi
    ensure_ca
    # With offload, the remote transcoder verifies the backend's certificate
    # against the address it calls back on, so that address must be a SAN.
    backend_san="${REMOTE_BACKEND_SAN:-}"
    if [[ -n "${backend_san}" ]]; then
        make_leaf arm-backend "${backend_san}"
    else
        make_leaf arm-backend
    fi
    make_leaf arm-db
    make_leaf arm-ui localhost "$(hostname -f 2>/dev/null || hostname || echo localhost)"

    step "Configuration"
    write_env
    if [[ -n "${release_repo}" ]]; then
        env_set ARMCTL_RELEASE_REPO "${release_repo}"
    fi
    write_host_overlay
    if [[ "${PROFILE}" == full ]]; then
        ensure_nvidia_container_toolkit
    fi
    install_udev_rule
    link_armctl

    step "Start"
    if [[ "${start}" -eq 1 ]]; then
        stack_up
        finish_up
    else
        log "not starting the stack (--no-start)"
    fi

    step "Finish"
    if offload_persisted; then
        if [[ -z "${REMOTE_RUN+x}" ]]; then
            offload_remote_run_init "$(env_file_value ARM_TRANSCODE_DOCKER_HOST)" \
                "${ARM_DIR}/ssh/id_ed25519" "${ARM_DIR}/ssh/known_hosts"
        fi
        offload_completion_report
    fi
    print_install_summary "${start}"
}
