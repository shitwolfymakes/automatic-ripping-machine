#!/usr/bin/env bash
# ARM v3 installer.
#
# One-command bootstrap for the v3 stack. Generates the internal CA + per-
# service leaf certs, seeds .env with sensible defaults, generates a
# docker-compose.yml with one ripper service per detected drive, and
# (on desktop hosts) installs a host-side udev rule disabling auto-mount
# for ARM-managed drives.
#
# Usage:
#   curl -fsSL .../install.sh | bash
#   bash install.sh                       # local checkout, default prefix
#   bash install.sh --prefix /srv/arm     # custom prefix
#   bash install.sh --start               # also `docker compose up -d`
#   bash install.sh --rotate-ca           # regen CA + every leaf
#
# Advanced (used by setup-dev.sh and unattended installs):
#   --certs-only        Only run cert generation; skip env/compose/udev.
#   --no-env            Skip .env seed.
#   --no-compose        Skip docker-compose.yml generation.
#   --no-udev           Skip host udev rule.
#
# See docs/arch/06-deployment.md for the full design.

set -euo pipefail

# ---------------------------------------------------------------------- args

PREFIX="${HOME}/arm"
ROTATE_CA=0
START=0
CERTS_ONLY=0
NO_ENV=0
NO_COMPOSE=0
NO_UDEV=0

ARM_IMAGE_PREFIX_DEFAULT="docker.io/automaticrippingmachine"
# GitHub repo whose latest *stable* (non-prerelease) release pins the image
# versions. Override for a fork via --release-repo or ARM_RELEASE_REPO.
ARM_RELEASE_REPO="${ARM_RELEASE_REPO:-automatic-ripping-machine/automatic-ripping-machine}"
# This installer targets ARM v3. The resolved release tag must be on this major
# line — guards against pinning the repo's latest *v2* stable (e.g. 2.x), whose
# images don't exist under the v3 arm-<svc> names. Bump when v4 lands.
ARM_EXPECTED_MAJOR="3"
# Resolved at install time from GitHub (resolve_image_tag) on a fresh install,
# or reused from an existing .env. No hardcoded fallback — a real install always
# pins a real published tag (we hard-fail rather than ship a stale default).
ARM_IMAGE_TAG_DEFAULT=""

usage() {
    cat <<EOF
ARM v3 installer.

Usage: install.sh [options]

Options:
  --prefix <path>     Install prefix (default: ~/arm)
  --rotate-ca         Regenerate the internal CA + all leaves (with confirm).
  --start             Run 'docker compose up -d' after install.
  --release-repo <owner/repo>
                      GitHub repo to resolve the latest stable image tag from
                      (default: automatic-ripping-machine/automatic-ripping-machine;
                      also settable via ARM_RELEASE_REPO).

Advanced (used by setup-dev.sh and unattended installs):
  --certs-only        Only run cert generation; skip env/compose/udev.
  --no-env            Skip .env seed.
  --no-compose        Skip docker-compose.yml generation.
  --no-udev           Skip host udev rule.
  -h, --help          This help.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix)      PREFIX="$2"; shift 2 ;;
        --prefix=*)    PREFIX="${1#*=}"; shift ;;
        --rotate-ca)   ROTATE_CA=1; shift ;;
        --start)       START=1; shift ;;
        --release-repo)   ARM_RELEASE_REPO="$2"; shift 2 ;;
        --release-repo=*) ARM_RELEASE_REPO="${1#*=}"; shift ;;
        --certs-only)  CERTS_ONLY=1; shift ;;
        --no-env)      NO_ENV=1; shift ;;
        --no-compose)  NO_COMPOSE=1; shift ;;
        --no-udev)     NO_UDEV=1; shift ;;
        -h|--help)     usage; exit 0 ;;
        *)             echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

# ------------------------------------------------------------------- helpers

log()  { printf '==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
err()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

require() {
    local bin="$1" hint="$2"
    command -v "$bin" >/dev/null 2>&1 || err "'$bin' not found. $hint"
}

# vercmp: returns 0 if $1 >= $2, 1 otherwise. Both args are dotted numerics.
# Uses sort -V for portability across distros.
vercmp_ge() {
    local lower
    lower="$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n 1)"
    [[ "$lower" = "$2" ]]
}

confirm() {
    local prompt="$1" reply
    if [[ ! -t 0 ]]; then
        # Non-interactive (piped from curl); accept on `yes |` or fail.
        read -r reply || reply="n"
    else
        read -rp "$prompt [y/N] " reply
    fi
    [[ "$reply" =~ ^[yY]([eE][sS])?$ ]]
}

# Extract the bare host from a URL: strip scheme://, any user@, :port, and /path.
# https://192.168.0.68:8080/api -> 192.168.0.68 ; https://h.example -> h.example
url_host() {
    local url="$1" hostport
    url="${url#*://}"      # drop scheme://
    url="${url%%/*}"       # drop /path
    url="${url##*@}"       # drop user@ (if present)
    hostport="$url"
    url="${hostport%%:*}"  # drop :port
    printf '%s' "$url"
}

# Resolve the image tag that pins ALL service images (backend/ripper/ui +
# the transcode image the dispatcher spawns). Reuse an existing pin from the
# prefix's .env so re-runs don't silently upgrade and work offline; otherwise
# fetch the latest *stable* (non-prerelease) release of ARM_RELEASE_REPO from
# GitHub. Hard-fail if it can't be resolved — we never ship a stale default.
resolve_image_tag() {
    local existing
    if [[ -f "$PREFIX/.env" ]]; then
        existing="$(sed -nE 's/^ARM_IMAGE_TAG=(.+)$/\1/p' "$PREFIX/.env" | head -n1)"
        if [[ -n "$existing" ]]; then
            log "reusing pinned image tag ${existing} from existing .env" >&2
            printf '%s' "$existing"
            return 0
        fi
    fi

    require curl "install curl, or pre-set ARM_IMAGE_TAG in $PREFIX/.env"
    local url="https://api.github.com/repos/${ARM_RELEASE_REPO}/releases/latest"
    local body tag
    # `releases/latest` returns the newest non-prerelease, non-draft release;
    # 404 when the repo has none. `-f` makes curl fail (non-zero) on any non-2xx.
    if ! body="$(curl -fsSL -H 'Accept: application/vnd.github+json' "$url" 2>/dev/null)"; then
        err "could not resolve a stable release tag from '${ARM_RELEASE_REPO}' (GitHub unreachable, rate-limited, or no stable release yet). Use --release-repo to point at the right repo, or pre-set ARM_IMAGE_TAG in $PREFIX/.env."
    fi
    tag="$(printf '%s' "$body" | grep -m1 '"tag_name"' | sed -E 's/.*"tag_name"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/')"
    [[ -n "$tag" ]] || err "could not parse a tag_name from '${ARM_RELEASE_REPO}' latest release."
    # Reject a tag off the expected major (e.g. the repo's latest v2 stable):
    # its v3 arm-<svc> images don't exist, so pulling would 404. Tags look like
    # `v3.0.0` or `3.0.0`; match the leading (optional-v) major.
    if [[ ! "$tag" =~ ^v?${ARM_EXPECTED_MAJOR}\. ]]; then
        err "latest stable release of '${ARM_RELEASE_REPO}' is ${tag}, not a v${ARM_EXPECTED_MAJOR} release. No v${ARM_EXPECTED_MAJOR} stable exists there yet — use --release-repo to point at a repo that has one, or pre-set ARM_IMAGE_TAG in $PREFIX/.env."
    fi
    log "pinned images to ${ARM_RELEASE_REPO}@${tag} (latest stable)" >&2
    printf '%s' "$tag"
}

# -------------------------------------------------------------- prereq check

check_prereqs() {
    log "checking prereqs"

    require docker  "install: https://docs.docker.com/engine/install/"
    require openssl "openssl should be present on any modern Linux system"
    require sed     "sed should be present on any modern Linux system"

    # bash 4+ — we use ${var,,} lowercasing, indexed array slicing, etc.
    if ! vercmp_ge "${BASH_VERSION%%[!0-9.]*}" "4.0"; then
        err "bash >= 4 required (have ${BASH_VERSION}); macOS ships bash 3.2 — install via brew."
    fi

    # docker >= 24 — ensures `docker compose` v2 is reliably present.
    local docker_ver
    docker_ver="$(docker --version 2>/dev/null | sed -E 's/^Docker version ([0-9.]+).*/\1/')"
    if [[ -z "$docker_ver" ]] || ! vercmp_ge "$docker_ver" "24.0.0"; then
        err "docker >= 24 required (have '${docker_ver:-unknown}'); please upgrade."
    fi

    # docker compose v2 plugin.
    if ! docker compose version >/dev/null 2>&1; then
        err "'docker compose' (v2 plugin) not available; install docker-compose-plugin."
    fi

    # openssl >= 1.1.1 for the SAN-injection pattern we use.
    local ossl_ver
    ossl_ver="$(openssl version 2>/dev/null | sed -E 's/^OpenSSL ([0-9.]+).*/\1/')"
    if [[ -z "$ossl_ver" ]] || ! vercmp_ge "$ossl_ver" "1.1.1"; then
        err "openssl >= 1.1.1 required (have '${ossl_ver:-unknown}')."
    fi

    # docker reachability — user is in `docker` group OR sudo works.
    if ! docker info >/dev/null 2>&1; then
        if ! sudo -n docker info >/dev/null 2>&1; then
            err "cannot reach docker daemon. Add yourself to the docker group: sudo usermod -aG docker \$USER && newgrp docker"
        fi
    fi

    # Optical group membership is a non-fatal warning; the container's
    # group_add: ["${CDROM_GID}"] handles the actual access at runtime.
    if [[ -e /dev/sr0 ]] && command -v getent >/dev/null 2>&1; then
        local cdrom_gid
        cdrom_gid="$(stat -c '%g' /dev/sr0 2>/dev/null || true)"
        if [[ -n "$cdrom_gid" ]] && ! id -G | tr ' ' '\n' | grep -qx "$cdrom_gid"; then
            warn "you are not in /dev/sr0's group (gid=$cdrom_gid). Container access works regardless via group_add; only matters if you debug a drive directly from the host."
        fi
    fi
}

# ------------------------------------------------------------- prefix layout

ensure_prefix() {
    log "ensuring install prefix at $PREFIX"
    mkdir -p "$PREFIX"/{certs,raw,media,logs,db}
    chmod 700 "$PREFIX/certs"
    # 2775 = setgid + group-writable. Per docs/arch/06-deployment.md: lets
    # ARM-created subdirs inherit the parent group automatically.
    chmod 2775 "$PREFIX/raw" "$PREFIX/media" "$PREFIX/logs"
}

# ---------------------------------------------------------- cert generation

make_ca() {
    local ca_key="$PREFIX/certs/arm-ca.key"
    local ca_crt="$PREFIX/certs/arm-ca.crt"

    if [[ -f "$ca_key" && -f "$ca_crt" ]]; then
        log "CA already exists; reusing (use --rotate-ca to regenerate)"
        return 0
    fi

    log "generating CA (EC P-384, 10y)"
    openssl ecparam -name secp384r1 -genkey -noout -out "$ca_key"
    chmod 400 "$ca_key"
    openssl req -x509 -new -nodes -key "$ca_key" -sha384 -days 3650 \
        -subj "/CN=ARM v3 Local CA" \
        -addext "basicConstraints=critical,CA:TRUE" \
        -addext "keyUsage=critical,keyCertSign,cRLSign" \
        -addext "subjectKeyIdentifier=hash" \
        -out "$ca_crt"
    chmod 444 "$ca_crt"
}

make_leaf() {
    local name="$1"; shift
    local extra_sans=("$@")
    local key="$PREFIX/certs/${name}.key"
    local csr="$PREFIX/certs/${name}.csr"
    local crt="$PREFIX/certs/${name}.crt"
    local ext="$PREFIX/certs/${name}.ext"

    log "issuing leaf: $name${extra_sans[*]:+ (extra SANs: ${extra_sans[*]})}"

    # Clear any prior 0400/0444 leaf so openssl can overwrite.
    rm -f "$key" "$crt"

    openssl ecparam -name prime256v1 -genkey -noout -out "$key"
    chmod 400 "$key"

    openssl req -new -key "$key" -subj "/CN=${name}" -out "$csr"

    local san="DNS:${name}"
    local s
    for s in "${extra_sans[@]:-}"; do
        [[ -z "$s" ]] && continue
        # IPv4 literal → IP: SAN (a remote transcoder may connect by IP);
        # anything else is a hostname → DNS:. IPv6 is out of scope.
        if [[ "$s" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
            san+=",IP:${s}"
        else
            san+=",DNS:${s}"
        fi
    done

    cat > "$ext" <<EOF
subjectAltName = ${san}
extendedKeyUsage = serverAuth, clientAuth
EOF

    openssl x509 -req -in "$csr" -CA "$PREFIX/certs/arm-ca.crt" \
        -CAkey "$PREFIX/certs/arm-ca.key" -CAcreateserial \
        -out "$crt" -days 3650 -sha384 -extfile "$ext"
    chmod 444 "$crt"

    rm -f "$csr" "$ext"
}

# --------------------------------------------------------------- drive scan

DRIVES_SR=()
DRIVES_SG=()

detect_drives() {
    log "scanning for optical drives"
    DRIVES_SR=()
    DRIVES_SG=()

    shopt -s nullglob
    local devs=(/dev/sr[0-9]*)
    shopt -u nullglob

    if [[ ${#devs[@]} -eq 0 ]]; then
        warn "no optical drives detected. Stack will install but no ripper services will be emitted."
        return 0
    fi

    local dev n sg_dir sg_name
    for dev in "${devs[@]}"; do
        n="${dev##*sr}"
        sg_dir="/sys/class/block/sr${n}/device/scsi_generic"
        if [[ ! -d "$sg_dir" ]]; then
            warn "${dev} has no scsi_generic node — MakeMKV will silently fail. Skipping."
            continue
        fi
        # shellcheck disable=SC2012  # sysfs entries are kernel-controlled "sgN"; ls is fine.
        sg_name="$(ls "$sg_dir" 2>/dev/null | head -n 1)"
        if [[ -z "$sg_name" ]]; then
            warn "${dev} has empty scsi_generic dir — skipping."
            continue
        fi
        log "  /dev/sr${n} ↔ /dev/${sg_name}"
        DRIVES_SR+=("$n")
        DRIVES_SG+=("$sg_name")
    done

    # Preserve any previously-enrolled drives (may be temporarily detached).
    # Read service names from an existing compose; union with currently-detected.
    local existing_compose="$PREFIX/docker-compose.yml"
    if [[ -f "$existing_compose" ]]; then
        local prev_n
        while IFS= read -r prev_n; do
            local seen=0 i
            for i in "${DRIVES_SR[@]:-}"; do
                [[ "$i" = "$prev_n" ]] && { seen=1; break; }
            done
            if [[ $seen -eq 0 ]]; then
                warn "  /dev/sr${prev_n} was previously enrolled but is not currently present. Block kept."
                DRIVES_SR+=("$prev_n")
                # Stale block — guess sg via ID if it returns. For now stamp
                # `sgX-MISSING` so the user notices on next compose validate.
                DRIVES_SG+=("sg-missing-sr${prev_n}")
            fi
        done < <(sed -nE 's/^  arm-ripper-sr([0-9]+):.*/\1/p' "$existing_compose")
    fi
}

# ----------------------------------------------------------------- env seed

# Minimum NVIDIA driver major version whose NVENC API satisfies the HandBrake
# build in services/transcode/Dockerfile. That Dockerfile pins nv-codec-headers
# to NVCODEC_VERSION 12.1.14.0, whose floor is driver 530.41.03. A host below
# this advertises NVENC via nvidia-smi but every GPU encode dies `rc=3` at
# `avcodec_open` ("Driver does not support the required nvenc API version"), so
# we gate it here and let such a host fall back to CPU. Keep in lockstep with the
# Dockerfile's NVCODEC_VERSION driver floor. Mirror any change in devtools/setup-dev.sh.
ARM_NVENC_MIN_DRIVER=530

# Echo `0` (advertise NVENC) or `1` (skip it) for the host's nvidia-smi driver.
# Warns via warn() (stderr) so it never pollutes detect_gpus' JSON on stdout.
nvenc_driver_ok() {
    local drv major
    drv="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)"
    major="${drv%%.*}"
    if [[ -z "$major" || ! "$major" =~ ^[0-9]+$ ]]; then
        warn "could not read NVIDIA driver version; advertising NVENC anyway"
        echo 0; return
    fi
    if (( major < ARM_NVENC_MIN_DRIVER )); then
        warn "NVIDIA driver ${drv} is too old for this build's NVENC (needs >= ${ARM_NVENC_MIN_DRIVER}.x); skipping NVENC so transcodes fall back to CPU. Upgrade the driver to enable HW encode."
        echo 1; return
    fi
    log "NVIDIA driver ${drv} detected (>= ${ARM_NVENC_MIN_DRIVER}.x); advertising NVENC" >&2
    echo 0
}

# Phase 7b: enumerate GPUs host-side so the GPU-free backend can fill the `gpus`
# table from ARM_GPUS instead of probing hardware. Prints a compact JSON array on
# stdout (empty `[]` if none). Mirrors services/backend/arm_backend/gpu_probe.py.
detect_gpus() {
    local entries=() node vendor_file vid vendor idx
    # Intel (QSV, 0x8086) / AMD (VAAPI, 0x1002) via DRM render nodes.
    if [[ -d /dev/dri ]]; then
        for node in /dev/dri/renderD*; do
            [[ -e "$node" ]] || continue
            vendor_file="/sys/class/drm/$(basename "$node")/device/vendor"
            [[ -r "$vendor_file" ]] || continue
            vid="$(tr -d '[:space:]' < "$vendor_file" | tr '[:upper:]' '[:lower:]')"
            case "$vid" in
                0x8086) vendor=qsv ;;
                0x1002) vendor=vaapi ;;
                *)      continue ;;
            esac
            entries+=("{\"vendor\":\"${vendor}\",\"device_path\":\"${node}\",\"encoder_kinds\":[\"h264\",\"h265\"]}")
        done
    fi
    # NVIDIA (NVENC) via nvidia-smi — one entry per listed GPU index. Gated on a
    # driver new enough for the shipped HandBrake NVENC build (see above).
    if command -v nvidia-smi >/dev/null 2>&1 && [[ "$(nvenc_driver_ok)" == 0 ]]; then
        while IFS= read -r idx; do
            [[ -n "$idx" ]] || continue
            entries+=("{\"vendor\":\"nvenc\",\"device_path\":\"nvidia://${idx}\",\"encoder_kinds\":[\"h264\",\"h265\"]}")
        done < <(nvidia-smi -L 2>/dev/null | sed -nE 's/^GPU ([0-9]+):.*/\1/p')
    fi
    local IFS=,
    printf '[%s]' "${entries[*]:-}"
}

# GID of the /dev/dri render-node group. The dispatcher adds it to VAAPI/QSV
# transcoders so the PUID-dropped process can open the node (root:render 0660).
# Empty if there's no render node (CPU / NVENC-only host).
detect_render_gid() {
    local node
    for node in /dev/dri/renderD*; do
        [[ -e "$node" ]] || continue
        stat -c '%g' "$node"
        return 0
    done
}

# Run GPU detection ON the remote host over ssh, using the dedicated key.
# Prints two lines: <ARM_GPUS json> then <render_gid>. Non-zero on ssh failure.
# Ships the three detection function bodies to the remote `bash -s`; the remote
# does not have install.sh, so we send the functions inline.
remote_detect_gpus() {
    local target="$1" key="$2" out
    # target is ssh://user@host — strip the scheme for the ssh CLI.
    local sshdest="${target#ssh://}"
    # shellcheck disable=SC2029 # intentional: function bodies are expanded client-side and shipped as source to the remote bash -s
    out="$(
        {
            declare -f nvenc_driver_ok detect_gpus detect_render_gid
            # shellcheck disable=SC2016 # single quotes are intentional: $(...) must expand on the remote, not here
            printf 'printf "%%s\\n" "$(detect_gpus)"\n'
            # shellcheck disable=SC2016 # single quotes are intentional: $(...) must expand on the remote, not here
            printf 'printf "%%s\\n" "$(detect_render_gid || true)"\n'
        } | ssh -i "$key" -o BatchMode=yes -o ConnectTimeout=10 \
                -o StrictHostKeyChecking=accept-new "$sshdest" bash -s 2>/dev/null
    )" || return 1
    printf '%s\n' "$out"
}

# Interactive: offer remote transcode offload. On yes, provision a dedicated
# ssh key, print the authorize line, detect the REMOTE GPU inventory, and set
# the REMOTE_* globals the rest of install.sh consumes. On no/non-interactive,
# leaves REMOTE_OFFLOAD empty => byte-for-byte local behavior downstream.
setup_remote_offload() {
    REMOTE_OFFLOAD=0
    # Non-interactive (no tty) => never prompt; stay local.
    [[ -t 0 ]] || return 0
    confirm "Enable remote transcode offload (spawn transcodes on a GPU host over ssh)?" || return 0
    REMOTE_OFFLOAD=1

    read -rp "  Remote docker endpoint (ssh://user@host): " REMOTE_DOCKER_HOST
    read -rp "  Routable backend URL the transcoder calls back (https://host:port): " REMOTE_BACKEND_URL
    local def_puid def_pgid
    def_puid="$(id -u)"; def_pgid="$(id -g)"
    local uidgid
    read -rp "  Transcoder write UID:GID for shared media [${def_puid}:${def_pgid}]: " uidgid
    uidgid="${uidgid:-${def_puid}:${def_pgid}}"
    REMOTE_TRANSCODE_PUID="${uidgid%%:*}"
    REMOTE_TRANSCODE_PGID="${uidgid##*:}"
    REMOTE_BACKEND_SAN="$(url_host "$REMOTE_BACKEND_URL")"

    # Dedicated ed25519 key for backend -> remote docker daemon.
    local sshdir="$PREFIX/ssh" key="$PREFIX/ssh/id_ed25519"
    local sshdest="${REMOTE_DOCKER_HOST#ssh://}"
    # sshdest may be user@host, user@host:port, host, or host:port. Split the
    # host from an optional :port and an optional user@ SEPARATELY: ssh-keyscan
    # takes `-p PORT HOST`, not `HOST:PORT`, so a `host:2222` endpoint would
    # otherwise keyscan-fail -> empty known_hosts -> offload silently dead.
    local hostport="${sshdest##*@}"          # strip user@ -> host[:port]
    local remote_host="${hostport%%:*}"      # bare host for keyscan + ssh config Host
    local remote_port=""
    [[ "$hostport" == *:* ]] && remote_port="${hostport##*:}"
    local remote_user=""
    [[ "$sshdest" == *@* ]] && remote_user="${sshdest%@*}"
    mkdir -p "$sshdir"
    if [[ ! -f "$key" ]]; then
        ssh-keygen -t ed25519 -N "" -C "armv3-backend@${remote_host}" -f "$key" >/dev/null
        log "generated dedicated ssh key: $key"
    fi
    # Pre-populate known_hosts (best-effort). StrictHostKeyChecking below is
    # accept-new (NOT yes) — matching remote_detect_gpus's detection path — so a
    # keyscan miss self-heals on the first real connection instead of permanently
    # disabling offload with an unusable strict-yes + empty known_hosts.
    ssh-keyscan -t ed25519 ${remote_port:+-p "$remote_port"} "$remote_host" \
        > "$sshdir/known_hosts" 2>/dev/null || \
        warn "ssh-keyscan of ${remote_host}${remote_port:+:$remote_port} failed; known_hosts seeded empty (first connect will accept-new)"
    {
        printf 'Host %s\n' "$remote_host"
        [[ -n "$remote_user" ]] && printf '  User %s\n' "$remote_user"
        [[ -n "$remote_port" ]] && printf '  Port %s\n' "$remote_port"
        printf '  IdentityFile /home/arm/.ssh/id_ed25519\n'
        printf '  UserKnownHostsFile /home/arm/.ssh/known_hosts\n'
        printf '  StrictHostKeyChecking accept-new\n'
    } > "$sshdir/config"
    chmod 700 "$sshdir"; chmod 600 "$key" "$sshdir/known_hosts" "$sshdir/config"
    # Own the ssh bundle as the BACKEND's runtime uid (this installer's own
    # id -u:id -g, i.e. top-level PUID/PGID — the entrypoint's gosu target),
    # NOT REMOTE_TRANSCODE_PUID/PGID: that's a different uid by design — the
    # one the *transcoder* drops to for writing the shared media export. The
    # backend is what mounts this dir :ro and reads the 600 key/config, so it
    # must be the owner or ssh transport fails silently.
    chown -R "${def_puid}:${def_pgid}" "$sshdir" 2>/dev/null || true

    echo
    log "Authorize this key on ${remote_host} — append the line below to ~/.ssh/authorized_keys there:"
    echo
    cat "$key.pub"
    echo
    read -rp "  Press Enter once the key is authorized on ${remote_host}... " _

    # Remote GPU detection doubles as the connectivity test (uses the dedicated key).
    REMOTE_GPUS=""; REMOTE_RENDER_GID=""
    while true; do
        local detect
        if detect="$(remote_detect_gpus "$REMOTE_DOCKER_HOST" "$key")"; then
            REMOTE_GPUS="$(printf '%s' "$detect" | sed -n '1p')"
            REMOTE_RENDER_GID="$(printf '%s' "$detect" | sed -n '2p')"
            log "remote GPUs: ${REMOTE_GPUS:-[]}  render_gid=${REMOTE_RENDER_GID:-(none)}"
            break
        fi
        warn "remote GPU detection failed (ssh to ${remote_host} — key authorized? host reachable?)"
        if ! confirm "  Re-check now? (No = skip; transcodes run CPU-only until fixed)"; then
            warn "skipping remote GPU detection; seeding ARM_GPUS=[] (CPU-only on the box)"
            REMOTE_GPUS="[]"; REMOTE_RENDER_GID=""
            break
        fi
    done
}

seed_env() {
    local env_file="$PREFIX/.env"

    local puid pgid cdrom_gid
    puid="$(id -u)"
    pgid="$(id -g)"
    cdrom_gid="$(stat -c '%g' /dev/sr0 2>/dev/null || echo 44)"

    local arm_gpus render_gid
    arm_gpus="$(detect_gpus)"
    render_gid="$(detect_render_gid || true)"

    # When offloading, the transcode host is remote: use the REMOTE inventory
    # (detected over ssh) so QSV/VAAPI get the remote render node + GID.
    if [[ "${REMOTE_OFFLOAD:-0}" == "1" && -n "${REMOTE_GPUS}" ]]; then
        arm_gpus="${REMOTE_GPUS}"
        render_gid="${REMOTE_RENDER_GID}"
    fi

    if [[ -f "$env_file" ]]; then
        log ".env exists; preserving secrets, re-deriving PUID/PGID/CDROM_GID/ARM_GPUS/ARM_RENDER_GID"
        sed -i \
            -e "s|^PUID=.*|PUID=${puid}|" \
            -e "s|^PGID=.*|PGID=${pgid}|" \
            -e "s|^CDROM_GID=.*|CDROM_GID=${cdrom_gid}|" \
            "$env_file"
        if grep -q '^ARM_GPUS=' "$env_file"; then
            sed -i "s|^ARM_GPUS=.*|ARM_GPUS=${arm_gpus}|" "$env_file"
        else
            printf 'ARM_GPUS=%s\n' "$arm_gpus" >> "$env_file"
        fi
        if grep -q '^ARM_RENDER_GID=' "$env_file"; then
            sed -i "s|^ARM_RENDER_GID=.*|ARM_RENDER_GID=${render_gid}|" "$env_file"
        else
            printf 'ARM_RENDER_GID=%s\n' "$render_gid" >> "$env_file"
        fi
        log "detected GPU(s): ${arm_gpus}  render_gid=${render_gid:-(none)}"

        # Offload keys: only touch them when offload is enabled, so declining
        # offload on an existing .env leaves it byte-for-byte untouched.
        if [[ "${REMOTE_OFFLOAD:-0}" == "1" ]]; then
            local kv key value
            for kv in \
                "ARM_TRANSCODE_DOCKER_HOST=${REMOTE_DOCKER_HOST}" \
                "ARM_TRANSCODE_BACKEND_URL=${REMOTE_BACKEND_URL}" \
                "ARM_TRANSCODE_PUID=${REMOTE_TRANSCODE_PUID}" \
                "ARM_TRANSCODE_PGID=${REMOTE_TRANSCODE_PGID}" \
                "ARM_TRANSCODE_SSH_DIR=./ssh"
            do
                key="${kv%%=*}"
                value="${kv#*=}"
                # Delete-then-append rather than `sed s|...|value|`: value is
                # free-text user input (REMOTE_DOCKER_HOST/REMOTE_BACKEND_URL), and
                # a `&` (URL query) or `|` (sed delimiter) in it would corrupt the
                # replacement. Rewriting the whole line sidesteps sed metachar hazards.
                if grep -q "^${key}=" "$env_file"; then
                    grep -v "^${key}=" "$env_file" > "$env_file.tmp" && mv "$env_file.tmp" "$env_file"
                fi
                printf '%s=%s\n' "$key" "$value" >> "$env_file"
            done
            log "seeded offload keys (ARM_TRANSCODE_DOCKER_HOST=${REMOTE_DOCKER_HOST})"
        fi

        return 0
    fi

    log "generating .env with random secrets"
    local pg_pass arm_tok
    pg_pass="$(openssl rand -hex 24)"
    arm_tok="$(openssl rand -hex 32)"

    cat > "$env_file" <<EOF
# Generated by install.sh — do not commit, do not share.
# Regenerate secrets only with care: changing POSTGRES_PASSWORD requires
# re-creating the DB; changing ARM_SERVICE_TOKEN requires restarting every
# ripper/transcoder.

POSTGRES_USER=arm
POSTGRES_PASSWORD=${pg_pass}
POSTGRES_DB=arm

ARM_SERVICE_TOKEN=${arm_tok}

PUID=${puid}
PGID=${pgid}
CDROM_GID=${cdrom_gid}

ARM_LOG_LEVEL=info

# Image registry + tag. Pins EVERY service image, including the transcode
# image the backend spawns (see ARM_TRANSCODE_IMAGE in docker-compose.yml,
# which is derived from these). Bump ARM_IMAGE_TAG to upgrade the whole stack.
ARM_IMAGE_PREFIX=${ARM_IMAGE_PREFIX_DEFAULT}
ARM_IMAGE_TAG=${ARM_IMAGE_TAG_DEFAULT}

# WebSocket Origin allowlist. Add every URL the UI is reachable at.
ARM_ALLOWED_ORIGINS=https://localhost:8081

# Phase 7: transcode dispatcher.
# ARM_TRANSCODE_IMAGE is not set here on purpose — docker-compose.yml derives it
# from ARM_IMAGE_PREFIX/ARM_IMAGE_TAG so it tracks the same version as the rest.
# Set it explicitly only to override the transcode image independently.
MAX_PARALLEL_TRANSCODES=1

# Backend's host-side mount paths. The dispatcher passes these to the docker
# daemon when spawning transcoder containers; \${PWD} resolves to the
# directory holding this compose file at parse time.
ARM_HOST_RAW_PATH=\${PWD}/raw
ARM_HOST_MEDIA_PATH=\${PWD}/media
ARM_HOST_LOGS_PATH=\${PWD}/logs
ARM_HOST_CERTS_PATH=\${PWD}/certs

# Docker network the spawned transcoder joins so it can reach the backend.
ARM_DOCKER_NETWORK=armv3_default

# Phase 7b: GPUs detected host-side at install time (see detect_gpus in
# install.sh). The GPU-free backend reads this to fill the gpus table; the
# dispatcher injects the matching device access into each ephemeral transcoder.
# Empty [] => CPU-only transcoding. Re-run install.sh after a GPU/driver change.
# NVIDIA hosts also need nvidia-container-toolkit (install.sh offers to set it up).
ARM_GPUS=${arm_gpus}

# GID of the /dev/dri render-node group. The dispatcher adds it to VAAPI/QSV
# transcoders so the PUID-dropped process can open the node (root:render 0660).
# Empty => not added (CPU / NVENC-only host).
ARM_RENDER_GID=${render_gid}
EOF

    if [[ "${REMOTE_OFFLOAD:-0}" == "1" ]]; then
        cat >> "$env_file" <<EOF

# Remote transcode offload (install.sh --). The dispatcher targets a remote
# docker daemon over ssh and spawns transcodes there; the container writes back
# to shared storage as PUID:PGID and calls the routable backend URL.
ARM_TRANSCODE_DOCKER_HOST=${REMOTE_DOCKER_HOST}
ARM_TRANSCODE_BACKEND_URL=${REMOTE_BACKEND_URL}
ARM_TRANSCODE_PUID=${REMOTE_TRANSCODE_PUID}
ARM_TRANSCODE_PGID=${REMOTE_TRANSCODE_PGID}
ARM_TRANSCODE_SSH_DIR=./ssh
EOF
    fi

    chmod 600 "$env_file"
}

# ---------------------------------------------- NVIDIA Container Toolkit setup

ensure_nvidia_container_toolkit() {
    # NVENC needs the host's nvidia-container-toolkit so the docker daemon can
    # pass GPU device files into the ephemeral transcoder. On apt hosts we offer
    # to install + register it; elsewhere we print the steps. CPU/VAAPI/QSV need
    # nothing here. Idempotent — skips when already wired up.

    # Cheap host detection: lspci has been on every Linux desktop since the 90s.
    if ! command -v lspci >/dev/null 2>&1; then
        return 0
    fi
    if ! lspci 2>/dev/null | grep -qi 'nvidia'; then
        return 0  # No NVIDIA hardware → toolkit irrelevant.
    fi
    if command -v nvidia-ctk >/dev/null 2>&1 && docker info 2>/dev/null | grep -q 'nvidia'; then
        return 0  # Already installed and registered with docker.
    fi

    if ! command -v apt-get >/dev/null 2>&1; then
        warn "NVIDIA GPU detected but nvidia-container-toolkit isn't set up (non-apt host)."
        cat >&2 <<'CTK'
    Install it for your distro, then re-run install.sh:
      https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
    After install: sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
    Skipping for now — CPU transcoding still works.
CTK
        return 0
    fi

    log "NVIDIA GPU detected; nvidia-container-toolkit enables NVENC transcoding."
    if ! confirm "Install nvidia-container-toolkit now (needs sudo)?"; then
        warn "skipping nvidia-container-toolkit — NVENC stays off until it's installed. CPU transcoding still works."
        return 0
    fi

    log "installing nvidia-container-toolkit (sudo)"
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
        | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
        | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
        | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
    sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
    log "nvidia-container-toolkit installed; docker 'nvidia' runtime registered"
}

# ---------------------------------------------------- compose generation

emit_ripper_block() {
    local n="$1" sg="$2"
    cat <<EOF

  arm-ripper-sr${n}:
    image: \${ARM_IMAGE_PREFIX:-${ARM_IMAGE_PREFIX_DEFAULT}}/arm-ripper:\${ARM_IMAGE_TAG:-${ARM_IMAGE_TAG_DEFAULT}}
    container_name: armv3-ripper-sr${n}
    hostname: arm-ripper-sr${n}
    restart: unless-stopped
    depends_on: [arm-backend]
    devices:
      - "/dev/sr${n}:/dev/sr${n}"
      - "/dev/${sg}:/dev/${sg}"
    group_add:
      - "\${CDROM_GID:-44}"
    environment:
      ARM_DRIVE_DEV: /dev/sr${n}
      ARM_BACKEND_URL: https://arm-backend:8443
      ARM_SERVICE_TOKEN: \${ARM_SERVICE_TOKEN}
      ARM_LOG_LEVEL: \${ARM_LOG_LEVEL:-info}
      PUID: \${PUID:-1000}
      PGID: \${PGID:-1000}
      CDROM_GID: \${CDROM_GID:-44}
    volumes:
      - ./raw:/raw
      - ./logs:/logs
      - ./certs/arm-ca.crt:/etc/ssl/arm/arm-ca.crt:ro
      - ./certs/arm-ripper-sr${n}.crt:/etc/ssl/arm/tls.crt:ro
      - ./certs/arm-ripper-sr${n}.key:/etc/ssl/arm/tls.key:ro
EOF
}

generate_compose() {
    local out="$PREFIX/docker-compose.yml"
    log "generating $out"

    cat > "$out" <<EOF
# Generated by install.sh — do not edit.
# Hand-edits will be clobbered the next time install.sh runs. Rerun
# install.sh after attaching new drives or upgrading.
name: armv3

services:
  arm-db:
    image: postgres:18
    container_name: armv3-db
    restart: unless-stopped
    entrypoint:
      - bash
      - -c
      - |
        install -o postgres -g postgres -m 0600 /etc/ssl/arm/tls.key /tmp/pg.key
        install -o postgres -g postgres -m 0644 /etc/ssl/arm/tls.crt /tmp/pg.crt
        exec docker-entrypoint.sh postgres \\
          -c ssl=on \\
          -c ssl_cert_file=/tmp/pg.crt \\
          -c ssl_key_file=/tmp/pg.key \\
          -c ssl_ca_file=/etc/ssl/arm/arm-ca.crt
    environment:
      POSTGRES_USER: \${POSTGRES_USER}
      POSTGRES_PASSWORD: \${POSTGRES_PASSWORD}
      POSTGRES_DB: \${POSTGRES_DB}
    volumes:
      # Postgres 18 expects the mount at /var/lib/postgresql (parent), not
      # /var/lib/postgresql/data — the image creates a versioned subdirectory.
      - ./db:/var/lib/postgresql
      - ./certs/arm-ca.crt:/etc/ssl/arm/arm-ca.crt:ro
      - ./certs/arm-db.crt:/etc/ssl/arm/tls.crt:ro
      - ./certs/arm-db.key:/etc/ssl/arm/tls.key:ro

  arm-backend:
    image: \${ARM_IMAGE_PREFIX:-${ARM_IMAGE_PREFIX_DEFAULT}}/arm-backend:\${ARM_IMAGE_TAG:-${ARM_IMAGE_TAG_DEFAULT}}
    container_name: armv3-backend
    restart: unless-stopped
    depends_on: [arm-db]
    environment:
      DATABASE_URL: postgresql://\${POSTGRES_USER}:\${POSTGRES_PASSWORD}@arm-db:5432/\${POSTGRES_DB}?sslmode=verify-full&sslrootcert=/etc/ssl/arm/arm-ca.crt
      ARM_SERVICE_TOKEN: \${ARM_SERVICE_TOKEN}
      ARM_LOG_LEVEL: \${ARM_LOG_LEVEL:-info}
      ARM_ALLOWED_ORIGINS: \${ARM_ALLOWED_ORIGINS:-}
      TLS_CERT_PATH: /etc/ssl/arm/tls.crt
      TLS_KEY_PATH: /etc/ssl/arm/tls.key
      PUID: \${PUID:-1000}
      PGID: \${PGID:-1000}
      MEDIA_ROOT: /media
      MAX_PARALLEL_TRANSCODES: \${MAX_PARALLEL_TRANSCODES:-1}
      # Derived from ARM_IMAGE_PREFIX/ARM_IMAGE_TAG exactly like the image: refs
      # above, so it tracks the same version. ARM_TRANSCODE_IMAGE in .env (if set)
      # still wins, for independent overrides.
      ARM_TRANSCODE_IMAGE: \${ARM_TRANSCODE_IMAGE:-\${ARM_IMAGE_PREFIX:-${ARM_IMAGE_PREFIX_DEFAULT}}/arm-transcode:\${ARM_IMAGE_TAG:-${ARM_IMAGE_TAG_DEFAULT}}}
      ARM_HOST_RAW_PATH: \${ARM_HOST_RAW_PATH}
      ARM_HOST_MEDIA_PATH: \${ARM_HOST_MEDIA_PATH}
      ARM_HOST_LOGS_PATH: \${ARM_HOST_LOGS_PATH}
      ARM_HOST_CERTS_PATH: \${ARM_HOST_CERTS_PATH}
      ARM_DOCKER_NETWORK: \${ARM_DOCKER_NETWORK:-armv3_default}
      ARM_GPUS: \${ARM_GPUS:-[]}
      ARM_RENDER_GID: \${ARM_RENDER_GID:-}
      ARM_TRANSCODE_DOCKER_HOST: \${ARM_TRANSCODE_DOCKER_HOST:-}
      ARM_TRANSCODE_BACKEND_URL: \${ARM_TRANSCODE_BACKEND_URL:-}
      ARM_TRANSCODE_PUID: \${ARM_TRANSCODE_PUID:-}
      ARM_TRANSCODE_PGID: \${ARM_TRANSCODE_PGID:-}
    volumes:
      - ./raw:/raw
      - ./media:/media
      - ./logs:/logs
      - ./certs/arm-ca.crt:/etc/ssl/arm/arm-ca.crt:ro
      - ./certs/arm-backend.crt:/etc/ssl/arm/tls.crt:ro
      - ./certs/arm-backend.key:/etc/ssl/arm/tls.key:ro
      - /var/run/docker.sock:/var/run/docker.sock

  arm-ui:
    image: \${ARM_IMAGE_PREFIX:-${ARM_IMAGE_PREFIX_DEFAULT}}/arm-ui:\${ARM_IMAGE_TAG:-${ARM_IMAGE_TAG_DEFAULT}}
    container_name: armv3-ui
    restart: unless-stopped
    depends_on: [arm-backend]
    ports:
      - "8081:443"
    volumes:
      - ./certs/arm-ca.crt:/etc/ssl/arm/arm-ca.crt:ro
      - ./certs/arm-ui.crt:/etc/ssl/arm/tls.crt:ro
      - ./certs/arm-ui.key:/etc/ssl/arm/tls.key:ro
EOF

    # Offload: give arm-backend the ssh key it uses to reach the remote docker
    # daemon. Injected only when enabled so a local install's compose has no
    # ssh mount at all.
    if [[ "${REMOTE_OFFLOAD:-0}" == "1" ]]; then
        # Insert the ssh mount right after the backend's docker.sock volume line.
        # The socket mount appears exactly ONCE in the file (only arm-backend
        # mounts it), so a plain awk one-pass insert is unambiguous — no need for
        # first-match sed addressing.
        local tmp="$out.tmp"
        awk '
            { print }
            $0 == "      - /var/run/docker.sock:/var/run/docker.sock" {
                print "      - ${ARM_TRANSCODE_SSH_DIR:-./ssh}:/home/arm/.ssh:ro"
            }
        ' "$out" > "$tmp" && mv "$tmp" "$out"
    fi

    # One ripper service block per detected drive.
    local i
    for i in "${!DRIVES_SR[@]}"; do
        emit_ripper_block "${DRIVES_SR[$i]}" "${DRIVES_SG[$i]}" >> "$out"
    done
}

# ----------------------------------------------------------- host udev rule

UDEV_RULE_PATH="/etc/udev/rules.d/99-arm-no-automount.rules"

build_udev_rule_content() {
    if [[ ${#DRIVES_SR[@]} -eq 0 ]]; then
        return 1
    fi

    local rule_lines=()
    local n id_path
    for n in "${DRIVES_SR[@]}"; do
        # Skip blocks for currently-absent drives (sg-missing-sr*).
        [[ ! -e "/dev/sr${n}" ]] && continue
        id_path="$(udevadm info "/dev/sr${n}" 2>/dev/null \
            | sed -nE 's|^E: ID_PATH=(.*)|\1|p' | head -n 1)"
        if [[ -z "$id_path" ]]; then
            warn "/dev/sr${n} has no ID_PATH — udev rule scoping needs a stable identifier; skipping."
            continue
        fi
        rule_lines+=("SUBSYSTEM==\"block\", KERNEL==\"sr[0-9]*\", ENV{ID_PATH}==\"${id_path}\", ENV{UDISKS_AUTO}=\"0\"")
    done

    [[ ${#rule_lines[@]} -eq 0 ]] && return 1

    cat <<HEADER
# Managed by install.sh — do not edit by hand.
# Disables host auto-mount for ARM-managed optical drives so the ripper
# container can eject after a rip. See:
#   docs/arch/06-deployment.md#host-side-auto-mount-must-be-disabled
HEADER
    printf '%s\n' "${rule_lines[@]}"
}

ensure_udev_rule() {
    if ! command -v udevadm >/dev/null 2>&1; then
        log "udevadm not on PATH — skipping host udev rule (non-Linux host?)"
        return 0
    fi

    local desired
    if ! desired="$(build_udev_rule_content)"; then
        log "no usable optical drives — skipping host udev rule"
        return 0
    fi

    if [[ -r "$UDEV_RULE_PATH" ]] && diff -q "$UDEV_RULE_PATH" <(printf '%s' "$desired") >/dev/null 2>&1; then
        log "host udev rule already current at $UDEV_RULE_PATH"
        return 0
    fi

    if ! sudo -n true 2>/dev/null && [[ ! -w "$UDEV_RULE_PATH" && ! -w /etc/udev/rules.d ]]; then
        warn "sudo not available — cannot write $UDEV_RULE_PATH automatically."
        echo "    Install manually as root:" >&2
        echo "    cat > $UDEV_RULE_PATH <<'EOF'" >&2
        echo "$desired" >&2
        echo "    EOF" >&2
        echo "    sudo udevadm control --reload-rules && sudo udevadm trigger" >&2
        return 0
    fi

    log "writing host udev rule at $UDEV_RULE_PATH (sudo)"
    printf '%s' "$desired" | sudo tee "$UDEV_RULE_PATH" >/dev/null
    sudo udevadm control --reload-rules
    sudo udevadm trigger --subsystem-match=block 2>/dev/null || sudo udevadm trigger
    log "udev rule installed; udisks2 will skip auto-mount for ARM drives"
}

# -------------------------------------------------------------- next steps

print_next_steps() {
    cat <<EOF

==> install complete

Prefix:   $PREFIX
Drives:   ${#DRIVES_SR[@]} ripper service(s) configured
Image:    $ARM_IMAGE_PREFIX_DEFAULT/arm-<svc>:$ARM_IMAGE_TAG_DEFAULT
          (latest stable from $ARM_RELEASE_REPO; bump ARM_IMAGE_TAG in .env to change)

Next:
  cd $PREFIX
  docker compose pull
  docker compose up -d

First-boot admin credentials (you'll be forced to change the password):
  docker exec armv3-backend cat /logs/first-boot.log

Then open: https://localhost:8081
  (Import $PREFIX/certs/arm-ca.crt into your browser/OS trust store
   to silence the cert warning across every device on the LAN.)

GPU host? GPUs are auto-detected into ARM_GPUS in $PREFIX/.env and the
backend wires them to the transcoder automatically. Re-run install.sh after
adding/removing a GPU or updating drivers. (NVIDIA hosts: install.sh offered
to set up nvidia-container-toolkit above.)

EOF
}

# ----------------------------------------------------------------- main

main() {
    check_prereqs
    ensure_prefix

    local REMOTE_OFFLOAD=0 REMOTE_DOCKER_HOST="" REMOTE_BACKEND_URL="" \
          REMOTE_TRANSCODE_PUID="" REMOTE_TRANSCODE_PGID="" REMOTE_BACKEND_SAN="" \
          REMOTE_GPUS="" REMOTE_RENDER_GID=""
    setup_remote_offload

    if [[ $ROTATE_CA -eq 1 ]]; then
        log "ROTATE_CA: this regenerates the CA + every leaf"
        if ! confirm "WARNING: every LAN client must re-import arm-ca.crt. Continue?"; then
            err "aborted"
        fi
        rm -f "$PREFIX/certs/arm-ca.key" "$PREFIX/certs/arm-ca.crt"
    fi

    make_ca
    if [[ "$REMOTE_OFFLOAD" == "1" && -n "$REMOTE_BACKEND_SAN" ]]; then
        make_leaf arm-backend "$REMOTE_BACKEND_SAN"
    else
        make_leaf arm-backend
    fi
    make_leaf arm-db
    make_leaf arm-ui localhost "$(hostname -f 2>/dev/null || hostname || echo localhost)"

    detect_drives
    local n
    for n in "${DRIVES_SR[@]:-}"; do
        [[ -z "$n" ]] && continue
        make_leaf "arm-ripper-sr${n}"
    done

    if [[ $CERTS_ONLY -eq 1 ]]; then
        log "certs-only mode; skipping env/compose/udev"
        return 0
    fi

    # Pin image versions before seeding env / generating compose (both bake the
    # tag). Resolved from GitHub on a fresh install; reused from .env otherwise.
    if [[ $NO_ENV -eq 0 || $NO_COMPOSE -eq 0 ]]; then
        ARM_IMAGE_TAG_DEFAULT="$(resolve_image_tag)"
    fi

    ensure_nvidia_container_toolkit
    [[ $NO_ENV -eq 0 ]]     && seed_env
    [[ $NO_COMPOSE -eq 0 ]] && generate_compose
    [[ $NO_UDEV -eq 0 ]]    && ensure_udev_rule

    print_next_steps

    if [[ $START -eq 1 ]]; then
        log "starting stack"
        ( cd "$PREFIX" && docker compose pull && docker compose up -d )
    fi
}

main "$@"
