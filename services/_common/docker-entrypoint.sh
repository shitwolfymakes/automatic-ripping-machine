#!/usr/bin/env bash
set -euo pipefail

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

# WRITE_TEST answers "can the drop-uid write $d?". Production drops to `arm` via
# gosu so the result reflects NFSv4-ACL enforcement server-side (a root test
# lies under root_squash). `test -w` is a faccessat — read-only, no atime bump,
# no NFS write side-effect. Array form so it word-splits cleanly (SC2086-safe).
# The guard test pre-declares WRITE_TEST=(test -w) before sourcing this file;
# the `declare -p` check means "default it only if the caller hasn't set it".
if ! declare -p WRITE_TEST >/dev/null 2>&1; then
    WRITE_TEST=(gosu arm test -w)
fi

# MOUNT_TEST answers "is $d an actual mounted volume?" (vs an incidental
# root-owned dir baked into the base image, e.g. the ripper's /media, which
# this service never mounts and must not be gated). Array + declare-p seam so
# the guard test can substitute a stub; production uses `mountpoint -q`.
if ! declare -p MOUNT_TEST >/dev/null 2>&1; then
    MOUNT_TEST=(mountpoint -q)
fi

# RO_TEST answers "is $d mounted read-only?" (e.g. the transcode dispatcher
# mounts /raw ro on purpose — transcoders only read rips). `test -w` on an ro
# mount is always false, so gating write-ability there would crash-loop every
# transcoder. Reads /proc/self/mounts directly (no findmnt dependency — slim
# images may not ship util-linux's findmnt). Array + declare-p seam so the
# guard test can substitute a stub, same pattern as MOUNT_TEST/WRITE_TEST.
if ! declare -p RO_TEST >/dev/null 2>&1; then
    RO_TEST=(mount_is_readonly)
fi

mount_is_readonly() {  # <dir> -> rc 0 iff the mountpoint at <dir> is ro
    local d="$1"
    awk -v d="$d" '$2 == d && $4 ~ /(^|,)ro(,|$)/ { found=1 } END { exit !found }' /proc/self/mounts
}

# READ_TEST is WRITE_TEST's counterpart for the read-only-mount path: "can the
# drop-uid read $d?" Same gosu-drop rationale as WRITE_TEST (see above). The
# guard test pre-declares READ_TEST=(test -r) before sourcing this file.
if ! declare -p READ_TEST >/dev/null 2>&1; then
    READ_TEST=(gosu arm test -r)
fi

# Bounded retry so a TRANSIENT mount-not-ready (NFS server slow, net settling)
# does not trip the hard exit — which, under `restart: unless-stopped`, would
# become a crash-loop. A PERSISTENT misconfig still fails fast (~ATTEMPTS*DELAY).
WRITE_CHECK_ATTEMPTS="${WRITE_CHECK_ATTEMPTS:-5}"
WRITE_CHECK_DELAY="${WRITE_CHECK_DELAY:-2}"

# v3 invariant (docs/arch/06-deployment.md): never chown a user-mounted volume.
# Ownership + setgid are host-prep (install.sh: `chmod 2775`). Here we only
# VERIFY the drop-uid can write each mounted data dir and fail fast with a clear
# diagnostic if not — instead of silently corrupting ownership (which bricks
# NFSv4-ACL exports for every uid) or dying later with an opaque [Errno 13].
require_writable() {
    local d="$1"
    # Only gate dirs that are actually mounted volumes for THIS service. A bare
    # `-d` test is not enough: some base images ship an incidental root-owned
    # /media (or similar) that this service never mounts — gating it would fail
    # fast on a dir the service doesn't use. A mounted data volume is always a
    # mountpoint; an incidental image dir is not.
    [[ -d "$d" ]] || return 0                    # absent -> not mounted here -> skip
    "${MOUNT_TEST[@]}" "$d" || return 0          # present but not a mount -> incidental image dir -> skip

    # A read-only mount (e.g. /raw in a transcoder) can never satisfy a write
    # test by design — gate readability instead, since that is the equivalent
    # ownership/uid check for a mount the service only ever reads.
    if "${RO_TEST[@]}" "$d"; then
        local attempt=1
        while (( attempt <= WRITE_CHECK_ATTEMPTS )); do
            if "${READ_TEST[@]}" "$d"; then
                return 0
            fi
            if (( attempt < WRITE_CHECK_ATTEMPTS )); then
                echo "waiting for ${d} to become readable by arm (attempt ${attempt}/${WRITE_CHECK_ATTEMPTS})..." >&2
                sleep "${WRITE_CHECK_DELAY}"
            fi
            (( attempt++ ))
        done
        local ro_owner
        ro_owner="$(stat -c '%u:%g' "$d" 2>/dev/null || echo '?:?')"
        echo "FATAL: ${d} is not readable by arm (read-only mount) (PUID:PGID=${PUID}:${PGID}); dir owner is ${ro_owner}." >&2
        echo "       ARM does not chown user-mounted volumes (docs/arch/06-deployment.md)." >&2
        echo "       Fix host ownership so it matches PUID:PGID — e.g. a NAS export owned by a" >&2
        echo "       different uid, or a PUID that doesn't match the mount owner." >&2
        return 1
    fi

    local attempt=1
    while (( attempt <= WRITE_CHECK_ATTEMPTS )); do
        if "${WRITE_TEST[@]}" "$d"; then
            return 0
        fi
        if (( attempt < WRITE_CHECK_ATTEMPTS )); then
            echo "waiting for ${d} to become writable by arm (attempt ${attempt}/${WRITE_CHECK_ATTEMPTS})..." >&2
            sleep "${WRITE_CHECK_DELAY}"
        fi
        (( attempt++ ))
    done
    local owner
    owner="$(stat -c '%u:%g' "$d" 2>/dev/null || echo '?:?')"
    echo "FATAL: ${d} is not writable by arm (PUID:PGID=${PUID}:${PGID}); dir owner is ${owner}." >&2
    echo "       ARM does not chown user-mounted volumes (docs/arch/06-deployment.md)." >&2
    echo "       Fix host ownership so it matches PUID:PGID — e.g. a NAS export owned by a" >&2
    echo "       different uid, or a PUID that doesn't match the mount owner." >&2
    return 1
}

# ---------------------------------------------------------------- optical nodes
# The ripper is NOT given its drive via a compose/docker `devices:` bind. Docker
# resolves those at container-create time, so an absent drive fails creation
# before the restart policy can engage, and a drive replugged later never
# appears inside a running container (moby#46608, moby#19763). Instead the
# container's device cgroup is granted the optical majors (b 11 = sr*, c 21 =
# sg*) and the nodes are created here.
#
# This works for hotplug because the kernel binds names to numbers statically:
# sr<N> is always block 11:<N> and sg<N> is always char 21:<N>. A node for a
# minor with no hardware behind it is harmless — open() gets ENXIO — and the
# same node starts working the moment a drive is enumerated onto that minor.
# So a fixed range created up front covers drives that come and go, and drives
# that come back under a different number, with no runtime mknod and no extra
# privilege: CAP_MKNOD is in Docker's default set and the cgroup rule's `m`
# bit permits it for exactly these majors.
#
# Both sr and sg are required: MakeMKV enumerates drives from real device
# nodes in the container's own /dev (symlinks and sg-only were both verified
# to fail) and pairs each sr with its sg itself.
#
# Existing nodes are skipped. Defined above the SOURCE_ONLY seam so
# test-entrypoint-optical.sh can exercise it unprivileged.
precreate_optical_nodes() {  # <dev_dir> <sr_max> <sg_max> <group>
    local dev_dir="$1" sr_max="$2" sg_max="$3" group="$4"
    local n created=0
    for n in $(seq 0 "${sr_max}"); do
        [[ -e "${dev_dir}/sr${n}" ]] && continue
        mknod -m 0660 "${dev_dir}/sr${n}" b 11 "${n}"
        chgrp "${group}" "${dev_dir}/sr${n}"
        created=$((created + 1))
    done
    for n in $(seq 0 "${sg_max}"); do
        [[ -e "${dev_dir}/sg${n}" ]] && continue
        mknod -m 0660 "${dev_dir}/sg${n}" c 21 "${n}"
        chgrp "${group}" "${dev_dir}/sg${n}"
        created=$((created + 1))
    done
    echo "optical nodes: created ${created} (sr0..sr${sr_max}, sg0..sg${sg_max}) in ${dev_dir}"
}

# Let the guard test source this file for its function/config without running
# the entrypoint's setup + exec. No-op in production (var never set there).
[[ -n "${ARM_ENTRYPOINT_SOURCE_ONLY:-}" ]] && return 0

if [[ -f /etc/ssl/arm/arm-ca.crt ]]; then
    cp /etc/ssl/arm/arm-ca.crt /usr/local/share/ca-certificates/arm-ca.crt
    update-ca-certificates >/dev/null
fi

# Give the arm user primary gid PGID. If that gid ALREADY exists in the image
# (gid 100 `users` — a common primary gid on SUSE/Synology hosts — or any
# Debian system gid), adopt the existing group instead: groupadd/groupmod
# refuse a duplicate gid and the service would crash-loop. useradd/usermod
# below take the numeric gid directly, whatever group name owns it. Mirrors
# the CDROM_GID/RENDER_GID adopt-by-gid handling further down.
if ! getent group "${PGID}" >/dev/null; then
    if getent group arm >/dev/null; then
        groupmod --gid "${PGID}" arm
    else
        groupadd --gid "${PGID}" arm
    fi
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

# Ripper-only path: pre-create the optical device nodes (see
# precreate_optical_nodes above). Gated on ARM_DRIVE_ID so the shared
# entrypoint does nothing for backend/ui/transcode containers. Group-owned
# like the host's nodes (root:cdrom 0660) so the gosu-dropped arm user can
# open them through the cdrom membership set up just above.
if [[ -n "${ARM_DRIVE_ID:-}" ]]; then
    precreate_optical_nodes /dev "${ARM_OPTICAL_SR_MAX:-7}" "${ARM_OPTICAL_SG_MAX:-15}" "${cdrom_group:-root}"
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
    require_writable "$d" || exit 1
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
# gosu switches UID but preserves the inherited environment — including
# HOME=/root from the root-owned parent. Processes running as `arm` must see
# HOME=/home/arm so `~` resolves to the arm user's dotfiles: paramiko (via the
# transcode dispatcher's docker-py ssh:// client) reads ~/.ssh/known_hosts, and
# with HOME=/root it looks in the nonexistent /root/.ssh and the remote
# transcode host key is "not found in known_hosts" → dispatcher disabled.
export HOME=/home/arm
exec /usr/bin/tini -- gosu arm "$@"
