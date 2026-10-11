#!/usr/bin/env bash
# Phase 15 — ISO-source smoke test for the ripper, end-to-end.
#
# Runs the full scan → identify → rip → transcode pipeline against a
# Sintel ISO fixture (no physical disc required), driven entirely through
# the `/api/iso` "Rip from ISO" API (spec 2026-09-30-iso-source-rip): the
# backend spawns and tears down its own one-shot ripper container, so the
# smoke no longer borrows (pauses/resumes) a real enrolled drive.
#
# Pipeline:
#   1. Sintel ISO comes from the matrix256-corpus image — pulled from
#      GHCR (Docker Hub fallback), `docker cp` just sintel.iso out so
#      the BBB layer doesn't burn 8.5 GB of host disk. SHA-256 verified
#      against the corpus.lock pin. Cache at ~/arm-corpus/ by default.
#      Last-resort fallback: direct fetch from archive.org.
#   2. Admin JWT acquired first. MakeMKV key: env var (MAKEMKV_KEY — any
#      value MakeMKV accepts, perma or beta) first, then a single forum-
#      scrape attempt; either way the resolved key is PATCHed onto the
#      backend's `Config.makemkv_key` so the ripper the backend spawns can
#      pick it up at pipeline start (job_controller._configured_makemkv_key).
#      The forum sits behind Cloudflare and rate-limits / 525s under load,
#      so an explicit MAKEMKV_KEY keeps the smoke deterministic.
#   3. The ISO is staged (hard-linked, falling back to a copy) into
#      `<ARM_HOST_ISO_LIBRARY_PATH>/arm-smoke/<iso>` — the backend's ISO
#      library requires `ARM_HOST_ISO_LIBRARY_PATH` set in `.env` and the
#      stack restarted so it's bind-mounted into the backend at /ingress.
#   4. `POST /api/iso/rips` creates a one-shot virtual drive for that file
#      and the backend spawns its ripper container (ARM_SOURCE_PATH mode).
#      `GET /api/jobs?drive_id=<id>` is polled until the job is ripped.
#      The ripper exits on its own once the rip ends (source mode is a
#      one-shot pipeline); the backend's watchdog retires the virtual
#      drive within ~30s of the container exiting.
#   5. The GPU-preferred Plex H.265 session applied to the job (JWT already
#      acquired in step 2). Transcode tasks are polled until all are
#      done|failed.
#   6. Cleanup: `DELETE /api/iso/rips/{id}` if the virtual drive is still
#      live (usually a no-op — the watchdog beats us to it). Opt out with
#      --no-cleanup.
#
# Idempotent. Safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." &>/dev/null && pwd)"
COMPOSE=( docker compose -f "${ROOT_DIR}/docker-compose.yml" )

CACHE_DIR="${ISO_CACHE_DIR:-${HOME}/arm-corpus}"

CORPUS_IMAGE_GHCR="ghcr.io/shitwolfymakes/matrix256-corpus:latest"
CORPUS_IMAGE_HUB="docker.io/shitwolfymakes/matrix256-corpus:latest"

# Both fixtures are SHA-256-pinned in matrix256-corpus/corpus.lock.json
# (CC-BY 3.0 sources). Pull either out of the corpus image, or fall back
# to Internet Archive when the image is too big for local Docker storage.
ISO_CHOICE="sintel"
ISO_NAME=""
ISO_PATH=""
ISO_SHA256=""
ISO_SIZE_BYTES=0
ARCHIVE_URL=""
configure_iso() {
    case "${ISO_CHOICE}" in
        sintel)
            ISO_NAME="sintel.iso"
            ISO_SHA256="7ea69a0215cdd7fff4acb48976677b2814a3d2e375b82b3288324bb356afe803"
            ISO_SIZE_BYTES=3881467904
            ARCHIVE_URL="https://archive.org/download/sintel_20260427/sintel.iso"
            ;;
        bbb|big_buck_bunny)
            ISO_NAME="big_buck_bunny.iso"
            ISO_SHA256="9691de650fa1aa09a537409b34898e747d5267ac68216c292bdd0dbea513f649"
            ISO_SIZE_BYTES=8474263552
            ARCHIVE_URL="https://archive.org/download/big_buck_bunny_202604/big_buck_bunny.iso"
            ;;
        *)
            err "unknown --iso=${ISO_CHOICE}; expected 'sintel' or 'bbb'"
            exit 2
            ;;
    esac
    ISO_PATH="${CACHE_DIR}/${ISO_NAME}"
}

RIPPER_IMAGE="${ARM_RIPPER_IMAGE:-arm-ripper:latest}"
RIPPER_SERVICE="arm-ripper"          # compose build-only service (image source)
DATA_DIR="${ROOT_DIR}/arm"           # raw/media/logs/certs live under ./arm/
MAKEMKV_FORUM_URL="https://forum.makemkv.com/forum/viewtopic.php?f=5&t=1053"

API_BASE="${ARM_API_BASE:-https://localhost:8081}"
DEFAULT_SESSION_ID="ses_builtin_movie_plex_1080p_gpu"
SESSION_ID="${DEFAULT_SESSION_ID}"
DO_TRANSCODE=1
DO_CLEANUP=1
FORCE_REBUILD=0

log() { printf '\033[1;36m→\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*" >&2; }
err() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; }

show_help() {
    sed -n '2,40p' "$0" | sed 's/^# \?//'
    cat <<'EOF'

Usage: iso-smoke.sh [options]

Options:
  --iso=sintel|bbb    Pick the fixture ISO (default: sintel — DVD,
                      ~3.7 GB). Use bbb for the Blu-ray fixture
                      (~8 GB) — that's the cutover-readiness criterion
                      at docs/developers/architecture/08-v2-isolation-and-cutover.md
                      § Readiness line 200.
  --no-transcode      Stop after the rip, skip the transcode chain.
  --session=<id>      Override the default transcode session
                      (default: ses_builtin_movie_plex_1080p_gpu —
                      NVENC-preferred Plex H.265 1080p).
  --no-cleanup        Don't DELETE /api/iso/rips/{id} on exit — leave the
                      virtual drive for manual inspection via the API/UI.
                      The backend's watchdog retires it on its own within
                      ~30s of the ripper container exiting either way.
  --rebuild           Force a fresh `docker compose build` of the ripper
                      image before launching. Use after editing
                      services/ripper/ — otherwise the in-flight image
                      still carries the old code.
  --help, -h          Show this message.

Environment variables:
  ISO_CACHE_DIR       Where the Sintel ISO is cached (default: ~/arm-corpus)
  MAKEMKV_KEY         MakeMKV app key (perma OR a beta you grabbed
                      manually). Overrides the forum scrape.
  ARM_ADMIN_USER      Admin username for the JWT-acquire step
                      (default: admin). Used non-interactively when set.
  ARM_ADMIN_PASSWORD  Admin password. If unset, the script prompts
                      interactively at JWT-acquire time.
  ARM_API_BASE        Backend / UI base URL (default: https://localhost:8081).
EOF
}

for arg in "$@"; do
    case "$arg" in
        --help|-h) show_help; exit 0 ;;
        --no-transcode) DO_TRANSCODE=0 ;;
        --no-cleanup) DO_CLEANUP=0 ;;
        --rebuild) FORCE_REBUILD=1 ;;
        --session=*) SESSION_ID="${arg#--session=}" ;;
        --iso=*) ISO_CHOICE="${arg#--iso=}" ;;
        *) err "unknown arg: $arg"; exit 2 ;;
    esac
done

configure_iso

# ---- ISO fetch + verify --------------------------------------------------

verify_iso_sha256() {
    [[ -f "${ISO_PATH}" ]] || return 1
    local actual
    actual=$(sha256sum "${ISO_PATH}" | awk '{print $1}')
    [[ "${actual}" == "${ISO_SHA256}" ]]
}

fetch_from_corpus_image() {
    local img="$1"
    log "trying ${img}"
    if ! docker pull "${img}" >/dev/null 2>&1; then
        warn "pull failed: ${img}"
        return 1
    fi
    local cid
    cid=$(docker create "${img}")
    # `docker cp` will fail cleanly if the path isn't in the image.
    if ! docker cp "${cid}:/corpus/${ISO_NAME}" "${ISO_PATH}" 2>/dev/null; then
        warn "docker cp from ${img} failed"
        docker rm "${cid}" >/dev/null
        return 1
    fi
    docker rm "${cid}" >/dev/null
    ok "extracted ${ISO_NAME} from ${img}"
}

fetch_from_archive() {
    log "fetching ${ARCHIVE_URL}"
    log "(${ISO_SIZE_BYTES} bytes — this will take a few minutes)"
    curl -fL --progress-bar "${ARCHIVE_URL}" -o "${ISO_PATH}"
}

ensure_iso() {
    mkdir -p "${CACHE_DIR}"
    if verify_iso_sha256; then
        ok "cached ISO verified: ${ISO_PATH}"
        return
    fi
    if [[ -f "${ISO_PATH}" ]]; then
        warn "cached ISO failed SHA-256; re-fetching"
        rm -f "${ISO_PATH}"
    fi
    # Primary: ghcr.io corpus image. Fallback: docker hub. Last resort: archive.org.
    fetch_from_corpus_image "${CORPUS_IMAGE_GHCR}" \
        || fetch_from_corpus_image "${CORPUS_IMAGE_HUB}" \
        || fetch_from_archive
    if ! verify_iso_sha256; then
        err "ISO SHA-256 mismatch after fetch: ${ISO_PATH}"
        sha256sum "${ISO_PATH}" >&2
        exit 1
    fi
    ok "fetched + verified ${ISO_PATH}"
}

# ---- MakeMKV key ---------------------------------------------------------

resolve_makemkv_key() {
    # Caller captures stdout, so status messages MUST go to stderr or
    # they get spliced into the key. Only the bare key is printed to
    # stdout below.
    if [[ -n "${MAKEMKV_KEY:-}" ]]; then
        ok "MAKEMKV_KEY from environment" >&2
        printf '%s\n' "${MAKEMKV_KEY}"
        return
    fi
    log "scraping monthly MakeMKV key from forum" >&2
    # Run curl on its own so we can report HTTP/network errors with
    # specifics, rather than reporting a generic "scrape failed" that
    # could mean a Cloudflare 525, a DNS hiccup, or a forum-page format
    # change. Each of those calls for a different operator response.
    local body curl_rc curl_stderr
    curl_stderr=$(mktemp)
    body=$(curl -sfL --max-time 15 -w '%{http_code}' "${MAKEMKV_FORUM_URL}" 2>"${curl_stderr}") || curl_rc=$?
    curl_rc=${curl_rc:-0}
    if (( curl_rc != 0 )); then
        err "forum scrape failed: curl exited ${curl_rc} (${MAKEMKV_FORUM_URL})"
        err "  stderr: $(tr '\n' ' ' <"${curl_stderr}")"
        rm -f "${curl_stderr}"
        err "MakeMKV's forum sits behind Cloudflare and rate-limits / 525s under load."
        err "Workaround: set MAKEMKV_KEY=<key> and re-run (one-time per month)."
        err "Key lives at the bottom of: ${MAKEMKV_FORUM_URL}"
        exit 1
    fi
    rm -f "${curl_stderr}"
    # `-w '%{http_code}'` appends the status code as the last 3 chars of $body.
    local http_code="${body: -3}"
    body="${body:0:${#body}-3}"
    local key
    key=$(printf '%s' "${body}" | grep -oP 'T-[\w\d@]{66}' | head -1 || true)
    if [[ -z "${key}" ]]; then
        err "forum scrape returned HTTP ${http_code} but no T-... key matched in the page body"
        err "The forum may have changed the post format. Inspect:"
        err "  ${MAKEMKV_FORUM_URL}"
        err "Workaround: set MAKEMKV_KEY=<key> and re-run."
        exit 1
    fi
    ok "scraped key: ${key:0:8}…${key: -8}" >&2
    printf '%s\n' "${key}"
}

apply_makemkv_key() {
    # The ripper no longer reads MAKEMKV_KEY from its own environment — the
    # backend spawns it and the pipeline fetches the key from
    # Config.makemkv_key at start (job_controller._configured_makemkv_key).
    # PATCH it onto the backend config instead of injecting it into a container.
    local jwt="$1" key="$2"
    log "setting the backend's MakeMKV key (PATCH /api/config)" >&2
    local body http_code
    body=$(curl -sk --max-time 10 -X PATCH "${API_BASE}/api/config" \
        -H "Authorization: Bearer ${jwt}" \
        -H 'Content-Type: application/json' \
        -d "$(printf '{"makemkv_key":"%s"}' "${key}")" \
        -w '\n%{http_code}' 2>/dev/null) || true
    http_code="${body##*$'\n'}"
    body="${body%$'\n'*}"
    if [[ "${http_code}" != "200" ]]; then
        err "PATCH /api/config HTTP ${http_code}: ${body:0:300}"
        exit 1
    fi
    ok "MakeMKV key set on the backend" >&2
}

# ---- Stack preflight -----------------------------------------------------

require_stack_up() {
    for ctr in armv3-backend armv3-db; do
        if ! docker ps --format '{{.Names}}' | grep -qx "${ctr}"; then
            err "${ctr} is not running"
            err "bring the stack up first: cd ${ROOT_DIR} && docker compose up -d arm-db arm-backend arm-ui"
            exit 1
        fi
    done
    ok "backend + db running"
}

require_ripper_image() {
    if (( FORCE_REBUILD == 1 )); then
        log "rebuilding ${RIPPER_IMAGE} (--rebuild)"
        ( cd "${ROOT_DIR}" && "${COMPOSE[@]}" build "${RIPPER_SERVICE}" )
    elif ! docker image inspect "${RIPPER_IMAGE}" >/dev/null 2>&1; then
        log "building ${RIPPER_IMAGE}"
        ( cd "${ROOT_DIR}" && "${COMPOSE[@]}" build "${RIPPER_SERVICE}" )
    fi
    ok "ripper image present: ${RIPPER_IMAGE}"
}

# ---- ISO library ----------------------------------------------------------

require_iso_library_path() {
    # Prints the host-side ISO library directory. `.env` is a plain
    # KEY=value file; a `${PWD}` reference in it is resolved by docker
    # compose against the directory holding docker-compose.yml at parse
    # time, which for this project is always ROOT_DIR (see .env.example).
    local raw path
    raw=$(sed -nE 's/^ARM_HOST_ISO_LIBRARY_PATH=(.+)$/\1/p' "${ROOT_DIR}/.env" 2>/dev/null | tail -n1)
    if [[ -z "${raw}" ]]; then
        err "ARM_HOST_ISO_LIBRARY_PATH is not set in ${ROOT_DIR}/.env"
        err "  Rip from ISO needs a host directory of .iso files mounted read-only"
        err "  into the backend. Set it and restart the stack:"
        err "    echo 'ARM_HOST_ISO_LIBRARY_PATH=${ROOT_DIR}/arm/iso-library' >> ${ROOT_DIR}/.env"
        err "    bash devtools/setup-dev.sh up"
        exit 1
    fi
    path="${raw//\$\{PWD\}/${ROOT_DIR}}"
    mkdir -p "${path}"
    ok "ISO library: ${path}" >&2
    printf '%s\n' "${path}"
}

stage_iso() {
    # Copies or hard-links the cached fixture ISO into
    # <library>/arm-smoke/<iso> and prints the library-relative path the
    # `/api/iso` endpoints expect.
    local lib="$1"
    local dest_dir="${lib}/arm-smoke"
    mkdir -p "${dest_dir}"
    local dest="${dest_dir}/${ISO_NAME}"
    rm -f "${dest}"
    if ! ln "${ISO_PATH}" "${dest}" 2>/dev/null; then
        cp "${ISO_PATH}" "${dest}"
    fi
    ok "staged arm-smoke/${ISO_NAME} in the ISO library" >&2
    printf 'arm-smoke/%s\n' "${ISO_NAME}"
}

# ---- Create / watch the ISO rip -------------------------------------------

create_iso_rip() {
    # Prints the virtual drive_id the backend created (and started
    # spawning a one-shot ripper container for).
    local jwt="$1" rel="$2"
    log "POST /api/iso/rips path=${rel}" >&2
    local body http_code
    body=$(curl -sk --max-time 10 -X POST "${API_BASE}/api/iso/rips" \
        -H "Authorization: Bearer ${jwt}" \
        -H 'Content-Type: application/json' \
        -d "$(printf '{"path":"%s"}' "${rel}")" \
        -w '\n%{http_code}' 2>/dev/null) || true
    http_code="${body##*$'\n'}"
    body="${body%$'\n'*}"
    if [[ "${http_code}" != "201" ]]; then
        err "POST /api/iso/rips HTTP ${http_code}: ${body:0:300}"
        exit 1
    fi
    local drive_id
    drive_id=$(printf '%s' "${body}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["drive_id"])' 2>/dev/null || true)
    if [[ -z "${drive_id}" ]]; then
        err "create-rip returned no drive_id: ${body:0:300}"
        exit 1
    fi
    ok "ISO rip created: drive_id=${drive_id}" >&2
    printf '%s\n' "${drive_id}"
}

watch_until_ripped() {
    # Polls GET /api/jobs?drive_id=<id> (the virtual drive is unique to this
    # run, so its single job is always the latest/only row) until it lands
    # in a post-rip terminal state. Prints the job_id; status messages go
    # to stderr only.
    local jwt="$1" drive_id="$2"
    log "polling /api/jobs?drive_id=${drive_id} until ripped (15-min timeout)" >&2
    local deadline=$(( $(date +%s) + 900 ))
    local last_status="" job_id="" job_status=""
    while :; do
        local body http_code
        body=$(curl -sk --max-time 10 "${API_BASE}/api/jobs?drive_id=${drive_id}&limit=1" \
            -H "Authorization: Bearer ${jwt}" -w '\n%{http_code}' 2>/dev/null) || true
        http_code="${body##*$'\n'}"
        body="${body%$'\n'*}"
        if [[ "${http_code}" != "200" ]]; then
            err "GET /api/jobs HTTP ${http_code}: ${body:0:200}"
            exit 1
        fi
        job_id=$(printf '%s' "${body}" | python3 -c \
            'import sys,json; rows=json.load(sys.stdin); print(rows[0]["id"] if rows else "")' 2>/dev/null || true)
        job_status=$(printf '%s' "${body}" | python3 -c \
            'import sys,json; rows=json.load(sys.stdin); print(rows[0]["status"] if rows else "")' 2>/dev/null || true)
        if [[ "${job_status}" != "${last_status}" ]]; then
            [[ -n "${job_status}" ]] && log "$(date +%T) job ${job_id}: ${job_status}" >&2
            last_status="${job_status}"
        fi
        case "${job_status}" in
            ripped|ripped_partial)
                ok "rip complete: ${job_status}" >&2
                printf '%s\n' "${job_id}"
                return 0
                ;;
            failed|abandoned)
                err "job ${job_id} ended in ${job_status} — check the backend log"
                exit 1
                ;;
        esac
        if (( $(date +%s) > deadline )); then
            err "deadline exceeded (15 min) waiting for the rip; job_id=${job_id:-unknown} status=${job_status:-unknown}"
            exit 1
        fi
        sleep 5
    done
}

# ---- Auth ---------------------------------------------------------------

acquire_jwt() {
    local user="${ARM_ADMIN_USER:-admin}"
    local password="${ARM_ADMIN_PASSWORD:-}"
    if [[ -z "${password}" ]]; then
        log "ARM_ADMIN_PASSWORD not set; prompting for ${user}" >&2
        read -rsp "  admin password: " password </dev/tty
        printf '\n' >&2
    fi
    local payload
    payload=$(printf '{"username":"%s","password":"%s"}' "${user}" "${password}")
    # `-f` would suppress the JSON error body on 4xx (e.g. 401 "invalid
    # credentials"); we'd then print "rc=0" because $? after `if !` is the
    # `!`'s status, not curl's. Parse http_code manually instead, same
    # shape as apply_transcode.
    local body http_code
    body=$(curl -sk --max-time 10 -X POST "${API_BASE}/api/auth/login" \
        -H 'Content-Type: application/json' \
        -d "${payload}" \
        -w '\n%{http_code}' 2>/dev/null) || true
    http_code="${body##*$'\n'}"
    body="${body%$'\n'*}"
    if [[ "${http_code}" != "200" ]]; then
        err "auth HTTP ${http_code} for user '${user}' against ${API_BASE}/api/auth/login"
        err "  body: ${body:0:300}"
        if [[ "${http_code}" == "401" ]]; then
            err "  hint: fresh-DB seed is admin/admin (forced-rotate on first login);"
            err "        if you've already rotated, set ARM_ADMIN_PASSWORD to the new value."
        elif [[ "${http_code}" == "000" ]]; then
            err "  hint: HTTP 000 = curl never got a response. Is arm-backend/arm-ui up on ${API_BASE}?"
        fi
        exit 1
    fi
    local jwt
    jwt=$(printf '%s' "${body}" | python3 -c \
        'import sys,json; d=json.load(sys.stdin); print(d.get("access_token",""))' 2>/dev/null || true)
    if [[ -z "${jwt}" ]]; then
        err "auth 200 but no access_token in body: ${body:0:300}"
        exit 1
    fi
    ok "JWT acquired for ${user}" >&2
    printf '%s\n' "${jwt}"
}

# ---- Transcode ----------------------------------------------------------

apply_transcode() {
    local jwt="$1" job_id="$2" session_id="$3"
    log "applying transcode session ${session_id} to ${job_id} (overwrite=true)" >&2
    # `-f` would swallow the error body that the API returns on 4xx (e.g.
    # `output_path collisions detected`), leaving the script with a blank
    # error. Instead we ask curl to print the http_code on its own line and
    # parse it manually so we keep the body for diagnostics.
    local body http_code
    body=$(curl -sk --max-time 10 -X POST \
        "${API_BASE}/api/jobs/${job_id}/transcode" \
        -H "Authorization: Bearer ${jwt}" \
        -H 'Content-Type: application/json' \
        -d "$(printf '{"session_id":"%s","overwrite":true}' "${session_id}")" \
        -w '\n%{http_code}' 2>/dev/null) || true
    http_code="${body##*$'\n'}"
    body="${body%$'\n'*}"
    if [[ "${http_code}" != "200" ]]; then
        err "apply_transcode HTTP ${http_code}"
        err "  body: ${body:0:500}"
        exit 1
    fi
    local resp="${body}"
    local sap_id task_count
    sap_id=$(printf '%s' "${resp}" | python3 -c \
        'import sys,json; print(json.load(sys.stdin)["session_application"]["id"])' 2>/dev/null || true)
    task_count=$(printf '%s' "${resp}" | python3 -c \
        'import sys,json; print(len(json.load(sys.stdin)["tasks"]))' 2>/dev/null || echo 0)
    if [[ -z "${sap_id}" ]]; then
        err "apply_transcode returned no session_application id: ${resp:0:300}"
        exit 1
    fi
    if (( task_count == 0 )); then
        err "apply_transcode queued 0 tasks — the job has no transcode-eligible tracks."
        err "Most common cause: MakeMKV failed to identify the disc and the ripper"
        err "fell back to the data-copy path (one big ISO blob, no per-title MKVs)."
        err "Hint: check the job's disc_type with:"
        err "  curl -sk -H \"Authorization: Bearer <jwt>\" ${API_BASE}/api/jobs/${job_id} | python3 -m json.tool"
        err "If disc_type=data, your MAKEMKV_KEY likely didn't reach the ripper —"
        err "re-run with --rebuild after editing services/ripper/."
        exit 1
    fi
    ok "session_application=${sap_id} with ${task_count} task(s) queued" >&2
    printf '%s\n' "${sap_id}"
}

watch_transcode() {
    local jwt="$1" sap_id="$2"
    log "polling /api/transcodes until all tasks for ${sap_id} terminal" >&2
    local deadline=$(( $(date +%s) + 1800 ))   # 30-min budget
    local last_summary=""
    while :; do
        local resp summary terminal
        if ! resp=$(curl -sfk --max-time 10 "${API_BASE}/api/transcodes" \
            -H "Authorization: Bearer ${jwt}" 2>/dev/null); then
            warn "transcode poll: curl failed; retrying in 10s"
            sleep 10
            continue
        fi
        # python prints a one-line summary on stdout and writes "TERMINAL"
        # to stderr when every task in this sap is in {done, failed}.
        # sap_id comes in via env to avoid bash-vs-python `$` confusion in
        # the heredoc (the single-quoted delimiter blocks bash expansion,
        # which would otherwise leak the literal ${sap_id} into python).
        summary=$(printf '%s' "${resp}" | SAP_ID="${sap_id}" python3 -c "$(cat <<'PYEOF'
import os, sys, json
sap = os.environ["SAP_ID"]
data = json.load(sys.stdin)
rows = [t for t in data if t.get("session_application_id") == sap]
buckets = {}
for t in rows:
    buckets[t["status"]] = buckets.get(t["status"], 0) + 1
parts = [f"{k}={v}" for k, v in sorted(buckets.items())]
print(f"{len(rows)} task(s): " + " ".join(parts))
# Empty rows is treated as terminal-with-warning here. apply_transcode
# refuses to return zero tasks, so reaching this branch means the API
# briefly hid them — never seen in practice but a belt-and-braces guard
# against an infinite poll.
if all(t["status"] in ("done", "failed") for t in rows):
    sys.stderr.write("TERMINAL\n")
PYEOF
)" 2>/tmp/iso_smoke_terminal) || true
        terminal=$(<"/tmp/iso_smoke_terminal")
        rm -f /tmp/iso_smoke_terminal
        if [[ "${summary}" != "${last_summary}" ]]; then
            log "$(date +%T) ${summary}" >&2
            last_summary="${summary}"
        fi
        if [[ "${terminal}" == "TERMINAL"* ]]; then
            ok "all transcode tasks terminal" >&2
            return 0
        fi
        if (( $(date +%s) > deadline )); then
            err "transcode poll exceeded 30 min; ${last_summary}"
            return 1
        fi
        sleep 10
    done
}

# ---- Cleanup --------------------------------------------------------------

# Cancels the ISO rip via the API if (and only if) the virtual drive is
# still live. In the common case the backend's watchdog has already
# retired it by the time we get here (the one-shot ripper exits on its
# own right after the rip ends, and the watchdog sweeps every 30s) — this
# just saves the operator that wait, and is a no-op otherwise.
cancel_iso_rip_if_live() {
    local jwt="$1" drive_id="$2"
    local body http_code
    body=$(curl -sk --max-time 10 "${API_BASE}/api/drives" -H "Authorization: Bearer ${jwt}" \
        -w '\n%{http_code}' 2>/dev/null) || true
    http_code="${body##*$'\n'}"
    body="${body%$'\n'*}"
    if [[ "${http_code}" != "200" ]]; then
        warn "cleanup: GET /api/drives HTTP ${http_code}; skipping DELETE /api/iso/rips/${drive_id}"
        return
    fi
    local live
    live=$(printf '%s' "${body}" | DRIVE_ID="${drive_id}" python3 -c '
import os, sys, json
want = os.environ["DRIVE_ID"]
rows = json.load(sys.stdin)
print("1" if any(d["id"] == want for d in rows) else "")
' 2>/dev/null || true)
    if [[ -z "${live}" ]]; then
        log "ISO drive ${drive_id} already retired — nothing to cancel"
        return
    fi
    log "DELETE /api/iso/rips/${drive_id}"
    http_code=$(curl -sk --max-time 10 -o /dev/null -w '%{http_code}' -X DELETE \
        "${API_BASE}/api/iso/rips/${drive_id}" -H "Authorization: Bearer ${jwt}" 2>/dev/null) || true
    if [[ "${http_code}" == "204" ]]; then
        ok "ISO rip cancelled"
    else
        warn "DELETE /api/iso/rips/${drive_id} HTTP ${http_code}"
    fi
}

# Installed as `trap on_exit EXIT` right after create_iso_rip, so it fires
# on every exit path (success, error, or an explicit `exit 1` — including
# the watch-deadline timeout).
on_exit() {
    if [[ -z "${ISO_DRIVE_ID:-}" ]]; then
        return
    fi
    if (( DO_CLEANUP == 0 )); then
        echo "    cleanup when done (or just wait — the watchdog retires a"
        echo "    finished rip within ~30s of its container exiting):"
        echo "      curl -sk -X DELETE ${API_BASE}/api/iso/rips/${ISO_DRIVE_ID} -H \"Authorization: Bearer \$JWT\""
        return
    fi
    cancel_iso_rip_if_live "${jwt}" "${ISO_DRIVE_ID}"
}

# ---- Summary ------------------------------------------------------------

final_summary() {
    local job_id="$1"
    local rip_secs="$2"
    local transcode_secs="${3:-}"
    local raw_dir="${DATA_DIR}/raw/${job_id}"
    local raw_total
    raw_total=$(du -cb "${raw_dir}"/*.mkv 2>/dev/null | tail -1 | awk '{print $1}' || echo 0)
    echo
    ok "ISO smoke complete"
    echo "    job_id        ${job_id}"
    echo "    raw output    ${raw_dir}/  ($(numfmt --to=iec "${raw_total}" 2>/dev/null || echo "${raw_total}B") across $(find "${raw_dir}" -name '*.mkv' 2>/dev/null | wc -l) files)"
    echo "    rip wall      ${rip_secs}s"
    if [[ -n "${transcode_secs}" ]]; then
        # Walk media/<Title> tree for the output of this run. We don't
        # know the exact title path without an API roundtrip, so just
        # report the most-recently-modified GPU-preferred batch.
        local media_dir
        media_dir=$(find "${DATA_DIR}/media" -name '*-gpu-preferred.mkv' -newer "${raw_dir}" \
            -printf '%h\n' 2>/dev/null | sort -u | head -1)
        if [[ -n "${media_dir}" ]]; then
            local media_total media_count
            media_total=$(du -cb "${media_dir}"/*-gpu-preferred.mkv 2>/dev/null | tail -1 | awk '{print $1}')
            media_count=$(find "${media_dir}" -name '*-gpu-preferred.mkv' | wc -l)
            local pct=$(( raw_total > 0 ? 100 - (media_total * 100 / raw_total) : 0 ))
            echo "    media output  ${media_dir}/  ($(numfmt --to=iec "${media_total}") across ${media_count} files, ${pct}% smaller)"
        fi
        echo "    transcode     ${transcode_secs}s"
    fi
}

# ---- Main ---------------------------------------------------------------

require_stack_up
require_ripper_image
ensure_iso
jwt=$(acquire_jwt)
key=$(resolve_makemkv_key)
apply_makemkv_key "${jwt}" "${key}"
ISO_LIBRARY_PATH=$(require_iso_library_path)
ISO_REL_PATH=$(stage_iso "${ISO_LIBRARY_PATH}")

rip_start=$(date +%s)
ISO_DRIVE_ID=$(create_iso_rip "${jwt}" "${ISO_REL_PATH}")
trap on_exit EXIT
job_id=$(watch_until_ripped "${jwt}" "${ISO_DRIVE_ID}")
rip_end=$(date +%s)
rip_secs=$(( rip_end - rip_start ))

if (( DO_TRANSCODE == 0 )); then
    final_summary "${job_id}" "${rip_secs}"
    echo
    echo "    apply transcode (skipped — --no-transcode):"
    echo "      JWT=\$(curl -sk ${API_BASE}/api/auth/login \\"
    echo "        -H 'Content-Type: application/json' \\"
    echo "        -d '{\"username\":\"admin\",\"password\":\"<your password>\"}' \\"
    echo "        | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"access_token\"])')"
    echo "      curl -sk -X POST ${API_BASE}/api/jobs/${job_id}/transcode \\"
    echo "        -H \"Authorization: Bearer \$JWT\" -H 'Content-Type: application/json' \\"
    echo "        -d '{\"session_id\":\"${SESSION_ID}\",\"overwrite\":false}'"
    exit 0
fi

sap_id=$(apply_transcode "${jwt}" "${job_id}" "${SESSION_ID}")
transcode_start=$(date +%s)
watch_transcode "${jwt}" "${sap_id}"
transcode_end=$(date +%s)
transcode_secs=$(( transcode_end - transcode_start ))

final_summary "${job_id}" "${rip_secs}" "${transcode_secs}"
