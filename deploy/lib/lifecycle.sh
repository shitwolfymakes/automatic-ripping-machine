#!/usr/bin/env bash
# shellcheck disable=SC2034  # HEALTH_RESULT and UP_SERVICES are read by the scripts that source this file
# deploy/lib/lifecycle.sh: Guard, backup and pruning, spawned-container cleanup, ripper respawn, retired services, image selection, health wait.
# Shared by devtools/setup-dev.sh and deploy/armctl.sh. Sourced, never executed.
# Needs deploy/lib/common.sh loaded first.

# The backend spawns one ripper container per enrolled drive (label
# `arm.drive_id`, ripper_manager.py) and one transcoder per local task (label
# `arm.task_id`, transcode_dispatcher.py). They are not compose services, so
# `docker compose down` leaves them behind — still holding the old image, the
# compose network, and the optical device nodes across a redeploy.
RIPPERS_REMOVED=0
remove_spawned_containers() {
    local ids rippers
    rippers="$(docker ps -aq --filter "label=arm.drive_id")"
    ids="$( { printf '%s\n' "${rippers}"; docker ps -aq --filter "label=arm.task_id"; } | sed '/^$/d' | sort -u )"
    # Rippers are respawned only by the backend's startup reconcile; `up`
    # checks this flag to make sure that reconcile runs again (see below).
    [[ -n "${rippers}" ]] && RIPPERS_REMOVED=1
    if [[ -n "${ids}" ]]; then
        arm_say "removing backend-spawned ripper/transcoder containers"
        # shellcheck disable=SC2086  # ids is a list of container ids by design
        docker rm -f ${ids} >/dev/null
    else
        arm_say "no backend-spawned ripper/transcoder containers to remove"
    fi
}

# The backend's container start time, or empty when it is not running.
backend_started_at() {
    local id
    id="$(compose ps -q "${BACKEND_SERVICE}" 2>/dev/null)" || true
    [[ -n "${id}" ]] || return 0
    docker inspect -f '{{.State.StartedAt}}' "${id}" 2>/dev/null || true
}

# The backend spawns rippers only at startup (reconcile_enrolled_rippers in
# main.py). `up` removes them before `compose up`, and compose leaves the
# backend running when its image and config are unchanged (a UI-only deploy),
# so nothing would respawn them: restart the backend in that case.
respawn_rippers_if_needed() {  # respawn_rippers_if_needed <backend StartedAt before up>
    [[ "${RIPPERS_REMOVED}" -eq 1 ]] || return 0
    local before="$1" after
    after="$(backend_started_at)"
    if [[ -n "${before}" && "${after}" == "${before}" ]]; then
        arm_say "${BACKEND_SERVICE} kept running; restarting it so it respawns the removed rippers"
        compose restart "${BACKEND_SERVICE}"
    fi
}

# Compose services an earlier version of this stack defined and this one no
# longer does. `compose up` leaves their containers running, still holding
# their host ports (the old arm-ui-neu kept the UI port, so the new arm-ui
# failed to bind). Remove exactly these by project + service label; a blanket
# `up --remove-orphans` is unsafe because backend-spawned containers carry the
# stack's project label too.
RETIRED_SERVICES=(arm-ui-neu)
remove_retired_services() {
    local project svc ids
    project="$(compose config 2>/dev/null | sed -n 's/^name: //p' | head -n 1)"
    [[ -n "${project}" ]] || return 0
    for svc in "${RETIRED_SERVICES[@]}"; do
        ids="$(docker ps -aq --filter "label=com.docker.compose.project=${project}" \
                            --filter "label=com.docker.compose.service=${svc}")"
        if [[ -n "${ids}" ]]; then
            arm_say "removing the retired ${svc} container (no longer part of the stack)"
            # shellcheck disable=SC2086  # ids is a list of container ids by design
            docker rm -f ${ids} >/dev/null
        fi
    done
}

# Minimum size for a gzipped pg_dump to count as real. gzip of empty input is
# ~20 bytes; a postgres:18 dump of a database with NO tables is ~400 bytes, so
# anything under this is a failed or truncated dump, never a valid one.
BACKUP_MIN_BYTES=256
BACKUP_TMP=""

backup_abort() {
    arm_err "pre-deploy database backup failed: $1"
    arm_sub "       Aborting before anything is removed or restarted; the running stack is untouched." >&2
    arm_sub "       Fix the cause, or re-run with --no-backup to deploy without a backup." >&2
    exit 1
}

# Before `up` recreates the backend (which runs Alembic migrations at boot, a
# one-way step), dump the running database to ./arm/backups/. Skipped when the
# db service isn't running (fresh install: nothing to lose) or with --no-backup.
# A failed, empty or truncated dump aborts the deploy.
backup_db() {
    if [[ "${NO_BACKUP}" -eq 1 ]]; then
        arm_say "--no-backup: skipping the pre-deploy database backup"
        return 0
    fi
    local running
    running="$(compose ps --status running --services)"
    if ! grep -qx "${DB_SERVICE}" <<<"${running}"; then
        arm_say "${DB_SERVICE} is not running; no database to back up"
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
    arm_say "backing up the ${DB_SERVICE} database to ${file}"
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
    arm_say "database backup OK: ${file} (${size} bytes)"
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
    arm_say "pruning $(( n - BACKUP_KEEP )) old backup(s); keeping the newest ${BACKUP_KEEP}"
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
                arm_say "could not inspect ${ctr} for an active rip; treating it as idle"
            fi
        done <<<"${drives}"
    fi
    if [[ ${#active[@]} -eq 0 ]]; then
        [[ -n "${drives}" ]] && arm_say "running rippers are idle (no makemkvcon/abcde/dd); safe to replace"
        return 0
    fi
    if [[ "${FORCE}" -eq 1 ]]; then
        arm_say "--force: removing containers with ACTIVE work:"
        for found in "${active[@]}"; do arm_sub "      ${found}"; done
        return 0
    fi
    {
        arm_err "backend-spawned containers have ACTIVE work:"
        for found in "${active[@]}"; do arm_sub "         ${found}"; done
        arm_sub "       Removing them would kill the rip or transcode in progress. ${ARM_HINT_IMAGES_READY};"
        arm_sub "       nothing has been backed up, removed or restarted yet."
        arm_sub "       Wait for the job to finish, or re-run the same command with --force, e.g.:"
        arm_sub "         ${ARM_HINT_FORCE_CMD}"
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
            arm_say "${BACKEND_SERVICE} publishes no host port for 8443; checking health from inside the container"
        else
            arm_say "curl not found; checking health from inside the ${BACKEND_SERVICE} container"
        fi
    fi
    arm_say "waiting for ${url} (up to ~${HEALTH_TIMEOUT}s)"
    start="${SECONDS}"
    while :; do
        if [[ "${mode}" == port ]]; then
            if curl -sk -f --max-time 5 -o /dev/null "${url}"; then rc=0; else rc=3; fi
        else
            rc=0
            # Same as compose() (cd to the repo root), but under `timeout` so a
            # wedged exec cannot stall the wait past its bound.
            (cd "${ARM_COMPOSE_CWD}" && timeout "${HEALTH_ATTEMPT_MAX}" "${ARM_COMPOSE_CMD[@]}" \
                exec -T "${BACKEND_SERVICE}" python -c "${HEALTH_PY}") </dev/null >/dev/null 2>&1 || rc=$?
        fi
        if [[ "${rc}" == 0 ]]; then
            arm_say "backend healthy: ${url}"
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
            arm_say "could not run the in-container health check (compose exec failed every time); skipping the wait"
            arm_sub "    (${BACKEND_SERVICE} is running; check it by hand: ${ARM_HINT_LOGS_CMD} ${BACKEND_SERVICE})"
            HEALTH_RESULT="backend health not verified (in-container check unavailable)"
            return 0
        fi
    fi
    arm_err "${BACKEND_SERVICE} did not answer ${url} after $(( SECONDS - start ))s (limit ${HEALTH_TIMEOUT}s); last 20 log lines:"
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
