#!/usr/bin/env bash
# deploy/lib/selinux.sh: SELinux labels for the stack's bind mounts.
# Shared by devtools/setup-dev.sh and deploy/armctl.sh. Sourced, never executed.
# Needs deploy/lib/common.sh loaded first.
#
# Callers set, before calling anything here:
#   ARM_DIR           the ARM data folder (dev: <repo>/arm, production: ~/arm)
#   ENV_FILE          path of the stack's .env (ARM_SELINUX_LABELS is read there)
#   plus what common.sh's `compose` needs.
#
# On a host whose Docker daemon labels containers (Fedora, RHEL and their
# rebuilds), a container may only open a bind-mounted host path whose SELinux
# type is container_file_t. A matching owner is not enough: the entrypoint's
# write check then fails with "dir owner is 1000:1000" on a folder owned
# 1000:1000, and a world-readable certificate fails with [Errno 13]. A container
# that mounts the Docker socket cannot reach it under a label at all.
#
# write_selinux_overlay reads the resolved compose config and writes an overlay
# that, per bind mount:
#   - a socket (the Docker socket): runs that service with `label=disable`. A
#     container that drives the Docker socket can start a privileged container
#     anyway, so a label would not confine it.
#   - a file or folder inside ARM_DIR: adds `selinux: z` (the long form of
#     `:z`), so Docker gives it the shared container label when it creates the
#     container. Everything in ARM_DIR is ARM's own.
#   - anything else (a NAS share, a media library, an ISO folder elsewhere):
#     left alone, like ownership (06-deployment.md: ARM never changes a user's
#     folders). Relabelling would replace a label something else may rely on,
#     such as a Samba share's. When its label would block the containers, the
#     run prints the command that fixes it.
# Compose merges an overlay's mounts into the template's by target path, so the
# overlay restates each mount's source, mode and create_host_path and adds the
# label. With nothing to label it is `services: {}` and changes nothing.
#
# ARM_SELINUX_LABELS in .env: auto (default; follow `docker info`), on, off.

SELINUX_OVERLAY_EMPTY='services: {}'

# Filesystems that keep no per-file SELinux label: Docker cannot relabel a path
# on them, and asking it to (`:z`) makes container creation fail.
selinux_unlabelled_fs() {
    case "$1" in
        nfs*|cifs|smb*|fuse*|msdos|vfat|exfat|v9fs|9p|ntfs*|autofs) return 0 ;;
    esac
    return 1
}

# Probes, one function each so the tests can replace them.
selinux_fs_type()    { stat -f -c '%T' -- "$1" 2>/dev/null || true; }
# The SELinux type of a path (e.g. container_file_t), or nothing when the host
# keeps no labels.
selinux_label_type() {
    local ctx
    ctx="$(stat -c '%C' -- "$1" 2>/dev/null || true)"
    [[ "${ctx}" == *:*:*:* ]] || return 0
    cut -d: -f3 <<<"${ctx}"
}
selinux_is_socket()  { [[ -S "$1" ]]; }
selinux_bool_on()    { [[ "$(getsebool "$1" 2>/dev/null)" == *"--> on" ]]; }
# True when Docker labels the containers it starts.
docker_labels_containers() {
    local opts
    opts="$(docker info --format '{{json .SecurityOptions}}' 2>/dev/null)" || return 1
    [[ "${opts}" == *name=selinux* ]]
}

selinux_labels_mode() {
    local mode
    mode="$(env_file_value ARM_SELINUX_LABELS)"
    case "${mode}" in
        ""|auto) echo auto ;;
        on|off)  echo "${mode}" ;;
        *) arm_warn "ignoring ARM_SELINUX_LABELS='${mode}' (use auto, on or off)"; echo auto ;;
    esac
}

# True when this run should write a labelling overlay.
selinux_labels_needed() {
    case "$(selinux_labels_mode)" in
        on)  return 0 ;;
        off) return 1 ;;
    esac
    docker_labels_containers
}

# ensure_selinux_overlay_file <path>: create an empty overlay if none exists,
# so a compose file list that names it stays valid.
ensure_selinux_overlay_file() {
    [[ -f "$1" ]] || printf '%s\n' "${SELINUX_OVERLAY_EMPTY}" > "$1"
}

# selinux_compose_files <COMPOSE_FILE> <separator> <overlay name> <override 0|1>:
# print the COMPOSE_FILE list setup-dev.sh keeps in .env while it names the
# overlay. Setting COMPOSE_FILE stops compose from loading
# docker-compose.override.yml by itself, so the list stands in for that: the
# override is added when the file exists (the last argument is 1) and dropped
# when it does not. The list starts from compose's default when empty, keeps
# every other entry in its order, and ends with the overlay, so its labels
# cover the mounts of every file before it.
selinux_compose_files() {
    local current="$1" sep="$2" overlay="$3" override="$4" f out="" listed=0
    local -a files=()
    IFS="${sep}" read -r -a files <<<"${current}"
    for f in "${files[@]}"; do
        [[ -n "${f}" && "${f}" != "${overlay}" ]] || continue
        if [[ "${f}" == docker-compose.override.yml ]]; then
            [[ "${override}" -eq 1 ]] || continue
            listed=1
        fi
        out+="${out:+${sep}}${f}"
    done
    [[ -n "${out}" ]] || out="docker-compose.yml"
    if [[ "${override}" -eq 1 && "${listed}" -eq 0 ]]; then
        out+="${sep}docker-compose.override.yml"
    fi
    printf '%s%s%s\n' "${out}" "${sep}" "${overlay}"
}

# The bind mounts of a `docker compose config` document on stdin, one per line:
# service <TAB> target <TAB> read_only (0|1) <TAB> create_host_path (0|1) <TAB>
# source. Compose prints every mount in the long form, fields at fixed indents;
# a quoted value is unquoted.
selinux_bind_mounts() {
    awk '
        function unq(v) {
            if (v ~ /^".*"$/) { v = substr(v, 2, length(v) - 2); gsub(/\\"/, "\"", v); gsub(/\\\\/, "\\", v) }
            else if (v ~ /^\047.*\047$/) { v = substr(v, 2, length(v) - 2); gsub(/\047\047/, "\047", v) }
            return v
        }
        function flush() {
            if (type == "bind" && src != "" && tgt != "") printf "%s\t%s\t%d\t%d\t%s\n", svc, tgt, ro, chp, src
            type = ""; src = ""; tgt = ""; ro = 0; chp = 0
        }
        /^[^ ]/            { flush(); insvc = ($0 == "services:"); invol = 0; next }
        !insvc             { next }
        /^  [^ ]/          { flush(); svc = $0; sub(/^  /, "", svc); sub(/:$/, "", svc); invol = 0; next }
        /^    [^ ]/        { flush(); invol = ($0 == "    volumes:"); next }
        !invol             { next }
        /^      - /        { flush(); line = $0; sub(/^      - /, "        ", line); $0 = line }
        /^        [a-z_]+:/ {
            key = $0; sub(/^        /, "", key); val = key
            sub(/:.*$/, "", key); sub(/^[a-z_]+: */, "", val)
            if (key == "type") type = val
            else if (key == "source") src = unq(val)
            else if (key == "target") tgt = unq(val)
            else if (key == "read_only") ro = (val == "true")
        }
        /^          create_host_path: true$/ { chp = 1 }
        END { flush() }
    '
}

selinux_yaml_quote() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    printf '"%s"' "${s}"
}

# selinux_hint <path> <fs type> <label type> <inside ARM_DIR 0|1>: warn about a
# mount whose label would block the containers, with the command that fixes it.
selinux_hint() {
    local path="$1" fs="$2" label="$3" inside="$4" bool=""
    if selinux_unlabelled_fs "${fs}"; then
        case "${fs}" in
            nfs*)       bool=virt_use_nfs ;;
            cifs|smb*)  bool=virt_use_samba ;;
            fuse*)      bool=virt_use_fusefs ;;
        esac
        if [[ -n "${bool}" ]]; then
            selinux_bool_on "${bool}" && return 0
            arm_warn "SELinux: ${path} is on ${fs}, which has no per-file labels, so containers cannot use it yet."
            arm_sub  "       Allow containers on ${fs} once with: sudo setsebool -P ${bool} 1"
        else
            arm_warn "SELinux: ${path} is on ${fs}, which has no per-file labels, so containers cannot use it."
            arm_sub  "       Mount it with context=\"system_u:object_r:container_file_t:s0\", or move it to a Linux filesystem."
        fi
        return 0
    fi
    [[ "${inside}" -eq 1 ]] && return 0
    arm_warn "SELinux: ${path} is labelled ${label}, which containers cannot use. It is outside ${ARM_DIR}, so ARM leaves its label alone."
    arm_sub  "       To give it to ARM: sudo chcon -R -t container_file_t '${path}'"
    arm_sub  "       That replaces its current label; check first that nothing else on this host relies on ${label}."
}

# selinux_overlay_from_config <writer>: read a `docker compose config` document
# on stdin, print the overlay. Notes and warnings go to stderr.
selinux_overlay_from_config() {
    local writer="$1" root records svc target ro chp src real fs label inside
    local -a order=()
    local -A body=() unconfined=() listed=() seen=() relabelled=()
    root="$(readlink -f -- "${ARM_DIR}" 2>/dev/null || printf '%s' "${ARM_DIR}")"
    records="$(selinux_bind_mounts)"
    while IFS=$'\t' read -r svc target ro chp src; do
        [[ -n "${svc}" ]] || continue
        if [[ -z "${listed[${svc}]+x}" ]]; then
            listed["${svc}"]=1
            order+=("${svc}")
        fi
        if selinux_is_socket "${src}"; then
            unconfined["${svc}"]=1
            continue
        fi
        # Devices and runtime trees (e.g. /dev/disk) never take a label.
        [[ -f "${src}" || -d "${src}" ]] || continue
        real="$(readlink -f -- "${src}" 2>/dev/null || printf '%s' "${src}")"
        fs="$(selinux_fs_type "${real}")"
        label="$(selinux_label_type "${real}")"
        inside=0
        [[ "${real}" == "${root}/"* ]] && inside=1
        if [[ "${inside}" -eq 1 ]] && ! selinux_unlabelled_fs "${fs}"; then
            body["${svc}"]+="      - type: bind
        source: $(selinux_yaml_quote "${src}")
        target: $(selinux_yaml_quote "${target}")
"
            [[ "${ro}" -eq 1 ]] && body["${svc}"]+="        read_only: true
"
            # Compose replaces the template's whole `bind:` block with this
            # one, so carry its create_host_path over.
            body["${svc}"]+="        bind:
"
            [[ "${chp}" -eq 1 ]] && body["${svc}"]+="          create_host_path: true
"
            body["${svc}"]+="          selinux: z
"
            relabelled["${real}"]=1
            continue
        fi
        # Already usable: nothing to say.
        [[ -z "${label}" || "${label}" == container_file_t ]] && continue
        [[ -n "${seen[${real}]+x}" ]] && continue
        seen["${real}"]=1
        selinux_hint "${src}" "${fs}" "${label}" "${inside}" >&2
    done <<<"${records}"

    local any=0
    printf '# Generated by %s (deploy/lib/selinux.sh). Do not edit: it is rewritten on every run.\n' "${writer}"
    for svc in "${order[@]}"; do
        [[ -n "${body[${svc}]+x}" || -n "${unconfined[${svc}]+x}" ]] || continue
        if [[ "${any}" -eq 0 ]]; then printf 'services:\n'; any=1; fi
        printf '  %s:\n' "${svc}"
        if [[ -n "${unconfined[${svc}]+x}" ]]; then
            printf '    security_opt:\n      - label=disable\n'
        fi
        if [[ -n "${body[${svc}]+x}" ]]; then
            printf '    volumes:\n%s' "${body[${svc}]}"
        fi
    done
    [[ "${any}" -eq 1 ]] || printf '%s\n' "${SELINUX_OVERLAY_EMPTY}"

    if [[ ${#relabelled[@]} -gt 0 ]]; then
        arm_say "SELinux: labelling ${#relabelled[@]} bind-mounted path(s) under ${ARM_DIR} for containers" >&2
    fi
    for svc in "${order[@]}"; do
        [[ -n "${unconfined[${svc}]+x}" ]] && arm_say "SELinux: ${svc} mounts the Docker socket; running it with label=disable" >&2
    done
    return 0
}

# write_selinux_overlay <path> <writer>: rewrite the overlay from the stack's
# resolved config. The caller has already put <path> on the compose file list.
# The overlay is emptied before the config is read: otherwise the previous run's
# overlay would be part of the input, and its replacements (not the template's
# mounts) would be what this run copies.
write_selinux_overlay() {
    local overlay="$1" writer="$2" cfg tmp
    printf '%s\n' "${SELINUX_OVERLAY_EMPTY}" > "${overlay}"
    if ! cfg="$(compose config)"; then
        arm_err "could not read the compose config to write ${overlay}"
        return 1
    fi
    tmp="${overlay}.tmp"
    selinux_overlay_from_config "${writer}" <<<"${cfg}" > "${tmp}" || { rm -f "${tmp}"; return 1; }
    mv "${tmp}" "${overlay}"
}
