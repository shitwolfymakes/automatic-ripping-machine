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

ARM_IMAGE_TAG_DEFAULT="v3.0.0-alpha-1"
ARM_IMAGE_PREFIX_DEFAULT="docker.io/automaticrippingmachine"

usage() {
    cat <<EOF
ARM v3 installer.

Usage: install.sh [options]

Options:
  --prefix <path>     Install prefix (default: ~/arm)
  --rotate-ca         Regenerate the internal CA + all leaves (with confirm).
  --start             Run 'docker compose up -d' after install.

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
        san+=",DNS:${s}"
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

seed_env() {
    local env_file="$PREFIX/.env"

    local puid pgid cdrom_gid
    puid="$(id -u)"
    pgid="$(id -g)"
    cdrom_gid="$(stat -c '%g' /dev/sr0 2>/dev/null || echo 44)"

    if [[ -f "$env_file" ]]; then
        log ".env exists; preserving secrets, re-deriving PUID/PGID/CDROM_GID"
        sed -i \
            -e "s|^PUID=.*|PUID=${puid}|" \
            -e "s|^PGID=.*|PGID=${pgid}|" \
            -e "s|^CDROM_GID=.*|CDROM_GID=${cdrom_gid}|" \
            "$env_file"
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

# Image registry + tag. Bump ARM_IMAGE_TAG to upgrade.
ARM_IMAGE_PREFIX=${ARM_IMAGE_PREFIX_DEFAULT}
ARM_IMAGE_TAG=${ARM_IMAGE_TAG_DEFAULT}

# Optional API keys; primarily set via the UI Settings page.
OMDB_API_KEY=

# WebSocket Origin allowlist. Add every URL the UI is reachable at.
ARM_ALLOWED_ORIGINS=https://localhost:8081

# Phase 7: transcode dispatcher.
MAX_PARALLEL_TRANSCODES=1
ARM_TRANSCODE_IMAGE=${ARM_IMAGE_PREFIX_DEFAULT}/arm-transcode:${ARM_IMAGE_TAG_DEFAULT}

# Backend's host-side mount paths. The dispatcher passes these to the docker
# daemon when spawning transcoder containers; \${PWD} resolves to the
# directory holding this compose file at parse time.
ARM_HOST_RAW_PATH=\${PWD}/raw
ARM_HOST_MEDIA_PATH=\${PWD}/media
ARM_HOST_LOGS_PATH=\${PWD}/logs
ARM_HOST_CERTS_PATH=\${PWD}/certs

# Docker network the spawned transcoder joins so it can reach the backend.
ARM_DOCKER_NETWORK=armv3_default

# Phase 7b: GPU transcoding (optional).
# Uncomment to load docker-compose.gpu.yml as an overlay automatically; the
# base compose stays CPU-only otherwise. NVIDIA hosts also need
# nvidia-container-toolkit installed (see .env.example for the apt commands).
# COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml
EOF
    chmod 600 "$env_file"
}

# ---------------------------------------------------- CTK detection (advisory)

check_nvidia_container_toolkit() {
    # Warn (don't fail) when the host has an NVIDIA GPU but the
    # nvidia-container-toolkit isn't registered with docker. Without the
    # toolkit, `docker compose -f docker-compose.gpu.yml up` fails with
    # "could not select device driver \"nvidia\"" — installable, but most
    # users won't connect that error to "you need an extra package."

    # Cheap host detection: lspci has been on every Linux desktop since the 90s.
    if ! command -v lspci >/dev/null 2>&1; then
        return 0
    fi
    if ! lspci 2>/dev/null | grep -qi 'nvidia'; then
        return 0  # No NVIDIA hardware → CTK irrelevant.
    fi

    if docker info 2>/dev/null | grep -q 'nvidia'; then
        return 0  # `Runtimes:` line lists `nvidia` → CTK already wired up.
    fi

    warn "NVIDIA GPU detected but the docker 'nvidia' runtime isn't registered."
    cat >&2 <<'CTK'
    For NVENC transcoding you'll want nvidia-container-toolkit. Install:

      curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
          | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
      curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
          | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
          | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
      sudo apt update && sudo apt install -y nvidia-container-toolkit
      sudo nvidia-ctk runtime configure --runtime=docker
      sudo systemctl restart docker

    Then uncomment COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml in
    your .env. Skipping for now — CPU transcoding still works.
CTK
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
      OMDB_API_KEY: \${OMDB_API_KEY:-}
      ARM_ALLOWED_ORIGINS: \${ARM_ALLOWED_ORIGINS:-}
      TLS_CERT_PATH: /etc/ssl/arm/tls.crt
      TLS_KEY_PATH: /etc/ssl/arm/tls.key
      PUID: \${PUID:-1000}
      PGID: \${PGID:-1000}
      MEDIA_ROOT: /media
      MAX_PARALLEL_TRANSCODES: \${MAX_PARALLEL_TRANSCODES:-1}
      ARM_TRANSCODE_IMAGE: \${ARM_TRANSCODE_IMAGE:-${ARM_IMAGE_PREFIX_DEFAULT}/arm-transcode:${ARM_IMAGE_TAG_DEFAULT}}
      ARM_HOST_RAW_PATH: \${ARM_HOST_RAW_PATH}
      ARM_HOST_MEDIA_PATH: \${ARM_HOST_MEDIA_PATH}
      ARM_HOST_LOGS_PATH: \${ARM_HOST_LOGS_PATH}
      ARM_HOST_CERTS_PATH: \${ARM_HOST_CERTS_PATH}
      ARM_DOCKER_NETWORK: \${ARM_DOCKER_NETWORK:-armv3_default}
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

    # One ripper service block per detected drive.
    local i
    for i in "${!DRIVES_SR[@]}"; do
        emit_ripper_block "${DRIVES_SR[$i]}" "${DRIVES_SG[$i]}" >> "$out"
    done
}

generate_compose_gpu() {
    local out="$PREFIX/docker-compose.gpu.yml"
    log "generating $out (overlay; load with -f docker-compose.yml -f docker-compose.gpu.yml)"
    cat > "$out" <<'EOF'
# Generated by install.sh — GPU transcoding overlay.
#
# Run with:
#   docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
#
# CPU-only host? Don't use this overlay. The base compose runs on CPU.
#
# Trim for your hardware:
# - VAAPI/QSV-only host (no NVIDIA): strip `runtime: nvidia` and the entire
#   `deploy:` block.
# - NVIDIA-only host: strip the `devices:` line.
# - Mixed host: leave everything; the probe handles each path independently.

services:
  arm-backend:
    devices:
      - /dev/dri:/dev/dri:ro
    runtime: nvidia
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu, video]
EOF
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

Next:
  cd $PREFIX
  docker compose pull         # NB: alpha/beta tags may not yet be published
  docker compose up -d

First-boot admin credentials (you'll be forced to change the password):
  docker exec armv3-backend cat /logs/first-boot.log

Then open: https://localhost:8081
  (Import $PREFIX/certs/arm-ca.crt into your browser/OS trust store
   to silence the cert warning across every device on the LAN.)

GPU host? Uncomment the COMPOSE_FILE line in $PREFIX/.env so the GPU
overlay loads automatically (NVIDIA hosts also need nvidia-container-
toolkit — see .env for the install commands).

Heads-up: $ARM_IMAGE_TAG_DEFAULT is a pre-release tag. Until Phase 14 (CI
+ image release) lands, 'docker compose pull' may 404. To run today, build
images locally from a local checkout and tag them — see README.md.

EOF
}

# ----------------------------------------------------------------- main

main() {
    check_prereqs
    check_nvidia_container_toolkit
    ensure_prefix

    if [[ $ROTATE_CA -eq 1 ]]; then
        log "ROTATE_CA: this regenerates the CA + every leaf"
        if ! confirm "WARNING: every LAN client must re-import arm-ca.crt. Continue?"; then
            err "aborted"
        fi
        rm -f "$PREFIX/certs/arm-ca.key" "$PREFIX/certs/arm-ca.crt"
    fi

    make_ca
    make_leaf arm-backend
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

    [[ $NO_ENV -eq 0 ]]     && seed_env
    [[ $NO_COMPOSE -eq 0 ]] && { generate_compose; generate_compose_gpu; }
    [[ $NO_UDEV -eq 0 ]]    && ensure_udev_rule

    print_next_steps

    if [[ $START -eq 1 ]]; then
        log "starting stack"
        ( cd "$PREFIX" && docker compose pull && docker compose up -d )
    fi
}

main "$@"
