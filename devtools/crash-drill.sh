#!/usr/bin/env bash
# Phase 9 + 15 — backend crash recovery drill.
#
# Inserts a synthetic in-flight job (status=ripping, one track in_progress)
# directly into the DB, force-kills the backend, brings it back, and asserts
# the lifespan-startup sweep recovered the job:
#   - track.status flipped to queued
#   - track.attempts incremented
#   - job.resumed_from_crash flipped to true
#
# Runs against the dev compose at docker-compose.yml. The DB and
# backend container names (armv3-db, armv3-backend) are taken from
# `name: armv3` in the compose file.
#
# Destructive: kills a running container. The script confirms before
# touching anything; --yes skips the prompt.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." &>/dev/null && pwd)"
COMPOSE=( docker compose -f "${ROOT_DIR}/docker-compose.yml" )
DB_CTR="armv3-db"
BACKEND_CTR="armv3-backend"
DRILL_PREFIX="DRILL-$(date -u +%s)-"
JOB_ID="${DRILL_PREFIX}JOB"
TRACK_ID="${DRILL_PREFIX}TRACK"

YES=0
for arg in "$@"; do
    case "$arg" in
        --yes|-y) YES=1 ;;
        --help|-h)
            sed -n '2,17p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *) echo "unknown arg: $arg" >&2; exit 2 ;;
    esac
done

log() { printf '\033[1;36m→\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; }

psql_exec() {
    docker exec -i "${DB_CTR}" psql -U arm -d arm -At -X "$@"
}

# Idempotent cleanup runs on EXIT regardless of success/failure.
cleanup() {
    set +e
    psql_exec -c "DELETE FROM tracks WHERE id = '${TRACK_ID}';" >/dev/null 2>&1
    psql_exec -c "DELETE FROM jobs   WHERE id = '${JOB_ID}';"   >/dev/null 2>&1
}
trap cleanup EXIT

# ---------- preflight ----------
log "checking dev stack is up"
if ! docker inspect -f '{{.State.Running}}' "${BACKEND_CTR}" 2>/dev/null | grep -q true; then
    err "${BACKEND_CTR} is not running. Bring up the dev stack first:"
    err "    cd ${ROOT_DIR} && docker compose up -d"
    exit 1
fi
if ! docker inspect -f '{{.State.Running}}' "${DB_CTR}" 2>/dev/null | grep -q true; then
    err "${DB_CTR} is not running."
    exit 1
fi
ok "stack is up (${BACKEND_CTR} + ${DB_CTR})"

if [[ ${YES} -eq 0 ]]; then
    cat <<EOF

This drill will:
  1. insert a synthetic ripping job (id ${JOB_ID}) + track in the dev DB
  2. force-kill ${BACKEND_CTR} (docker kill -s KILL)
  3. restart it via docker compose up -d
  4. assert the startup sweep recovered the job
  5. delete the synthetic job + track

The backend WILL be hard-killed. In-flight real jobs would be reset
to queued by the sweep — fine in dev, but don't run this against a
host that's actively ripping a real disc.

EOF
    read -rp "Continue? [y/N] " reply
    [[ "${reply,,}" == "y" || "${reply,,}" == "yes" ]] || { log "aborted"; exit 0; }
fi

# ---------- find a drive ----------
log "looking up a registered drive_id (FK target)"
DRIVE_ID="$(psql_exec -c "SELECT id FROM drives ORDER BY created_at DESC LIMIT 1;" | tr -d '[:space:]')"
if [[ -z "${DRIVE_ID}" ]]; then
    err "no drives registered yet — start a ripper at least once before running this drill."
    exit 1
fi
ok "using drive_id=${DRIVE_ID}"

# ---------- inject synthetic ripping state ----------
log "inserting synthetic job + track (status=ripping / in_progress)"
psql_exec <<SQL
INSERT INTO jobs (id, drive_id, disc_type, status, resumed_from_crash, created_at, updated_at)
VALUES ('${JOB_ID}', '${DRIVE_ID}', 'dvd', 'ripping', false, NOW(), NOW());

INSERT INTO tracks (id, job_id, kind, index, source_ref, status, attempts, created_at, updated_at)
VALUES ('${TRACK_ID}', '${JOB_ID}', 'video_title', 1, 'drill-source', 'in_progress', 0, NOW(), NOW());
SQL
ok "synthetic state inserted"

# ---------- confirm pre-state ----------
log "verifying pre-state"
PRE_JOB="$(psql_exec -c "SELECT status || ',' || resumed_from_crash FROM jobs WHERE id='${JOB_ID}';")"
PRE_TRACK="$(psql_exec -c "SELECT status || ',' || attempts FROM tracks WHERE id='${TRACK_ID}';")"
echo "    job:   ${PRE_JOB}      (expected: ripping,false)"
echo "    track: ${PRE_TRACK}    (expected: in_progress,0)"
[[ "${PRE_JOB}"   == "ripping,false"  ]] || { err "pre-state job mismatch";   exit 1; }
[[ "${PRE_TRACK}" == "in_progress,0"  ]] || { err "pre-state track mismatch"; exit 1; }
ok "pre-state matches expectations"

# ---------- crash + recover ----------
log "force-killing ${BACKEND_CTR}"
docker kill -s KILL "${BACKEND_CTR}" >/dev/null
log "waiting for container to exit"
until [[ "$(docker inspect -f '{{.State.Status}}' "${BACKEND_CTR}" 2>/dev/null)" != "running" ]]; do
    sleep 0.2
done
ok "backend exited"

log "bringing backend back"
"${COMPOSE[@]}" up -d arm-backend >/dev/null

log "waiting for backend lifespan to complete (sweep runs there)"
deadline=$(( $(date +%s) + 120 ))
while [[ $(date +%s) -lt ${deadline} ]]; do
    if docker exec "${BACKEND_CTR}" curl -ksSf https://localhost:8443/api/health >/dev/null 2>&1; then
        ok "backend ready"
        break
    fi
    sleep 1
done
if ! docker exec "${BACKEND_CTR}" curl -ksSf https://localhost:8443/api/health >/dev/null 2>&1; then
    err "backend never came back — see: docker logs ${BACKEND_CTR}"
    exit 1
fi

# ---------- assert recovery ----------
log "verifying post-state (sweep should have recovered the job)"
POST_JOB="$(psql_exec -c "SELECT status || ',' || resumed_from_crash FROM jobs WHERE id='${JOB_ID}';")"
POST_TRACK="$(psql_exec -c "SELECT status || ',' || attempts FROM tracks WHERE id='${TRACK_ID}';")"
echo "    job:   ${POST_JOB}    (expected: ripping,true)"
echo "    track: ${POST_TRACK}  (expected: queued,1)"

fail=0
[[ "${POST_JOB}"   == "ripping,true" ]] || { err "job.resumed_from_crash NOT set"; fail=1; }
[[ "${POST_TRACK}" == "queued,1"     ]] || { err "track NOT recovered (expected queued,1)"; fail=1; }

if (( fail )); then
    err "DRILL FAILED — backend's startup sweep did not recover the job."
    err "Inspect logs: docker logs ${BACKEND_CTR} 2>&1 | grep -i 'crash\\|recover\\|sweep'"
    exit 1
fi

ok "DRILL PASSED — startup sweep recovered job ${JOB_ID} cleanly."
