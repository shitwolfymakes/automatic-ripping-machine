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
    cdrom_group="$(getent group "${CDROM_GID}" | cut -d: -f1)"
    if [[ -z "${cdrom_group}" ]]; then
        groupadd --gid "${CDROM_GID}" cdrom-host
        cdrom_group="cdrom-host"
    fi
    usermod --append --groups "${cdrom_group}" arm
fi

for d in /logs /raw /media; do
    [[ -d "$d" ]] || continue
    chown arm:arm "$d" 2>/dev/null || true
done

# Ripper-only: refresh the MakeMKV app_Key on every boot. The hook is
# gated on update_key.sh + makemkvcon existing, so backend / transcode
# containers no-op past it. Failures must not block boot.
if [[ -x /usr/local/bin/update_key.sh ]] && command -v makemkvcon >/dev/null 2>&1; then
    [[ -d /home/arm/.MakeMKV ]] || install -d -o arm -g arm /home/arm/.MakeMKV
    chown arm:arm /home/arm /home/arm/.MakeMKV 2>/dev/null || true
    gosu arm /usr/local/bin/update_key.sh || true
fi

umask 002
exec /usr/bin/tini -- gosu arm "$@"
