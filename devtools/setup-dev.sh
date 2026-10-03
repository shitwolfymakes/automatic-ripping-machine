#!/usr/bin/env bash
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
UI_SERVICE="arm-ui-neu"

require() {
    local bin="$1"
    local hint="$2"
    if ! command -v "${bin}" >/dev/null 2>&1; then
        echo "ERROR: '${bin}' not found. ${hint}" >&2
        exit 1
    fi
}

compose() {
    (cd "${ROOT_DIR}" && docker compose "$@")
}

require_compose() {
    if ! docker compose version >/dev/null 2>&1; then
        echo "ERROR: 'docker compose' (v2 plugin) not available" >&2
        exit 1
    fi
}

# The backend spawns one ripper container per enrolled drive (label
# `arm.drive_id`, ripper_manager.py) and one transcoder per local task (label
# `arm.task_id`, transcode_dispatcher.py). They are not compose services, so
# `docker compose down` leaves them behind — still holding the old image, the
# compose network, and the optical device nodes across a redeploy.
remove_spawned_containers() {
    local ids
    ids="$( { docker ps -aq --filter "label=arm.drive_id"; docker ps -aq --filter "label=arm.task_id"; } | sort -u )"
    if [[ -n "${ids}" ]]; then
        echo "==> removing backend-spawned ripper/transcoder containers"
        # shellcheck disable=SC2086  # ids is a list of container ids by design
        docker rm -f ${ids} >/dev/null
    else
        echo "==> no backend-spawned ripper/transcoder containers to remove"
    fi
}

if [[ "${ACTION}" == "down" ]]; then
    require docker "Install docker first."
    require_compose
    remove_spawned_containers
    echo "==> stopping the compose stack"
    compose down
    exit 0
fi

# Load nvm if the user manages Node that way. nvm only wires `node`/`npm` onto
# PATH in interactive shells, so a non-interactive `bash devtools/setup-dev.sh`
# wouldn't see them; sourcing nvm.sh here fixes that and pins the version to
# services/ui/.nvmrc so the host toolchain matches the container build.
load_nvm() {
    local nvm_sh="${NVM_DIR:-${HOME}/.nvm}/nvm.sh"
    [[ -s "${nvm_sh}" ]] || return 0   # no nvm install — fall through to PATH + require
    echo "==> nvm detected — loading Node from services/ui/.nvmrc"
    local want
    want="$(cat "${ROOT_DIR}/services/ui/.nvmrc" 2>/dev/null || true)"
    # nvm.sh isn't written for `set -eu`; relax around the load + select, then restore.
    set +eu
    # shellcheck disable=SC1090
    . "${nvm_sh}"
    if [[ -n "${want}" ]]; then
        nvm install "${want}" && nvm use "${want}"
    fi
    set -eu
}

# Minimum NVIDIA driver major version whose NVENC API satisfies the HandBrake
# build in services/transcode/Dockerfile. That Dockerfile pins nv-codec-headers
# to NVCODEC_VERSION 12.1.14.0, whose floor is driver 530.41.03. A host below
# this advertises NVENC via nvidia-smi but every GPU encode dies `rc=3` at
# `avcodec_open` ("Driver does not support the required nvenc API version");
# gating here makes such a host fall back to CPU instead. Keep in lockstep with
# the Dockerfile's NVCODEC_VERSION driver floor. Mirror any change in install.sh.
ARM_NVENC_MIN_DRIVER=530

# Echo `0` (advertise NVENC) or `1` (skip it) for the host's nvidia-smi driver.
# Warns to stderr — NOT stdout — so it never pollutes detect_gpus' JSON.
nvenc_driver_ok() {
    local drv major
    drv="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)"
    major="${drv%%.*}"
    if [[ -z "${major}" || ! "${major}" =~ ^[0-9]+$ ]]; then
        echo "WARNING: could not read NVIDIA driver version; advertising NVENC anyway" >&2
        echo 0; return
    fi
    if (( major < ARM_NVENC_MIN_DRIVER )); then
        echo "WARNING: NVIDIA driver ${drv} is too old for this build's NVENC (needs >= ${ARM_NVENC_MIN_DRIVER}.x); skipping NVENC so transcodes fall back to CPU. Upgrade the driver to enable HW encode." >&2
        echo 1; return
    fi
    echo "==> NVIDIA driver ${drv} detected (>= ${ARM_NVENC_MIN_DRIVER}.x); advertising NVENC" >&2
    echo 0
}

# Print KEY's value from the repo-root .env (last uncommented assignment, one
# layer of surrounding quotes stripped), or nothing if it is absent.
env_file_value() {
    local key="$1" val
    [[ -f "${ENV_FILE}" ]] || return 0
    val="$(sed -nE "s/^${key}=(.*)$/\\1/p" "${ENV_FILE}" | tail -n1)"
    val="${val%\"}"; val="${val#\"}"
    val="${val%\'}"; val="${val#\'}"
    printf '%s' "${val}"
}

# Phase 7b: enumerate GPUs host-side so the GPU-free backend can fill the `gpus`
# table from ARM_GPUS instead of probing hardware. Prints a compact JSON array
# (empty `[]` if none). Every entry carries `"encoder_kinds":[]`: the backend
# probes each device itself with a real test encode, so this only reports which
# devices exist, never which codecs they can run. Needs no built image.
# Mirrors services/backend/arm_backend/gpu_probe.py and the detect_gpus in
# install.sh.
detect_gpus() {
    local entries=() node vendor_file vid vendor idx
    if [[ -d /dev/dri ]]; then
        for node in /dev/dri/renderD*; do
            [[ -e "${node}" ]] || continue
            vendor_file="/sys/class/drm/$(basename "${node}")/device/vendor"
            [[ -r "${vendor_file}" ]] || continue
            vid="$(tr -d '[:space:]' < "${vendor_file}" | tr '[:upper:]' '[:lower:]')"
            case "${vid}" in
                0x8086) vendor=qsv ;;
                0x1002) vendor=vaapi ;;
                *)      continue ;;
            esac
            entries+=("{\"vendor\":\"${vendor}\",\"device_path\":\"${node}\",\"encoder_kinds\":[]}")
        done
    fi
    if command -v nvidia-smi >/dev/null 2>&1 && [[ "$(nvenc_driver_ok)" == 0 ]]; then
        while IFS= read -r idx; do
            [[ -n "${idx}" ]] || continue
            entries+=("{\"vendor\":\"nvenc\",\"device_path\":\"nvidia://${idx}\",\"encoder_kinds\":[]}")
        done < <(nvidia-smi -L 2>/dev/null | sed -nE 's/^GPU ([0-9]+):.*/\1/p')
    fi
    local IFS=,
    printf '[%s]' "${entries[*]:-}"
}

# GID of the /dev/dri render-node group. The dispatcher adds this to VAAPI/QSV
# transcoders so the PUID-dropped process can open the node (root:render 0660).
# Empty if there's no render node (CPU / NVENC-only host).
detect_render_gid() {
    local node
    for node in /dev/dri/renderD*; do
        [[ -e "${node}" ]] || continue
        stat -c '%g' "${node}"
        return 0
    done
}

# Host GPU list for this run, detected once and shared by the variant-build
# filter (select_up_services, before the build) and the .env write
# (refresh_arm_gpus, after the active-work guard). Detection only reads sysfs
# and nvidia-smi, so it never writes .env: a refused `up` leaves .env untouched.
DETECTED_GPUS=""
DETECTED_GPUS_SET=0
detect_gpus_once() {
    if [[ "${DETECTED_GPUS_SET}" -eq 0 ]]; then
        DETECTED_GPUS="$(detect_gpus)"
        DETECTED_GPUS_SET=1
    fi
}

# Refresh ARM_GPUS from host detection (it's derived, not a secret), UNLESS the
# transcode dispatcher is pointed at a remote docker host: then ARM_GPUS
# describes the REMOTE machine's GPUs (the dispatcher injects device access
# where the container actually runs), and detecting this host's GPUs would
# overwrite a hand-set remote GPU list with the wrong hardware.
# --ripper-only also skips detection: a ripper-only install never spawns a
# local transcoder, so there's nothing to advertise GPUs for.
refresh_arm_gpus() {
    local value
    if grep -qE '^ARM_TRANSCODE_DOCKER_HOST=..*' "${ENV_FILE}"; then
        echo "==> ARM_TRANSCODE_DOCKER_HOST set — keeping .env's ARM_GPUS (remote transcode host owns the GPUs)"
        return 0
    elif [[ "${RIPPER_ONLY}" -eq 1 ]]; then
        value="[]"
    else
        detect_gpus_once
        value="${DETECTED_GPUS}"
    fi
    if grep -q '^ARM_GPUS=' "${ENV_FILE}"; then
        sed -i "s|^ARM_GPUS=.*|ARM_GPUS=${value}|" "${ENV_FILE}"
    else
        printf 'ARM_GPUS=%s\n' "${value}" >> "${ENV_FILE}"
    fi
    if [[ "${RIPPER_ONLY}" -eq 1 ]]; then
        echo "==> --ripper-only: skipping GPU detection, ARM_GPUS=[]"
    else
        echo "==> detected GPU(s) for ARM_GPUS: ${value}"
    fi
}

# Minimum size for a gzipped pg_dump to count as real. gzip of empty input is
# ~20 bytes; a postgres:18 dump of a database with NO tables is ~400 bytes, so
# anything under this is a failed or truncated dump, never a valid one.
BACKUP_MIN_BYTES=256
BACKUP_TMP=""

backup_abort() {
    echo "ERROR: pre-deploy database backup failed: $1" >&2
    echo "       Aborting before anything is removed or restarted; the running stack is untouched." >&2
    echo "       Fix the cause, or re-run with --no-backup to deploy without a backup." >&2
    exit 1
}

# Before `up` recreates the backend (which runs Alembic migrations at boot, a
# one-way step), dump the running database to ./arm/backups/. Skipped when the
# db service isn't running (fresh install: nothing to lose) or with --no-backup.
# A failed, empty or truncated dump aborts the deploy.
backup_db() {
    if [[ "${NO_BACKUP}" -eq 1 ]]; then
        echo "==> --no-backup: skipping the pre-deploy database backup"
        return 0
    fi
    local running
    running="$(compose ps --status running --services)"
    if ! grep -qx "${DB_SERVICE}" <<<"${running}"; then
        echo "==> ${DB_SERVICE} is not running; no database to back up"
        return 0
    fi
    local dir="${ARM_DIR}/backups" ts file tmp size tail_txt
    mkdir -p "${dir}"
    ts="$(date -u +%Y%m%dT%H%M%SZ)"
    file="${dir}/pg-backup-${ts}.sql.gz"
    tmp="${file}.partial"
    # Never leave a stray .partial behind: any exit before the final mv (an
    # abort, a set -e failure in a later pipe, Ctrl-C or SIGTERM mid-dump)
    # removes it. Signals are turned into exits so the EXIT trap runs.
    BACKUP_TMP="${tmp}"
    trap 'rm -f "${BACKUP_TMP:-}"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    echo "==> backing up the ${DB_SERVICE} database to ${file}"
    # Single quotes on purpose: POSTGRES_USER/POSTGRES_DB resolve INSIDE the db
    # container, from the environment compose gave it.
    # shellcheck disable=SC2016
    if ! compose exec -T "${DB_SERVICE}" sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "${tmp}"; then
        backup_abort "pg_dump exited non-zero"
    fi
    size="$(wc -c < "${tmp}")" || backup_abort "cannot read ${tmp}"
    if (( size < BACKUP_MIN_BYTES )); then
        backup_abort "dump is only ${size} bytes gzipped (expected >= ${BACKUP_MIN_BYTES}); treating it as empty"
    fi
    if ! gzip -t "${tmp}" 2>/dev/null; then
        backup_abort "dump is not a valid gzip stream"
    fi
    # pg_dump writes this trailer only after a complete dump.
    tail_txt="$(gzip -dc "${tmp}" | tail -n 20)" || backup_abort "cannot decompress ${tmp}"
    if [[ "${tail_txt}" != *"PostgreSQL database dump complete"* ]]; then
        backup_abort "dump has no 'PostgreSQL database dump complete' trailer (truncated?)"
    fi
    mv "${tmp}" "${file}" || backup_abort "cannot move ${tmp} into place"
    BACKUP_TMP=""
    trap - EXIT INT TERM
    echo "==> database backup OK: ${file} (${size} bytes)"
    prune_backups "${dir}"
}

# Keep only the newest BACKUP_KEEP pg-backup-<UTC>.sql.gz files. The UTC
# timestamp names sort chronologically, and only files matching that exact
# pattern are ever pruned (anything else in the dir is left alone).
BACKUP_KEEP=5
prune_backups() {
    local dir="$1" f backups=() n i
    for f in "${dir}"/pg-backup-*.sql.gz; do
        [[ -f "${f}" && "$(basename "${f}")" =~ ^pg-backup-[0-9]{8}T[0-9]{6}Z\.sql\.gz$ ]] || continue
        backups+=("${f}")
    done
    n=${#backups[@]}
    (( n > BACKUP_KEEP )) || return 0
    echo "==> pruning $(( n - BACKUP_KEEP )) old backup(s); keeping the newest ${BACKUP_KEEP}"
    for (( i = 0; i < n - BACKUP_KEEP; i++ )); do
        rm -f "${backups[i]}"
    done
}

# Run inside a ripper container (plain POSIX sh): print the name of every
# active rip tool, nothing when idle. The ripper image is python:*-slim with no
# procps, so pgrep/ps are tried first and /proc/*/comm is the fallback. Exits 3
# when none of the three is usable (detection failed, NOT "idle").
# Tools are v3's rip commands: makemkvcon (video), abcde (audio CD) and plain
# dd (data disc, services/ripper/arm_ripper/rip/data_rip.py). Every path
# matches the process name EXACTLY (pgrep -x / string equality on comm), so
# `dd` cannot false-positive on names that merely contain it.
# shellcheck disable=SC2016  # expands inside the container, not here
RIP_PROBE_SH='
tools="makemkvcon abcde dd"
if command -v pgrep >/dev/null 2>&1; then
    for t in $tools; do pgrep -x "$t" >/dev/null 2>&1 && echo "$t"; done
    exit 0
fi
if command -v ps >/dev/null 2>&1; then
    ps -eo comm= 2>/dev/null | while read -r c; do
        for t in $tools; do [ "$c" = "$t" ] && echo "$t"; done
    done | sort -u
    exit 0
fi
[ -r /proc/self/comm ] || exit 3
for f in /proc/[0-9]*/comm; do
    c=$(cat "$f" 2>/dev/null) || continue
    for t in $tools; do [ "$c" = "$t" ] && echo "$t"; done
done | sort -u
exit 0
'

# Protect ACTIVE work, not idle containers. Every enrolled drive keeps a
# durable ripper running (and the backend respawns removed ones), so a running
# ripper alone is not a reason to refuse. Refuse unless --force when:
#   (a) any RUNNING arm.task_id container exists (a transcoder is active work
#       by construction), or
#   (b) a RUNNING arm.drive_id container has a rip tool running inside it:
#       makemkvcon (video), abcde (audio CD) or dd (data disc, data_rip.py).
# A ripper that cannot be inspected (exec error, or no answer within 15s from
# a wedged container) is treated as idle, with a note: detection failure never
# blocks or hangs a deploy.
guard_running_spawned() {
    local tasks drives ctr found active=()
    tasks="$(docker ps --filter "label=arm.task_id" --filter "status=running" --format '{{.Names}}')"
    drives="$(docker ps --filter "label=arm.drive_id" --filter "status=running" --format '{{.Names}}')"
    if [[ -n "${tasks}" ]]; then
        while IFS= read -r ctr; do
            [[ -n "${ctr}" ]] && active+=("${ctr} (transcoder)")
        done <<<"${tasks}"
    fi
    if [[ -n "${drives}" ]]; then
        while IFS= read -r ctr; do
            [[ -n "${ctr}" ]] || continue
            if found="$(timeout 15 docker exec "${ctr}" sh -c "${RIP_PROBE_SH}" 2>/dev/null </dev/null)"; then
                if [[ -n "${found}" ]]; then
                    active+=("${ctr} (ripping: $(tr '\n' ' ' <<<"${found}" | sed 's/ *$//'))")
                fi
            else
                echo "==> could not inspect ${ctr} for an active rip; treating it as idle"
            fi
        done <<<"${drives}"
    fi
    if [[ ${#active[@]} -eq 0 ]]; then
        [[ -n "${drives}" ]] && echo "==> running rippers are idle (no makemkvcon/abcde/dd); safe to replace"
        return 0
    fi
    if [[ "${FORCE}" -eq 1 ]]; then
        echo "==> --force: removing containers with ACTIVE work:"
        printf '      %s\n' "${active[@]}"
        return 0
    fi
    {
        echo "ERROR: backend-spawned containers have ACTIVE work:"
        printf '         %s\n' "${active[@]}"
        echo "       Removing them would kill the rip or transcode in progress. Images are built;"
        echo "       nothing has been backed up, removed or restarted yet."
        echo "       Wait for the job to finish, or re-run the same command with --force, e.g.:"
        echo "         bash devtools/setup-dev.sh up --force"
    } >&2
    exit 1
}

# Echo https://<host>:<port> for a service's published container port, or
# nothing when this compose config publishes none (overlay-proof: asks compose).
published_url() {
    local svc="$1" cport="$2" mapping host port
    mapping="$(compose port "${svc}" "${cport}" 2>/dev/null | head -n1 || true)"
    [[ -n "${mapping}" ]] || return 0
    port="${mapping##*:}"
    host="${mapping%:*}"
    [[ "${port}" =~ ^[0-9]+$ && "${port}" != 0 ]] || return 0
    case "${host}" in
        ""|0.0.0.0|"[::]"|"::") host=localhost ;;
    esac
    printf 'https://%s:%s' "${host}" "${port}"
}

HEALTH_TIMEOUT=90      # seconds; ELAPSED-time bound on the whole wait
HEALTH_SLEEP=2
HEALTH_ATTEMPT_MAX=15  # seconds; hard cap on one in-container exec attempt
HEALTH_RESULT=""       # summary line for the final banner

# In-container health check for when no host port is published. Stdlib only
# (urllib + ssl), so it cannot break on a dependency change. TLS verification
# is off because it dials localhost, which is not in the backend cert's SANs.
# Exits 0 healthy, 3 reached-but-unhealthy; any other status means the exec
# itself failed (container not running, no python, ...).
HEALTH_PY='
import ssl, sys, urllib.request
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
try:
    with urllib.request.urlopen("https://localhost:8443/api/health", context=ctx, timeout=5) as r:
        ok = r.status == 200
except Exception:
    ok = False
sys.exit(0 if ok else 3)
'

# Wait for the backend's /api/health, bounded by ELAPSED time: no new attempt
# starts after HEALTH_TIMEOUT seconds, and one attempt is capped (curl
# --max-time 5, exec by `timeout HEALTH_ATTEMPT_MAX`), so the worst case is
# HEALTH_TIMEOUT + HEALTH_ATTEMPT_MAX. Primary path: curl the host port
# `compose port` reports for 8443 (overlay-proof). With no published port
# (the template default) or no curl, check from inside the backend container
# via `compose exec` instead. Timeout prints the backend's recent logs and
# exits 1. Only when exec itself never works while the backend IS running is
# the wait skipped with a note.
wait_for_backend() {
    # python_ran=1 once any in-container attempt got as far as running the
    # Python check (exit 3 = python ran, backend not healthy yet). It says
    # nothing about the backend answering; it only separates "the check runs
    # but fails" from "compose exec itself cannot run".
    local base="" url mode rc python_ran=0 running start elapsed
    base="$(published_url "${BACKEND_SERVICE}" 8443)"
    if [[ -n "${base}" ]] && command -v curl >/dev/null 2>&1; then
        mode="port"
        url="${base}/api/health"
    else
        mode="exec"
        url="https://localhost:8443/api/health (inside ${BACKEND_SERVICE}, via compose exec)"
        if [[ -z "${base}" ]]; then
            echo "==> ${BACKEND_SERVICE} publishes no host port for 8443; checking health from inside the container"
        else
            echo "==> curl not found; checking health from inside the ${BACKEND_SERVICE} container"
        fi
    fi
    echo "==> waiting for ${url} (up to ~${HEALTH_TIMEOUT}s)"
    start="${SECONDS}"
    while :; do
        if [[ "${mode}" == port ]]; then
            if curl -sk -f --max-time 5 -o /dev/null "${url}"; then rc=0; else rc=3; fi
        else
            rc=0
            # Same as compose() (cd to the repo root), but under `timeout` so a
            # wedged exec cannot stall the wait past its bound.
            (cd "${ROOT_DIR}" && timeout "${HEALTH_ATTEMPT_MAX}" docker compose \
                exec -T "${BACKEND_SERVICE}" python -c "${HEALTH_PY}") </dev/null >/dev/null 2>&1 || rc=$?
        fi
        if [[ "${rc}" == 0 ]]; then
            echo "==> backend healthy: ${url}"
            HEALTH_RESULT="backend healthy at ${url}"
            return 0
        fi
        [[ "${rc}" == 3 ]] && python_ran=1
        elapsed=$(( SECONDS - start ))
        (( elapsed < HEALTH_TIMEOUT )) || break
        sleep "${HEALTH_SLEEP}"
    done
    if [[ "${mode}" == exec && "${python_ran}" == 0 ]]; then
        running="$(compose ps --status running --services 2>/dev/null || true)"
        if grep -qx "${BACKEND_SERVICE}" <<<"${running}"; then
            echo "==> could not run the in-container health check (compose exec failed every time); skipping the wait"
            echo "    (${BACKEND_SERVICE} is running; check it by hand: docker compose logs ${BACKEND_SERVICE})"
            HEALTH_RESULT="backend health not verified (in-container check unavailable)"
            return 0
        fi
    fi
    echo "ERROR: ${BACKEND_SERVICE} did not answer ${url} after $(( SECONDS - start ))s (limit ${HEALTH_TIMEOUT}s); last 20 log lines:" >&2
    compose logs --tail 20 "${BACKEND_SERVICE}" >&2 || true
    exit 1
}

# Services to build + start. Empty means "all" (compose's default). Otherwise
# it names every service except the skipped transcode images, because
# `compose build`/`up` with no service args builds every service with a
# `build:` key (deploy.replicas:0 services are never started, but still built):
#   - --ripper-only skips arm-transcode, arm-transcode-intel and
#     arm-transcode-amd (no local transcoder ever runs);
#   - arm-transcode-intel is built only when this host has a `qsv` GPU, and
#     arm-transcode-amd only when it has a `vaapi` GPU;
#   - with ARM_TRANSCODE_DOCKER_HOST set, both variants are skipped (the remote
#     host builds its own) but arm-transcode is kept.
# The backend falls back to arm-transcode for a vendor whose variant is absent.
UP_SERVICES=()
select_up_services() {
    local svc want_intel=0 want_amd=0 skipped=0 all=()
    if [[ "${RIPPER_ONLY}" -eq 0 ]] && ! grep -qE '^ARM_TRANSCODE_DOCKER_HOST=..*' "${ENV_FILE}"; then
        detect_gpus_once
        [[ "${DETECTED_GPUS}" == *'"vendor":"qsv"'* ]] && want_intel=1
        [[ "${DETECTED_GPUS}" == *'"vendor":"vaapi"'* ]] && want_amd=1
    fi
    while IFS= read -r svc; do
        case "${svc}" in
            arm-transcode)
                if [[ "${RIPPER_ONLY}" -eq 1 ]]; then skipped=1; continue; fi ;;
            arm-transcode-intel)
                if [[ "${want_intel}" -eq 0 ]]; then skipped=1; continue; fi ;;
            arm-transcode-amd)
                if [[ "${want_amd}" -eq 0 ]]; then skipped=1; continue; fi ;;
        esac
        all+=("${svc}")
    done < <(compose config --services)
    if [[ "${skipped}" -eq 1 ]]; then
        UP_SERVICES=("${all[@]}")
    fi
}

# Prereqs. Every action needs docker + the compose plugin; openssl mints the
# first-run .env secrets and (via install.sh --certs-only) the certs. The dev
# toolchain (uv, node, npm) is `setup`-only: `up` builds everything inside
# images and must not need or mutate a host venv / node_modules.
require docker  "install: https://docs.docker.com/engine/install/"
require_compose
require openssl "openssl should be present on any linux system"

if [[ "${ACTION}" == "setup" ]]; then
    require uv      "install: curl -LsSf https://astral.sh/uv/install.sh | sh"

    # nvm users: pull Node onto PATH (and pin it to .nvmrc) before the checks below.
    load_nvm

    require node    "install Node 22 (matches services/ui/.nvmrc / Dockerfile): https://nodejs.org/ — or 'nvm install' if you use nvm"
    require npm     "npm ships with Node — reinstall Node, or run 'nvm use', if it's missing"

    echo "==> syncing host venv via uv"
    ( cd "${ROOT_DIR}" && uv sync )

    # UI deps from the committed lockfile (same as services/ui/Dockerfile, which
    # builds on node:22). npm ci wipes node_modules and reinstalls exactly what
    # package-lock.json pins, so guard it: npm writes node_modules/.package-lock.json
    # on install, and a `git pull` that updates the lockfile makes it newer again.
    UI_DIR="${ROOT_DIR}/services/ui"
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
mkdir -p "${ARM_DIR}"/{certs,raw,media,logs,db,scripts}
chmod 700 "${ARM_DIR}/certs"
chmod 2775 "${ARM_DIR}/raw" "${ARM_DIR}/media" "${ARM_DIR}/logs"

if [[ -f "${ARM_DIR}/certs/arm-ca.crt" ]]; then
    echo "==> certs already present in arm/certs/ — skipping bootstrap"
else
    echo "==> generating internal CA + leaves via install.sh --certs-only"
    bash "${ROOT_DIR}/install.sh" \
        --prefix "${ARM_DIR}" \
        --certs-only \
        --no-env \
        --no-compose \
        --no-udev
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
    cdrom_gid="$(getent group cdrom | cut -d: -f3 || true)"
    cdrom_gid="${cdrom_gid:-44}"

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

# Prevent the host's udisks2/gvfs from auto-mounting optical drives ARM
# wants to drive. Without this, post-rip `eject` from the ripper
# container fails with EBUSY because the host mount holds /dev/srN.
# See docs/arch/06-deployment.md.
UDEV_RULE_PATH="/etc/udev/rules.d/99-arm-no-automount.rules"
build_udev_rule_content() {
    cat <<'RULE'
# Managed by devtools/setup-dev.sh — do not edit by hand.
# Disables host auto-mount for optical drives so an ARM ripper container can
# eject after a rip. Drives are hot-plugged and enrolled from the UI after
# install, so the rule is not scoped per drive: ARM owns the optical drives
# on this host. See docs/arch/06-deployment.md#host-side-auto-mount-must-be-disabled
SUBSYSTEM=="block", KERNEL=="sr[0-9]*", ENV{UDISKS_AUTO}="0"
RULE
}

ensure_udev_rule() {
    if ! command -v udevadm >/dev/null 2>&1; then
        echo "==> udevadm not on PATH — skipping host udev rule (non-Linux host?)"
        return 0
    fi

    local desired
    desired="$(build_udev_rule_content)"

    if [[ -r "${UDEV_RULE_PATH}" ]] && diff -q "${UDEV_RULE_PATH}" <(printf '%s' "${desired}") >/dev/null 2>&1; then
        echo "==> host udev rule already current at ${UDEV_RULE_PATH}"
        return 0
    fi

    if ! sudo -n true 2>/dev/null; then
        echo "==> sudo needs a password; to install the udev rule run:"
        echo "    printf '%s' \"\$(cat <<'RULE'"
        printf '%s\n' "${desired}"
        echo "RULE"
        echo "    )\" | sudo tee ${UDEV_RULE_PATH}"
        echo "    sudo udevadm control --reload-rules"
        echo "    sudo udevadm trigger --subsystem-match=block"
        return 0
    fi

    echo "==> writing host udev rule at ${UDEV_RULE_PATH} (sudo)"
    printf '%s' "${desired}" | sudo tee "${UDEV_RULE_PATH}" >/dev/null
    sudo udevadm control --reload-rules
    sudo udevadm trigger --subsystem-match=block 2>/dev/null || sudo udevadm trigger
    echo "==> udev rule installed; udisks2 will skip auto-mount for ARM drives"
}

ensure_udev_rule

if [[ "${ACTION}" == "up" ]]; then
    # 1. Build first. A failed build aborts here (set -e) with the running
    #    stack, its rippers and transcoders untouched. The service list comes
    #    from GPU detection (read-only; .env is written in step 3).
    select_up_services
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

    # 5. Only now remove backend-spawned rippers/transcoders.
    remove_spawned_containers

    # 6. Start from the images built above (no --build). An explicit service
    #    list keeps `up` from building a skipped image that does not exist yet.
    echo "==> starting the stack"
    if [[ ${#UP_SERVICES[@]} -gt 0 ]]; then
        compose up -d "${UP_SERVICES[@]}"
    else
        compose up -d
    fi

    # 7. Wait for the backend to answer its health check.
    wait_for_backend

    UI_URL="$(published_url "${UI_SERVICE}" 443)"
    UI_URL="${UI_URL:-https://localhost:8082}"
    cat <<EOF

stack is up; ${HEALTH_RESULT}
open ${UI_URL} -> Drives -> Enroll each drive you want ARM to use
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
  then open https://localhost:8082 -> Drives -> Enroll each drive you want ARM to use
  spin it down (stack + spawned ripper/transcoder containers): bash devtools/setup-dev.sh down

  optional — trust the local CA so browsers/curl skip the self-signed warning:
    bash devtools/trust-ca.sh

IDE: point your interpreter at ${ROOT_DIR}/.venv/bin/python
EOF
