#!/usr/bin/env bash
set -euo pipefail

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

# ---------------------------------------------------------------- functions

# Grant the arm user access to /dev/dri render nodes BEFORE the gosu drop —
# gosu resets supplementary groups, so a docker --group-add would not survive;
# membership must be written to /etc/group here.
#
# Resolution order:
#   1. Explicit RENDER_GID env (dispatcher override / legacy configs) — wins.
#   2. Self-derive: stat every mounted renderD* node. Device nodes keep their
#      HOST gid inside the container, so this is correct on whichever host the
#      container actually runs (local or remote offload) with zero config.
# No nodes and no RENDER_GID → silent no-op (backend/ripper/ui/CPU/NVENC).
# ARM_RENDER_NODE_DIR is a test seam; production always uses /dev/dri.
setup_render_access() {
    local dri_dir="${ARM_RENDER_NODE_DIR:-/dev/dri}"
    if [[ -n "${RENDER_GID:-}" ]]; then
        if [[ "${RENDER_GID}" == "0" ]]; then
            echo "render access: refusing explicit RENDER_GID=0 — never adding arm to gid 0" >&2
            return 0
        fi
        _join_render_gid "${RENDER_GID}" "render-host"
        echo "render access: RENDER_GID=${RENDER_GID} (explicit)"
        return 0
    fi
    local node gid g seen failed=0 found=0
    local gids=()
    for node in "${dri_dir}"/renderD*; do
        [[ -e "$node" ]] || continue
        found=1
        if ! gid="$(stat -c '%g' "$node" 2>/dev/null)"; then
            echo "render access: FAILED — cannot stat ${node}" >&2
            failed=1
            continue
        fi
        if [[ "$gid" == "0" ]]; then
            echo "render access: skipping ${node} (group root) — refusing to add arm to gid 0" >&2
            continue
        fi
        seen=0
        for g in "${gids[@]}"; do [[ "$g" == "$gid" ]] && seen=1; done
        [[ "$seen" == "1" ]] && continue
        gids+=("$gid")
        _join_render_gid "$gid" "render-host-${gid}"
    done
    if [[ "${#gids[@]}" -gt 0 ]]; then
        echo "render access: derived gid(s) ${gids[*]} from ${dri_dir}/renderD*"
    elif [[ "${ARM_GPU_DEVICE:-}" == /dev/dri/* ]]; then
        # The dispatcher assigned a render-node GPU but no usable gid was
        # derived — HandBrake will fail encoder init; make the cause greppable.
        # (Per-node stat failures already printed their own FAILED line.)
        if [[ "$found" == "0" ]]; then
            echo "render access: FAILED — ARM_GPU_DEVICE=${ARM_GPU_DEVICE} set but no ${dri_dir}/renderD* visible" >&2
        elif [[ "$failed" == "0" ]]; then
            echo "render access: FAILED — ARM_GPU_DEVICE=${ARM_GPU_DEVICE} set but no usable render gid (node group is root)" >&2
        fi
    fi
    return 0
}

# _join_render_gid <gid> <fallback_name>: adopt an existing group by gid, else
# create <fallback_name> with that gid; then append arm. Mirrors the
# CDROM_GID / docker.sock adopt-by-gid handling below.
_join_render_gid() {
    local gid="$1" fallback_name="$2" group
    group="$(getent group "${gid}" | cut -d: -f1 || true)"
    if [[ -z "${group}" ]]; then
        groupadd --gid "${gid}" "${fallback_name}"
        group="${fallback_name}"
    fi
    usermod --append --groups "${group}" arm
}

# Test seam: lets services/_common/test-entrypoint-render.sh source the
# functions above without executing the entrypoint (mirrors install.sh's
# ARM_INSTALL_SOURCE_ONLY). The sourced-ness check makes a leaked env var
# harmless when the entrypoint is EXECUTED (top-level `return` would abort).
[[ -n "${ARM_ENTRYPOINT_SOURCE_ONLY:-}" && "${BASH_SOURCE[0]}" != "$0" ]] && return 0

if [[ -f /etc/ssl/arm/arm-ca.crt ]]; then
    cp /etc/ssl/arm/arm-ca.crt /usr/local/share/ca-certificates/arm-ca.crt
    update-ca-certificates >/dev/null
fi

if ! getent group arm >/dev/null; then
    groupadd --gid "${PGID}" arm
else
    groupmod --gid "${PGID}" arm
fi

if ! id -u arm >/dev/null 2>&1; then
    useradd --no-create-home --uid "${PUID}" --gid "${PGID}" --shell /usr/sbin/nologin arm
else
    usermod --uid "${PUID}" --gid "${PGID}" arm
fi

if [[ -n "${CDROM_GID:-}" ]]; then
    cdrom_group="$(getent group "${CDROM_GID}" | cut -d: -f1 || true)"
    if [[ -z "${cdrom_group}" ]]; then
        groupadd --gid "${CDROM_GID}" cdrom-host
        cdrom_group="cdrom-host"
    fi
    usermod --append --groups "${cdrom_group}" arm
fi

# Transcode-only path: VAAPI/QSV render-node access (see setup_render_access
# above — explicit RENDER_GID wins, else derived from the mounted nodes).
setup_render_access

# Backend-only path: when /var/run/docker.sock is bind-mounted in so the
# transcode dispatcher can spawn arm-transcode-* containers, the socket's
# host GID varies per distro (989 on Debian 13, 998/999 on Ubuntu, ...).
# Stat the socket and add `arm` to the matching group so docker-py can
# connect without running the backend as root. No-op for ripper/ui/
# transcode (they don't mount the socket).
if [[ -S /var/run/docker.sock ]]; then
    sock_gid="$(stat -c '%g' /var/run/docker.sock)"
    if [[ -n "${sock_gid}" && "${sock_gid}" != "0" ]]; then
        # `getent group <gid>` exits 2 when the GID isn't already a known
        # group inside the image — under `set -euo pipefail` that kills the
        # script. Tolerate the miss and let the next branch create the group.
        sock_group="$(getent group "${sock_gid}" | cut -d: -f1 || true)"
        if [[ -z "${sock_group}" ]]; then
            groupadd --gid "${sock_gid}" docker-host
            sock_group="docker-host"
        fi
        usermod --append --groups "${sock_group}" arm
    fi
fi

for d in /logs /raw /media; do
    [[ -d "$d" ]] || continue
    chown arm:arm "$d" 2>/dev/null || true
done

# Ripper-only: ensure the arm user owns its home + MakeMKV config dir so the
# per-rip key refresh (arm_ripper/makemkv_key.py) can write settings.conf —
# the Dockerfile chowns /home/arm to UID 1000 at build, so a PUID/PGID remap
# would otherwise leave it unwritable. The key itself is no longer scraped at
# boot; the JobController runs update_key.sh before every rip. Gated on the
# ripper image's update_key.sh + makemkvcon so backend / transcode no-op past it.
if [[ -x /usr/local/bin/update_key.sh ]] && command -v makemkvcon >/dev/null 2>&1; then
    [[ -d /home/arm/.MakeMKV ]] || install -d -o arm -g arm /home/arm/.MakeMKV
    chown arm:arm /home/arm /home/arm/.MakeMKV 2>/dev/null || true
fi

umask 002
exec /usr/bin/tini -- gosu arm "$@"
