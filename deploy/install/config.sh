#!/usr/bin/env bash
# shellcheck disable=SC2034 # the answers assigned here are read by other sourced modules
# deploy/install/config.sh: profile, storage locations, .env, image pins and
# the generated host overlay. Sourced by deploy/armctl.sh; needs deploy/lib/*
# and deploy/install/ui.sh loaded first.

ARM_IMAGE_PREFIX_DEFAULT="docker.io/automaticrippingmachine"
# The release this run pins. The install flow sets it from the bundle's VERSION.
ARM_IMAGE_TAG_DEFAULT=""

# Answers from flags (empty = not given) and the resolved answers.
PROFILE_ARG=""
RAW_ARG=""
MEDIA_ARG=""
IMAGE_PREFIX_ARG=""
RAW_PATH=""
MEDIA_PATH=""

valid_profile() {
    [[ "$1" == full || "$1" == ripper-only || "$1" == offload ]]
}

# Sets PROFILE and RIPPER_ONLY. Order: the --profile flag, then (with no
# terminal) the saved profile or `full`, then a prompt defaulting to the saved
# profile.
choose_profile() {
    local saved reply def
    saved="$(env_file_value ARMCTL_PROFILE)"
    if [[ -n "${PROFILE_ARG}" ]]; then
        valid_profile "${PROFILE_ARG}" || err "--profile must be full, ripper-only or offload (got '${PROFILE_ARG}')"
        PROFILE="${PROFILE_ARG}"
    elif [[ ! -t 0 ]]; then
        PROFILE="${saved:-full}"
    else
        def="${saved:-full}"
        printf '  How will this host be used?\n'
        printf '    1) full         rip and transcode on this host\n'
        printf '    2) ripper-only  rip here, never transcode here\n'
        printf '    3) offload      rip here, transcode on another host over ssh\n'
        while true; do
            read -rp "  Choice [${def}]: " reply
            case "${reply:-${def}}" in
                1|full)        PROFILE=full; break ;;
                2|ripper-only) PROFILE=ripper-only; break ;;
                3|offload)     PROFILE=offload; break ;;
                *) printf '    ! enter 1, 2 or 3\n' >&2 ;;
            esac
        done
    fi
    RIPPER_ONLY=0
    if [[ "${PROFILE}" == ripper-only ]]; then
        RIPPER_ONLY=1
    fi
    okline "profile: ${PROFILE}"
}

# A storage folder must be a full path, and free of the characters that the
# overlay's "host:container" mount syntax or an unquoted .env value cannot
# carry. Spaces are fine.
valid_storage_path() {
    [[ "$1" == /* ]] || return 1
    case "$1" in
        *$'\n'*|*:*|*\"*|*\$*|*\#*|*\\*|*\'*) return 1 ;;
    esac
    return 0
}

# pick_storage <label> <flag value> <env key> <default>: print the folder to
# use. Order: the flag, then (with no terminal) the saved answer or the
# default, then a prompt.
pick_storage() {
    local label="$1" arg="$2" key="$3" def="$4" saved reply
    saved="$(env_file_value "${key}")"
    # .env.example ships these keys as ${PWD}/arm/...; that is not an answer.
    if [[ "${saved}" != /* ]]; then
        saved=""
    fi
    def="${saved:-${def}}"
    if [[ -n "${arg}" ]]; then
        valid_storage_path "${arg}" \
            || err "the folder for ${label} must be a full path starting with / and without : \" \$ # \\ or quote characters (got '${arg}')"
        printf '%s' "${arg}"
        return 0
    fi
    if [[ ! -t 0 ]]; then
        printf '%s' "${def}"
        return 0
    fi
    while true; do
        read -rp "  Folder for ${label} [${def}]: " reply
        reply="${reply:-${def}}"
        if valid_storage_path "${reply}"; then
            printf '%s' "${reply}"
            return 0
        fi
        printf '    ! enter a full path starting with / and without : " $ # \\ or quote characters\n' >&2
    done
}

# Create the folder if needed and make sure this user can write to it. Folders
# inside the arm folder get the setgid, group-writable mode the stack expects;
# a folder the user pointed us at elsewhere is theirs, so its mode is left alone.
prepare_storage() {
    local dir="$1"
    if [[ ! -d "${dir}" ]]; then
        mkdir -p "${dir}" 2>/dev/null \
            || err "cannot create ${dir}. Create it yourself, writable by $(id -un), then run the installer again."
    fi
    [[ -w "${dir}" ]] \
        || err "${dir} is not writable by $(id -un). Fix its ownership or choose another folder, then run the installer again."
    if [[ "${dir}" == "${ARM_DIR}/"* ]]; then
        chmod 2775 "${dir}"
    fi
}

choose_storage() {
    RAW_PATH="$(pick_storage "raw rips" "${RAW_ARG}" ARM_HOST_RAW_PATH "${ARM_DIR}/raw")"
    MEDIA_PATH="$(pick_storage "finished media" "${MEDIA_ARG}" ARM_HOST_MEDIA_PATH "${ARM_DIR}/media")"
    prepare_storage "${RAW_PATH}"
    prepare_storage "${MEDIA_PATH}"
    okline "raw rips:       ${RAW_PATH}"
    okline "finished media: ${MEDIA_PATH}"
}

# env_merge_new_keys <example> <env>: append every KEY=value line of the
# example whose key the env file does not have yet. This is how a setting
# introduced by a newer release gets its default on re-run and on upgrade.
env_merge_new_keys() {
    local example="$1" env="$2" line key
    while IFS= read -r line; do
        [[ "${line}" =~ ^[A-Z][A-Z0-9_]*= ]] || continue
        key="${line%%=*}"
        if ! grep -q "^${key}=" "${env}"; then
            printf '%s\n' "${line}" >> "${env}"
        fi
    done < "${example}"
}

# write_image_pins <tag> [env file]: pin every image to one release. The
# backend, data-init and UI images come from ARM_IMAGE_PREFIX/ARM_IMAGE_TAG
# through docker-compose.release.yml; the ripper and transcode images are
# variables the compose template already reads.
write_image_pins() {
    local tag="$1" file="${2:-${ENV_FILE}}" prefix
    [[ -n "${tag}" ]] || err "no release version to pin the images to"
    prefix="${IMAGE_PREFIX_ARG:-}"
    if [[ -z "${prefix}" ]]; then
        prefix="$(sed -nE 's/^ARM_IMAGE_PREFIX=(.+)$/\1/p' "${file}" 2>/dev/null | tail -n1)"
    fi
    prefix="${prefix:-${ARM_IMAGE_PREFIX_DEFAULT}}"
    env_set ARM_IMAGE_PREFIX "${prefix}" "${file}"
    env_set ARM_IMAGE_TAG "${tag}" "${file}"
    env_set ARM_RIPPER_IMAGE "${prefix}/arm-ripper:${tag}" "${file}"
    env_set ARM_TRANSCODE_IMAGE "${prefix}/arm-transcode:${tag}" "${file}"
    env_set ARM_TRANSCODE_IMAGE_QSV "${prefix}/arm-transcode:${tag}-intel" "${file}"
    env_set ARM_TRANSCODE_IMAGE_VAAPI "${prefix}/arm-transcode:${tag}-amd" "${file}"
}

# Write ENV_FILE from the bundle's .env.example. Secrets are generated once
# and kept on every later run; everything detected or answered is rewritten.
write_env() {
    local example="${ARMCTL_RELEASE_DIR}/.env.example" key
    if [[ -f "${ENV_FILE}" ]]; then
        log ".env exists; keeping its secrets and refreshing detected values"
        env_merge_new_keys "${example}" "${ENV_FILE}"
    else
        log "generating .env with random secrets"
        mkdir -p "$(dirname "${ENV_FILE}")"
        sed \
            -e "s|change-me-openssl-rand-hex-24|$(openssl rand -hex 24)|" \
            -e "s|change-me-openssl-rand-hex-32|$(openssl rand -hex 32)|" \
            "${example}" > "${ENV_FILE}"
        chmod 600 "${ENV_FILE}"
    fi

    env_set PUID "$(id -u)"
    env_set PGID "$(id -g)"
    env_set CDROM_GID "$(detect_cdrom_gid)"
    env_set ARMCTL_PROFILE "${PROFILE}"
    # The template defaults these from ${PWD}, the folder compose was started
    # in. armctl can be run from anywhere, so they are always written in full.
    env_set ARM_HOST_RAW_PATH "${RAW_PATH}"
    env_set ARM_HOST_MEDIA_PATH "${MEDIA_PATH}"
    env_set ARM_HOST_LOGS_PATH "${ARM_DIR}/logs"
    if [[ -z "$(env_file_value ARM_ALLOWED_ORIGINS)" ]]; then
        env_set ARM_ALLOWED_ORIGINS "https://localhost:8081"
    fi
    write_image_pins "${ARM_IMAGE_TAG_DEFAULT}"

    if [[ "${PROFILE}" == ripper-only ]]; then
        env_set ARM_TRANSCODE_CAPABLE false
    else
        env_set ARM_TRANSCODE_CAPABLE true
    fi

    if [[ "${PROFILE}" == offload ]]; then
        env_set ARM_TRANSCODE_DOCKER_HOST "${REMOTE_DOCKER_HOST}"
        env_set ARM_TRANSCODE_BACKEND_URL "${REMOTE_BACKEND_URL}"
        env_set ARM_TRANSCODE_PUID "${REMOTE_TRANSCODE_PUID}"
        env_set ARM_TRANSCODE_PGID "${REMOTE_TRANSCODE_PGID}"
        env_set ARM_TRANSCODE_SSH_DIR "${ARM_DIR}/ssh"
        # Transcoders run on the remote daemon and mount certs from ITS path;
        # rippers run on this host and need the local folder.
        env_set ARM_HOST_CERTS_PATH "$(offload_certs_path "${REMOTE_DOCKER_HOST}")"
        env_set ARM_RIPPER_CERTS_PATH "${ARM_DIR}/certs"
        env_set ARM_GPUS "${REMOTE_GPUS:-[]}"
        env_set ARM_RENDER_GID "${REMOTE_RENDER_GID:-}"
    else
        for key in ARM_TRANSCODE_DOCKER_HOST ARM_TRANSCODE_BACKEND_URL ARM_TRANSCODE_PUID \
                   ARM_TRANSCODE_PGID ARM_TRANSCODE_SSH_DIR ARM_RIPPER_CERTS_PATH; do
            env_unset "${key}"
        done
        env_set ARM_HOST_CERTS_PATH "${ARM_DIR}/certs"
        refresh_arm_gpus
        env_set ARM_RENDER_GID "$(detect_render_gid || true)"
    fi
}

# The per-install compose overlay: where raw rips and finished media live,
# and, for offload, the ssh folder and the published callback port. It is
# rewritten in full each time, so a changed answer never leaves a stale entry.
# Compose replaces a template mount that targets the same container path.
write_host_overlay() {
    local tmp="${HOST_OVERLAY}.tmp"
    mkdir -p "$(dirname "${HOST_OVERLAY}")"
    {
        # shellcheck disable=SC2016 # backticks are literal text in the comment
        printf '# Generated by armctl install. Do not edit; run `armctl install` again to change it.\n'
        printf 'services:\n'
        printf '  arm-backend:\n'
        printf '    volumes:\n'
        printf '      - "%s:/raw"\n' "${RAW_PATH}"
        printf '      - "%s:/media"\n' "${MEDIA_PATH}"
        if [[ "${PROFILE}" == offload ]]; then
            printf '      - "%s:/home/arm/.ssh:ro"\n' "${ARM_DIR}/ssh"
            printf '    ports:\n'
            printf '      - "%s:8443"\n' "$(offload_backend_port "${REMOTE_BACKEND_URL}")"
        fi
    } > "${tmp}"
    mv "${tmp}" "${HOST_OVERLAY}"
}
