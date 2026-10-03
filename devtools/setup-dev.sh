#!/usr/bin/env bash
# shellcheck disable=SC2034  # sets the flags and settings deploy/lib/*.sh reads
# One-shot dev-environment setup for the walking skeleton, and the stack's
# up/down entry point.
# Idempotent — rerunning skips work already done and leaves existing .env alone.
#
# Usage:  bash devtools/setup-dev.sh          # dev setup (uv sync, npm ci, certs, .env)
#         bash devtools/setup-dev.sh up       # deploy: certs + .env, build, refuse if a
#                                             # rip/transcode is ACTIVE (unless --force),
#                                             # back up the DB, then (re)start the stack
#                                             # + health wait
#         bash devtools/setup-dev.sh down     # stop the stack + spawned containers
#
# Roles: `setup` is the dev bootstrap and needs the dev toolchain (uv, node,
# npm). `up` and `down` are the deploy/lifecycle driver and need only docker +
# the compose plugin (plus openssl for first-run secrets and certs); they never
# touch the host venv or node_modules.
#
#         --no-backup     # `up` only: skip the pre-deploy pg_dump of the running
#                          # arm-db into ./arm/backups/. Without it, a failed or
#                          # empty backup aborts the deploy before anything is
#                          # removed or restarted. Rotation keeps the newest 5
#                          # script-made pg-backup-<UTC>.sql.gz files (e.g.
#                          # pg-backup-20260926T120000Z.sql.gz) and prunes only
#                          # older files of exactly that shape; any other file
#                          # (e.g. a manual pg-backup-pre-*.sql.gz) is never touched.
#         --force         # `up` only: replace backend-spawned containers even
#                          # while they have ACTIVE work (a running transcoder,
#                          # or a ripper running makemkvcon, abcde or dd).
#                          # Without it, `up` refuses and lists them. Idle
#                          # rippers are always replaced without --force.
#         --ripper-only   # ripper-only profile: skip every arm-transcode
#                          # image build (base, intel, amd) and host GPU
#                          # detection; write ARM_TRANSCODE_CAPABLE=false to
#                          # .env (ARM_GPUS is written as `[]`). Combine with
#                          # any action, e.g. `setup-dev.sh up --ripper-only`.
#                          # Not sticky: every run WITHOUT the flag writes
#                          # ARM_TRANSCODE_CAPABLE=true and (with `up`) builds
#                          # the arm-transcode image, so re-running without it
#                          # is how a ripper-only box becomes transcode-capable.
#
# Host overlays (NFS repoints, port changes, remote-transcode env) layer in via
# COMPOSE_FILE in the repo-root .env — docker compose reads it natively, so this
# script needs no per-host knowledge.
set -euo pipefail

# uv (and other per-user tools) install into ~/.local/bin, which only a login
# or interactive shell puts on PATH. A non-interactive run (ssh host 'bash
# devtools/setup-dev.sh up') would otherwise not find them; same idea as
# load_nvm below.
export PATH="${HOME}/.local/bin:${PATH}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

usage() {
    cat <<'USAGE'
Usage: bash devtools/setup-dev.sh [setup|up|down] [--ripper-only] [--no-backup] [--force]

  setup (default)  dev bootstrap: uv sync, npm ci, certs, .env (needs uv, node, npm)
  up               deploy: certs + .env, build images, refuse while a rip or
                   transcode is ACTIVE (override: --force), back up the running
                   DB, (re)start the stack, wait for the backend health check
                   (needs docker + the compose plugin; no uv/node/npm)
  down             stop the stack + backend-spawned ripper/transcoder containers

  --ripper-only    skip every arm-transcode image and GPU detection; write
                   ARM_TRANSCODE_CAPABLE=false (per run, not sticky)

  Transcode images on `up`: arm-transcode (base: CPU + NVENC) is always built;
  the arm-transcode-intel / arm-transcode-amd variants are built only when an
  Intel (qsv) / AMD (vaapi) GPU is detected on this host, and never when
  ARM_TRANSCODE_DOCKER_HOST is set (the remote host builds its own).
  --no-backup      up: skip the pre-deploy pg_dump into ./arm/backups/
                   (without it: the newest 5 pg-backup-<UTC>.sql.gz files, e.g.
                   pg-backup-20260926T120000Z.sql.gz, are kept and older ones of
                   exactly that shape pruned; other files such as
                   pg-backup-pre-*.sql.gz are never touched)
  --force          up: replace spawned containers even with ACTIVE work (a
                   running transcoder, or a ripper running makemkvcon, abcde
                   or dd); idle rippers never need it
USAGE
}

RIPPER_ONLY=0
NO_BACKUP=0
FORCE=0
ACTION="setup"
for arg in "$@"; do
    case "${arg}" in
        --ripper-only) RIPPER_ONLY=1 ;;
        --no-backup) NO_BACKUP=1 ;;
        --force) FORCE=1 ;;
        setup|up|down) ACTION="${arg}" ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            exit 2
            ;;
    esac
done

# Runtime/data dirs (db, raw, media, logs, certs) live under ./arm/ to keep the
# repo root tidy — the dev mirror of production's ~/arm prefix. The compose file
# and .env still live in the repo root (dev builds from `context: .`).
ARM_DIR="${ROOT_DIR}/arm"

# Compose SERVICE names from docker-compose.yml.example (not container names,
# which an overlay may change). Everything below addresses them through
# `compose`, so COMPOSE_FILE overlays and a repointed data prefix still apply.
DB_SERVICE="arm-db"
BACKEND_SERVICE="arm-backend"
UI_SERVICE="arm-ui"

# Shared deploy library: the same functions deploy/armctl.sh (the production
# launcher) uses. The settings below are this script's side of that contract.
ARM_COMPOSE_CWD="${ROOT_DIR}"
ARM_COMPOSE_CMD=(docker compose)
ARM_CERTS_DIR="${ARM_DIR}/certs"
ARM_HINT_FORCE_CMD="bash devtools/setup-dev.sh up --force"
ARM_HINT_IMAGES_READY="Images are built"
ARM_HINT_LOGS_CMD="docker compose logs"
ARM_HINT_RIPPER_ONLY="--ripper-only"
ARM_UDEV_MANAGED_BY="devtools/setup-dev.sh"
for lib in common detect certs udev lifecycle; do
    # shellcheck source=/dev/null
    source "${ROOT_DIR}/deploy/lib/${lib}.sh"
done

if [[ "${ACTION}" == "down" ]]; then
    require docker "Install docker first."
    require_compose
    remove_spawned_containers
    remove_retired_services
    echo "==> stopping the compose stack"
    compose down
    exit 0
fi

# Load nvm if the user manages Node that way. nvm only wires `node`/`npm` onto
# PATH in interactive shells, so a non-interactive `bash devtools/setup-dev.sh`
# wouldn't see them; sourcing nvm.sh here fixes that and pins the version to
# services/ui-neu/frontend/.nvmrc so the host toolchain matches the container build.
load_nvm() {
    local nvm_sh="${NVM_DIR:-${HOME}/.nvm}/nvm.sh"
    [[ -s "${nvm_sh}" ]] || return 0   # no nvm install — fall through to PATH + require
    echo "==> nvm detected; loading Node from services/ui-neu/frontend/.nvmrc"
    local want
    want="$(cat "${ROOT_DIR}/services/ui-neu/frontend/.nvmrc" 2>/dev/null || true)"
    # nvm.sh isn't written for `set -eu`; relax around the load + select, then restore.
    set +eu
    # shellcheck disable=SC1090
    . "${nvm_sh}"
    if [[ -n "${want}" ]]; then
        nvm install "${want}" && nvm use "${want}"
    fi
    set -eu
}

# Prereqs. Every action needs docker + the compose plugin; openssl mints the
# first-run .env secrets and the certs. Certificates come from
# deploy/lib/certs.sh. The dev toolchain (uv, node, npm) is `setup`-only: `up`
# builds everything inside images and must not need or mutate a host venv /
# node_modules.
require docker  "install: https://docs.docker.com/engine/install/"
require_compose
require openssl "openssl should be present on any linux system"

if [[ "${ACTION}" == "setup" ]]; then
    require uv      "install: curl -LsSf https://astral.sh/uv/install.sh | sh"

    # nvm users: pull Node onto PATH (and pin it to .nvmrc) before the checks below.
    load_nvm

    require node    "install Node 26 (matches services/ui-neu/frontend/.nvmrc / Dockerfile): https://nodejs.org/ (or 'nvm install' if you use nvm)"
    require npm     "npm ships with Node — reinstall Node, or run 'nvm use', if it's missing"

    echo "==> syncing host venv via uv"
    ( cd "${ROOT_DIR}" && uv sync )

    # UI deps from the committed lockfile (same as services/ui-neu/Dockerfile, which
    # builds on node:26). npm ci wipes node_modules and reinstalls exactly what
    # package-lock.json pins, so guard it: npm writes node_modules/.package-lock.json
    # on install, and a `git pull` that updates the lockfile makes it newer again.
    UI_DIR="${ROOT_DIR}/services/ui-neu/frontend"
    if [[ -d "${UI_DIR}/node_modules" \
          && "${UI_DIR}/node_modules/.package-lock.json" -nt "${UI_DIR}/package-lock.json" ]]; then
        echo "==> UI deps already current — skipping npm ci"
    else
        echo "==> installing UI deps via npm ci"
        ( cd "${UI_DIR}" && npm ci --no-audit --no-fund )
    fi
fi

# Create the data-dir tree under ./arm/ (mirrors install.sh's ensure_prefix:
# setgid + group-writable on the ARM-written dirs so spawned containers inherit
# the group). Idempotent; pre-creating avoids docker bind-mounting root-owned
# source dirs into the PUID-dropped containers.
echo "==> ensuring data dirs under ${ARM_DIR}"
mkdir -p "${ARM_DIR}"/{certs,raw,media,logs,db,scripts,iso-library}
chmod 700 "${ARM_DIR}/certs"
chmod 2775 "${ARM_DIR}/raw" "${ARM_DIR}/media" "${ARM_DIR}/logs"

if [[ -f "${ARM_DIR}/certs/arm-ca.crt" ]]; then
    echo "==> certs already present in arm/certs/ — skipping bootstrap"
else
    echo "==> generating internal CA + leaves"
    ensure_ca
    make_leaf arm-backend
    make_leaf arm-db
    make_leaf arm-ui localhost "$(hostname -f 2>/dev/null || hostname || echo localhost)"
fi

# docker-compose.yml is generated per host (gitignored, like .env): bootstrap
# it from the committed docker-compose.yml.example template. Drives are NOT
# enumerated here: the backend's scanner finds them and the operator enrolls
# from the UI (drive lifecycle spec §5).
COMPOSE_FILE_PATH="${ROOT_DIR}/docker-compose.yml"
COMPOSE_TEMPLATE_PATH="${ROOT_DIR}/docker-compose.yml.example"

generate_compose() {
    # The dev compose is a generated artifact (gitignored, like .env): always
    # regenerate it from the committed template so static services stay in
    # sync — knobs live in .env, so there are no hand-edits to preserve.
    # Drives are NOT enumerated here: the backend's scanner finds them and the
    # operator enrolls from the UI (drive lifecycle spec §5).
    if [[ ! -f "${COMPOSE_TEMPLATE_PATH}" ]]; then
        echo "ERROR: ${COMPOSE_TEMPLATE_PATH} missing; cannot create docker-compose.yml." >&2
        exit 1
    fi
    echo "==> generating docker-compose.yml from docker-compose.yml.example"
    cp "${COMPOSE_TEMPLATE_PATH}" "${COMPOSE_FILE_PATH}"
}

generate_compose

ENV_FILE="${ROOT_DIR}/.env"
if [[ -f "${ENV_FILE}" ]]; then
    echo "==> ${ENV_FILE} exists — preserving secrets, refreshing ARM_GPUS"
else
    echo "==> creating .env from .env.example with generated secrets"
    pg_pass="$(openssl rand -hex 24)"
    arm_tok="$(openssl rand -hex 32)"
    puid="$(id -u)"
    pgid="$(id -g)"
    cdrom_gid="$(detect_cdrom_gid)"

    sed \
        -e "s|change-me-openssl-rand-hex-24|${pg_pass}|" \
        -e "s|change-me-openssl-rand-hex-32|${arm_tok}|" \
        -e "s|^PUID=.*|PUID=${puid}|" \
        -e "s|^PGID=.*|PGID=${pgid}|" \
        -e "s|^CDROM_GID=.*|CDROM_GID=${cdrom_gid}|" \
        "${ROOT_DIR}/.env.example" > "${ENV_FILE}"
    chmod 600 "${ENV_FILE}"
fi

# ARM_GPUS: `setup` refreshes it here; `up` defers the .env write until after
# its active-work guard so a refused run leaves .env untouched.
if [[ "${ACTION}" == "setup" ]]; then
    refresh_arm_gpus
fi

# Render-node group for VAAPI/QSV device access (set-or-append, like ARM_GPUS,
# and skipped for the same reason when transcode runs on a remote host).
if grep -qE '^ARM_TRANSCODE_DOCKER_HOST=..*' "${ENV_FILE}"; then
    echo "==> ARM_TRANSCODE_DOCKER_HOST set — keeping .env's ARM_RENDER_GID"
else
    RENDER_GID_VALUE="$(detect_render_gid || true)"
    if grep -q '^ARM_RENDER_GID=' "${ENV_FILE}"; then
        sed -i "s|^ARM_RENDER_GID=.*|ARM_RENDER_GID=${RENDER_GID_VALUE}|" "${ENV_FILE}"
    else
        printf 'ARM_RENDER_GID=%s\n' "${RENDER_GID_VALUE}" >> "${ENV_FILE}"
    fi
    echo "==> detected render group GID for ARM_RENDER_GID: ${RENDER_GID_VALUE:-(none)}"
fi

# ARM_TRANSCODE_CAPABLE is derived from the flag on every run (like ARM_GPUS),
# not preserved like a secret: --ripper-only writes `false`, a run without it
# writes `true`. Re-running without the flag is the supported way to turn a
# ripper-only box back into a transcode-capable one (it also builds the
# arm-transcode image on `up`); the Settings toggle then switches encode work on.
if [[ "${RIPPER_ONLY}" -eq 1 ]]; then
    ARM_TRANSCODE_CAPABLE_VALUE=false
    echo "==> --ripper-only: writing ARM_TRANSCODE_CAPABLE=false"
else
    ARM_TRANSCODE_CAPABLE_VALUE=true
    echo "==> writing ARM_TRANSCODE_CAPABLE=true (pass --ripper-only for a ripper-only install)"
fi
if grep -q '^ARM_TRANSCODE_CAPABLE=' "${ENV_FILE}"; then
    sed -i "s|^ARM_TRANSCODE_CAPABLE=.*|ARM_TRANSCODE_CAPABLE=${ARM_TRANSCODE_CAPABLE_VALUE}|" "${ENV_FILE}"
elif grep -q '^#ARM_TRANSCODE_CAPABLE=' "${ENV_FILE}"; then
    sed -i "s|^#ARM_TRANSCODE_CAPABLE=.*|ARM_TRANSCODE_CAPABLE=${ARM_TRANSCODE_CAPABLE_VALUE}|" "${ENV_FILE}"
else
    printf 'ARM_TRANSCODE_CAPABLE=%s\n' "${ARM_TRANSCODE_CAPABLE_VALUE}" >> "${ENV_FILE}"
fi

# The transcode images are built by `up`'s `compose build` like every other
# service (the arm-transcode* services have deploy.replicas:0: built, never
# run). select_up_services decides which of them to build: base always (except
# --ripper-only), the intel/amd variants only for GPU vendors found on this host.

ensure_udev_rule

if [[ "${ACTION}" == "up" ]]; then
    # 1. Build first. A failed build aborts here (set -e) with the running
    #    stack, its rippers and transcoders untouched. The service list comes
    #    from GPU detection (read-only; .env is written in step 3).
    select_up_services
    # shellcheck disable=SC2153  # UP_SERVICES is set by select_up_services (deploy/lib/lifecycle.sh)
    if [[ ${#UP_SERVICES[@]} -gt 0 ]]; then
        echo "==> building images: ${UP_SERVICES[*]}"
        compose build "${UP_SERVICES[@]}"
    else
        echo "==> building images"
        compose build
    fi

    # 2. Refuse (unless --force) while a rip or transcode is ACTIVE. This runs
    #    before anything else changes, so a refused run leaves no side effects
    #    beyond the built images.
    guard_running_spawned

    # 3. Write the detected GPUs to .env as ARM_GPUS.
    refresh_arm_gpus

    # 4. Back up the running database before migrations can touch it.
    backup_db

    # 5. Only now remove backend-spawned rippers/transcoders, and containers of
    #    services this stack no longer defines (they would hold their ports).
    #    Note the backend's start time first, to tell whether step 6 restarts it.
    BACKEND_STARTED_BEFORE="$(backend_started_at)"
    remove_spawned_containers
    remove_retired_services

    # 6. Start from the images built above (no --build). An explicit service
    #    list keeps `up` from building a skipped image that does not exist yet.
    echo "==> starting the stack"
    if [[ ${#UP_SERVICES[@]} -gt 0 ]]; then
        compose up -d "${UP_SERVICES[@]}"
    else
        compose up -d
    fi
    respawn_rippers_if_needed "${BACKEND_STARTED_BEFORE}"

    # 7. Wait for the backend to answer its health check.
    wait_for_backend

    UI_URL="$(published_url "${UI_SERVICE}" 443)"
    UI_URL="${UI_URL:-https://localhost:8081}"
    cat <<EOF

stack is up; ${HEALTH_RESULT}
open ${UI_URL} and follow the setup walkthrough (drives, keys, defaults)
(spin it down with: bash devtools/setup-dev.sh down)

  optional — trust the local CA so browsers/curl skip the self-signed warning:
    bash devtools/trust-ca.sh
EOF
    exit 0
fi

cat <<EOF

done — next:
  bash devtools/setup-dev.sh up      # build, back up the DB, (re)start the stack, wait for health
                                     # (or: docker compose up -d --build; no backup or health wait)
  then open https://localhost:8081 and follow the setup walkthrough (drives, keys, defaults)
  spin it down (stack + spawned ripper/transcoder containers): bash devtools/setup-dev.sh down

  optional — trust the local CA so browsers/curl skip the self-signed warning:
    bash devtools/trust-ca.sh

IDE: point your interpreter at ${ROOT_DIR}/.venv/bin/python
EOF
