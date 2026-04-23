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

umask 002
exec /usr/bin/tini -- gosu arm "$@"
