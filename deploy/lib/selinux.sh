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
#   - a device or runtime path (/dev/disk, anything on devtmpfs, proc or
#     sysfs): skipped. udev manages those labels, and relabelling them would
#     do harm.
# Compose merges an overlay's mounts into the template's by target path, so the
# overlay restates each mount's source, mode, create_host_path and propagation
# and adds the label. With nothing to label it is `services: {}`.
#
# `:z` also works for the backend, which runs with label=disable: Docker then
# gives the container the shared container mount label, so the backend's own
# mounts of raw/, media/ and logs/ are what labels the folders the rippers and
# transcoders it spawns use. Their files keep the shared label (plain s0), so
# one container can read what another wrote.
#
# Flow: selinux_bind_mounts (parse) -> selinux_plan (decide, one line per
# mount) -> selinux_report (hints and summary, stderr) and selinux_emit_overlay
# (YAML, stdout). selinux_apply is the entry point both callers share.
#
# ARM_SELINUX_LABELS in .env: auto (default; follow `docker info`), on, off.

SELINUX_OVERLAY_EMPTY='services: {}'

# selinux_empty_overlay <path>: write the overlay that changes nothing.
selinux_empty_overlay() { printf '%s\n' "${SELINUX_OVERLAY_EMPTY}" > "$1"; }

# ensure_selinux_overlay_file <path>: create an empty overlay if none exists,
# so a compose file list that names it stays valid.
ensure_selinux_overlay_file() {
    [[ -f "$1" ]] || selinux_empty_overlay "$1"
}

# Filesystems that keep no per-file SELinux label: Docker cannot relabel a path
# on them, and asking it to (`:z`) makes container creation fail.
selinux_unlabelled_fs() {
    case "$1" in
        nfs*|cifs|smb*|fuse*|msdos|vfat|exfat|v9fs|9p|ntfs*|autofs) return 0 ;;
    esac
    return 1
}

# selinux_never_label <real path> <fs type>: true for device and runtime trees.
# They are neither labelled nor reported: their labels belong to udev and the
# kernel, and the containers that mount them do not need container_file_t.
selinux_never_label() {
    case "$2" in
        devtmpfs|proc|sysfs|cgroup*|securityfs|debugfs|tracefs) return 0 ;;
    esac
    case "$1" in
        /dev|/dev/*|/proc|/proc/*|/sys|/sys/*|/run|/run/*) return 0 ;;
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
# True when Docker labels the containers it starts. Podman's docker emulation
# is not detected; ARM_SELINUX_LABELS=on covers it.
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

# --- COMPOSE_FILE (setup-dev.sh) -------------------------------------------
# setup-dev puts the overlay on COMPOSE_FILE in .env, so manual `docker compose`
# commands get it too. armctl names its files with -f and does not use this.

# selinux_list_names <list> <separator> <name>: true when the list names <name>.
selinux_list_names() {
    [[ "$2$1$2" == *"$2$3$2"* ]]
}

# selinux_compose_separator: COMPOSE_PATH_SEPARATOR from .env, or compose's ':'.
selinux_compose_separator() {
    local sep
    sep="$(env_file_value COMPOSE_PATH_SEPARATOR)"
    printf '%s' "${sep:-:}"
}

# selinux_overlay_listed <name>: true when COMPOSE_FILE in .env names it.
selinux_overlay_listed() {
    selinux_list_names "$(env_file_value COMPOSE_FILE)" "$(selinux_compose_separator)" "$1"
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

# selinux_warn_shell_compose_file <separator> <name>: a COMPOSE_FILE exported in
# the shell overrides the one in .env, so compose would not load the overlay.
selinux_warn_shell_compose_file() {
    [[ -n "${COMPOSE_FILE+x}" ]] || return 0
    selinux_list_names "${COMPOSE_FILE}" "$1" "$2" && return 0
    arm_warn "SELinux: COMPOSE_FILE is set in your shell (${COMPOSE_FILE}). It overrides .env, so docker compose will not load $2."
    arm_sub  "       Unset it, or add $2 to it."
}

# selinux_sync_compose_files add|keep <root dir> <overlay name>: bring
# COMPOSE_FILE in .env to the list selinux_compose_files gives. An override
# created or deleted after the overlay joined the list is picked up here, on
# the next run. `add` puts the overlay on the list; `keep` changes the list only
# if it already names the overlay.
selinux_sync_compose_files() {
    local mode="$1" root="$2" name="$3" sep files want override=0
    sep="$(selinux_compose_separator)"
    files="$(env_file_value COMPOSE_FILE)"
    if [[ "${mode}" == keep ]] && ! selinux_list_names "${files}" "${sep}" "${name}"; then
        return 0
    fi
    if [[ -f "${root}/docker-compose.override.yml" ]]; then override=1; fi
    want="$(selinux_compose_files "${files}" "${sep}" "${name}" "${override}")"
    selinux_warn_shell_compose_file "${sep}" "${name}"
    [[ "${want}" != "${files}" ]] || return 0
    env_set COMPOSE_FILE "${want}"
    arm_say "SELinux: COMPOSE_FILE in .env is now ${want}"
}

# selinux_dev_prepare <root dir> <overlay name>: run at the top of setup-dev,
# before any compose command (`down` included). Once .env names the overlay,
# the file must exist, and the list must follow docker-compose.override.yml.
selinux_dev_prepare() {
    selinux_overlay_listed "$2" || return 0
    ensure_selinux_overlay_file "$1/$2"
    selinux_sync_compose_files keep "$1" "$2"
}

# --- reading the compose config -------------------------------------------

# The bind mounts of a `docker compose config` document on stdin, one per line:
# service <TAB> target <TAB> read_only (0|1) <TAB> create_host_path (0|1) <TAB>
# propagation (- for none) <TAB> source. Compose prints every mount in the long
# form, fields at fixed indents; a quoted value is unquoted.
selinux_bind_mounts() {
    awk '
        function unq(v) {
            if (v ~ /^".*"$/) { v = substr(v, 2, length(v) - 2); gsub(/\\"/, "\"", v); gsub(/\\\\/, "\\", v) }
            else if (v ~ /^\047.*\047$/) { v = substr(v, 2, length(v) - 2); gsub(/\047\047/, "\047", v) }
            return v
        }
        function flush() {
            if (type == "bind" && src != "" && tgt != "") printf "%s\t%s\t%d\t%d\t%s\t%s\n", svc, tgt, ro, chp, prop, src
            type = ""; src = ""; tgt = ""; ro = 0; chp = 0; prop = "-"
        }
        BEGIN { prop = "-" }
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
        /^          propagation: [a-z]+$/ { prop = $2 }
        END { flush() }
    '
}

selinux_real_path() { readlink -f -- "$1" 2>/dev/null || printf '%s' "$1"; }

# selinux_mount_action <inside ARM_DIR 0|1> <fs type> <label type>: what to do
# with one existing, non-device bind mount. Prints one word:
#   label  inside ARM_DIR on a filesystem that keeps labels: add `selinux: z`
#   skip   already usable (container_file_t), or a host without labels
#   hint   anything else: leave it, tell the user how to fix it
selinux_mount_action() {
    if [[ "$1" -eq 1 ]] && ! selinux_unlabelled_fs "$2"; then
        echo label
    elif [[ -z "$3" || "$3" == container_file_t ]]; then
        echo skip
    else
        echo hint
    fi
}

# selinux_plan: read a `docker compose config` document on stdin, print one
# line per mount that matters, tab-separated:
#   socket <svc>
#   label  <svc> <target> <ro> <chp> <propagation> <source> <real path>
#   hint   <svc> <source> <fs type> <label type> <real path>
selinux_plan() {
    local root svc target ro chp prop src real fs label inside
    root="$(selinux_real_path "${ARM_DIR}")"
    while IFS=$'\t' read -r svc target ro chp prop src; do
        [[ -n "${svc}" ]] || continue
        if selinux_is_socket "${src}"; then
            printf 'socket\t%s\n' "${svc}"
            continue
        fi
        [[ -f "${src}" || -d "${src}" ]] || continue
        real="$(selinux_real_path "${src}")"
        fs="$(selinux_fs_type "${real}")"
        selinux_never_label "${real}" "${fs}" && continue
        label="$(selinux_label_type "${real}")"
        inside=0
        [[ "${real}" == "${root}/"* ]] && inside=1
        case "$(selinux_mount_action "${inside}" "${fs}" "${label}")" in
            label) printf 'label\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "${svc}" "${target}" "${ro}" "${chp}" "${prop}" "${src}" "${real}" ;;
            hint)  printf 'hint\t%s\t%s\t%s\t%s\t%s\n' "${svc}" "${src}" "${fs:--}" "${label}" "${real}" ;;
        esac
    done < <(selinux_bind_mounts)
}

selinux_yaml_quote() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    printf '"%s"' "${s}"
}

# selinux_mount_yaml <target> <ro> <chp> <propagation> <source>: one overlay
# mount. Compose replaces the template's whole `bind:` block with this one, so
# create_host_path and propagation are carried over.
selinux_mount_yaml() {
    printf '      - type: bind\n        source: %s\n        target: %s\n' \
        "$(selinux_yaml_quote "$5")" "$(selinux_yaml_quote "$1")"
    if [[ "$2" -eq 1 ]]; then printf '        read_only: true\n'; fi
    printf '        bind:\n'
    if [[ "$3" -eq 1 ]]; then printf '          create_host_path: true\n'; fi
    if [[ "$4" != - ]]; then printf '          propagation: %s\n' "$4"; fi
    printf '          selinux: z\n'
}

# selinux_emit_overlay <writer>: read a plan on stdin, print the overlay.
selinux_emit_overlay() {
    local kind svc target ro chp prop src
    local -a order=()
    local -A body=() unconfined=() listed=()
    while IFS=$'\t' read -r kind svc target ro chp prop src _; do
        case "${kind}" in
            socket) unconfined["${svc}"]=1 ;;
            label)  body["${svc}"]+="$(selinux_mount_yaml "${target}" "${ro}" "${chp}" "${prop}" "${src}")"$'\n' ;;
            *)      continue ;;
        esac
        if [[ -z "${listed[${svc}]+x}" ]]; then listed["${svc}"]=1; order+=("${svc}"); fi
    done
    printf '# Generated by %s (deploy/lib/selinux.sh). Do not edit: it is rewritten on every run.\n' "$1"
    if [[ ${#order[@]} -eq 0 ]]; then
        printf '%s\n' "${SELINUX_OVERLAY_EMPTY}"
        return 0
    fi
    printf 'services:\n'
    for svc in "${order[@]}"; do
        printf '  %s:\n' "${svc}"
        if [[ -n "${unconfined[${svc}]+x}" ]]; then printf '    security_opt:\n      - label=disable\n'; fi
        if [[ -n "${body[${svc}]+x}" ]]; then printf '    volumes:\n%s' "${body[${svc}]}"; fi
    done
}

# selinux_fs_hint <path> <fs type>: a path on a filesystem without per-file
# labels: name the boolean that lets containers use it, if there is one.
selinux_fs_hint() {
    local bool=""
    case "$2" in
        nfs*)       bool=virt_use_nfs ;;
        cifs|smb*)  bool=virt_use_samba ;;
        fuse*)      bool=virt_use_fusefs ;;
    esac
    if [[ -z "${bool}" ]]; then
        arm_warn "SELinux: $1 is on $2, which has no per-file labels, so containers cannot use it."
        arm_sub  "       Mount it with context=\"system_u:object_r:container_file_t:s0\", or move it to a Linux filesystem."
        return 0
    fi
    selinux_bool_on "${bool}" && return 0
    arm_warn "SELinux: $1 is on $2, which has no per-file labels, so containers cannot use it yet."
    arm_sub  "       Allow containers on $2 once with: sudo setsebool -P ${bool} 1"
}

# selinux_hint <path> <fs type> <label type>: warn about a mount whose label
# would block the containers, with the command that fixes it. A path inside
# ARM_DIR only gets here on a filesystem without labels (selinux_mount_action).
selinux_hint() {
    if selinux_unlabelled_fs "$2"; then
        selinux_fs_hint "$1" "$2"
        return 0
    fi
    arm_warn "SELinux: $1 is labelled $3, which containers cannot use. It is outside ${ARM_DIR}, so ARM leaves its label alone."
    arm_sub  "       To give it to ARM: sudo chcon -R -t container_file_t '$1'"
    arm_sub  "       That replaces its current label; check first that nothing else on this host relies on $3."
}

# selinux_report: read a plan on stdin; print each hint once per real path,
# then what was labelled and which services run unlabelled.
selinux_report() {
    local svc
    local -a f=() sockets=()
    local -A seen=() relabelled=() listed=()
    while IFS=$'\t' read -r -a f; do
        [[ ${#f[@]} -gt 0 ]] || continue
        case "${f[0]}" in
            label) relabelled["${f[7]}"]=1 ;;
            socket)
                if [[ -z "${listed[${f[1]}]+x}" ]]; then listed["${f[1]}"]=1; sockets+=("${f[1]}"); fi ;;
            hint)
                if [[ -z "${seen[${f[5]}]+x}" ]]; then seen["${f[5]}"]=1; selinux_hint "${f[2]}" "${f[3]}" "${f[4]}"; fi ;;
        esac
    done
    if [[ ${#relabelled[@]} -gt 0 ]]; then
        arm_say "SELinux: labelling ${#relabelled[@]} bind-mounted path(s) under ${ARM_DIR} for containers"
    fi
    for svc in "${sockets[@]+"${sockets[@]}"}"; do
        arm_say "SELinux: ${svc} mounts the Docker socket; running it with label=disable"
    done
}

# selinux_overlay_from_config <writer>: read a `docker compose config` document
# on stdin, print the overlay. Notes and warnings go to stderr.
selinux_overlay_from_config() {
    local plan
    plan="$(selinux_plan)"
    selinux_report <<<"${plan}" >&2
    selinux_emit_overlay "$1" <<<"${plan}"
}

# write_selinux_overlay <path> <writer>: rewrite the overlay from the stack's
# resolved config. The caller has already put <path> on the compose file list.
# The overlay is emptied before the config is read: otherwise the previous run's
# overlay would be part of the input, and its replacements (not the template's
# mounts) would be what this run copies. On failure it stays empty, which
# leaves the stack as it would be without SELinux handling.
write_selinux_overlay() {
    local overlay="$1" writer="$2" cfg tmp
    selinux_empty_overlay "${overlay}"
    if ! cfg="$(compose config)"; then
        arm_err "could not read the compose config to write ${overlay}"
        return 1
    fi
    tmp="${overlay}.tmp"
    selinux_overlay_from_config "${writer}" <<<"${cfg}" > "${tmp}" || { rm -f "${tmp}"; return 1; }
    mv "${tmp}" "${overlay}"
}

# selinux_apply <overlay> <writer> <register command...>: the step both callers
# run. When labels are needed, create the overlay, run <register command> to
# put it on the compose file list (armctl: use_env_file; setup-dev: the
# COMPOSE_FILE sync), then write it. When they are not, an overlay from an
# earlier run is emptied, never removed, so a file list naming it stays valid.
selinux_apply() {
    local overlay="$1" writer="$2"
    shift 2
    if selinux_labels_needed; then
        ensure_selinux_overlay_file "${overlay}"
        "$@"
        write_selinux_overlay "${overlay}" "${writer}"
    elif [[ -f "${overlay}" ]]; then
        selinux_empty_overlay "${overlay}"
    fi
}
