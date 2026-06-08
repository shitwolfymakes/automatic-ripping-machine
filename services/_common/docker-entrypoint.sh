#!/usr/bin/env bash
set -euo pipefail

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

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

# Transcode-only path: VAAPI/QSV transcoders get the host's /dev/dri render node
# (root:render 0660) passed in by the dispatcher. The node is group-owned, so the
# `arm` user must join that group IN /etc/group — `gosu` resets supplementary
# groups to the user's membership, dropping any docker --group-add. Mirrors the
# CDROM_GID handling above. No-op when RENDER_GID is unset (CPU / NVENC / ripper).
if [[ -n "${RENDER_GID:-}" ]]; then
    render_group="$(getent group "${RENDER_GID}" | cut -d: -f1 || true)"
    if [[ -z "${render_group}" ]]; then
        groupadd --gid "${RENDER_GID}" render-host
        render_group="render-host"
    fi
    usermod --append --groups "${render_group}" arm
fi

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
