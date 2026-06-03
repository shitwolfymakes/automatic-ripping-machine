#!/usr/bin/env bash
# Phase 15 — ISO-source smoke test for the ripper.
#
# Runs the full scan → identify → rip pipeline against a Sintel ISO
# fixture (no physical disc required). Ticks the cutover criterion that
# was deferred to v3.1 as "the BBB ISO rig" but pulled forward into v3.0
# via the ARM_MANUAL_TRIGGER_ISO env var.
#
# Pipeline:
#   1. Sintel ISO comes from the matrix256-corpus image — pulled from
#      GHCR (Docker Hub fallback), `docker cp` just sintel.iso out so
#      the BBB layer doesn't burn 8.5 GB of host disk. SHA-256 verified
#      against the corpus.lock pin. Cache at ~/arm-corpus/ by default.
#      Last-resort fallback: direct fetch from archive.org.
#   2. MakeMKV key: env var first (MAKEMKV_PERMA_KEY), then a single
#      forum-scrape attempt. Container-boot scrape is flaky (Cloudflare
#      525), so an explicit key keeps the smoke deterministic.
#   3. The live `arm-ripper-sr0` service is stopped (poll-loop ripper
#      and ISO-mode ripper conflict on the same drive_id registration).
#   4. One-shot `docker run --privileged` of the ripper image with
#      ARM_MANUAL_TRIGGER_ISO and the ISO bind-mounted at /corpus.
#   5. Logs are tailed until rip-complete; the script reports the job_id
#      so the operator can chain `POST /api/jobs/{id}/transcode`.
#   6. The ripper container is left running (it idles after the one-shot
#      so the WS subscription stays open for cancellation). Stop with
#      `docker stop armv3-ripper-iso` when done; the existing
#      arm-ripper-sr0 service is NOT auto-restarted — bring it back with
#      `docker compose up -d arm-ripper-sr0` when you're done with the
#      ISO smoke.
#
# Idempotent. Safe to re-run.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
V3_DIR="$(cd -- "${SCRIPT_DIR}/.." &>/dev/null && pwd)"
COMPOSE=( docker compose -f "${V3_DIR}/docker-compose.yml" )

CACHE_DIR="${ISO_CACHE_DIR:-${HOME}/arm-corpus}"
ISO_NAME="sintel.iso"
ISO_PATH="${CACHE_DIR}/${ISO_NAME}"
ISO_SHA256="7ea69a0215cdd7fff4acb48976677b2814a3d2e375b82b3288324bb356afe803"
ISO_SIZE_BYTES=3881467904

CORPUS_IMAGE_GHCR="ghcr.io/shitwolfymakes/matrix256-corpus:latest"
CORPUS_IMAGE_HUB="docker.io/shitwolfymakes/matrix256-corpus:latest"
ARCHIVE_URL="https://archive.org/download/sintel_20260427/sintel.iso"

RIPPER_IMAGE="armv3-arm-ripper-sr0"
RIPPER_CTR="armv3-ripper-iso"
RIPPER_SERVICE="arm-ripper-sr0"
COMPOSE_NETWORK="armv3_default"
MAKEMKV_FORUM_URL="https://forum.makemkv.com/forum/viewtopic.php?f=5&t=1053"

log() { printf '\033[1;36m→\033[0m %s\n' "$*"; }
ok()  { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*" >&2; }
err() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; }

show_help() {
    sed -n '2,32p' "$0" | sed 's/^# \?//'
    cat <<'EOF'

Usage: iso-smoke.sh [--help]

Environment variables:
  ISO_CACHE_DIR       Where the Sintel ISO is cached (default: ~/arm-corpus)
  MAKEMKV_PERMA_KEY   MakeMKV beta key (overrides forum scrape)
EOF
}

for arg in "$@"; do
    case "$arg" in
        --help|-h) show_help; exit 0 ;;
        *) err "unknown arg: $arg"; exit 2 ;;
    esac
done

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
    if [[ -n "${MAKEMKV_PERMA_KEY:-}" ]]; then
        ok "MAKEMKV_PERMA_KEY from environment" >&2
        printf '%s\n' "${MAKEMKV_PERMA_KEY}"
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
        err "Workaround: set MAKEMKV_PERMA_KEY=<key> and re-run (one-time per month)."
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
        err "Workaround: set MAKEMKV_PERMA_KEY=<key> and re-run."
        exit 1
    fi
    ok "scraped key: ${key:0:8}…${key: -8}" >&2
    printf '%s\n' "${key}"
}

# ---- Stack preflight -----------------------------------------------------

require_stack_up() {
    for ctr in armv3-backend armv3-db; do
        if ! docker ps --format '{{.Names}}' | grep -qx "${ctr}"; then
            err "${ctr} is not running"
            err "bring the stack up first: cd ${V3_DIR} && docker compose up -d arm-db arm-backend arm-ui"
            exit 1
        fi
    done
    ok "backend + db running"
}

require_ripper_image() {
    if ! docker image inspect "${RIPPER_IMAGE}" >/dev/null 2>&1; then
        log "building ${RIPPER_IMAGE}"
        ( cd "${V3_DIR}" && "${COMPOSE[@]}" build "${RIPPER_SERVICE}" )
    fi
    ok "ripper image present: ${RIPPER_IMAGE}"
}

stop_live_ripper() {
    if docker ps --format '{{.Names}}' | grep -qx "armv3-ripper-sr0"; then
        log "stopping the live arm-ripper-sr0 (conflicts with the ISO-mode ripper on the same drive_id)"
        ( cd "${V3_DIR}" && "${COMPOSE[@]}" stop "${RIPPER_SERVICE}" >/dev/null )
        ok "armv3-ripper-sr0 stopped"
    fi
    # Clean up a prior ISO-mode container if one is still running.
    if docker ps -a --format '{{.Names}}' | grep -qx "${RIPPER_CTR}"; then
        log "removing prior ${RIPPER_CTR}"
        docker rm -f "${RIPPER_CTR}" >/dev/null
    fi
}

# ---- Run ----------------------------------------------------------------

run_iso_ripper() {
    local key="$1"

    # The compose .env holds ARM_SERVICE_TOKEN; the backend container
    # expects the same value.
    # shellcheck disable=SC1091
    . "${V3_DIR}/.env"

    log "launching one-shot ripper: ${RIPPER_CTR}"
    docker run --rm -d \
        --name "${RIPPER_CTR}" \
        --network "${COMPOSE_NETWORK}" \
        --hostname "arm-ripper-iso" \
        --privileged \
        -e ARM_DRIVE_DEV=/dev/sr0 \
        -e ARM_BACKEND_URL=https://arm-backend:8443 \
        -e ARM_SERVICE_TOKEN="${ARM_SERVICE_TOKEN}" \
        -e ARM_LOG_LEVEL="${ARM_LOG_LEVEL:-info}" \
        -e ARM_MANUAL_TRIGGER_ISO=/corpus/sintel.iso \
        -e MAKEMKV_PERMA_KEY="${key}" \
        -e PUID="${PUID:-1000}" -e PGID="${PGID:-1000}" -e CDROM_GID="${CDROM_GID:-24}" \
        -v "${CACHE_DIR}:/corpus:ro" \
        -v "${V3_DIR}/raw:/raw" \
        -v "${V3_DIR}/logs:/logs" \
        -v "${V3_DIR}/certs/arm-ca.crt:/etc/ssl/arm/arm-ca.crt:ro" \
        -v "${V3_DIR}/certs/arm-ripper-sr0.crt:/etc/ssl/arm/tls.crt:ro" \
        -v "${V3_DIR}/certs/arm-ripper-sr0.key:/etc/ssl/arm/tls.key:ro" \
        "${RIPPER_IMAGE}" >/dev/null
    ok "${RIPPER_CTR} up"
}

# ---- Watch --------------------------------------------------------------

watch_until_complete() {
    log "tailing logs until rip-complete (or 15-min timeout)"
    local deadline=$(( $(date +%s) + 900 ))
    local job_id=""
    # `docker logs -f` keeps streaming after rip-complete (container idles
    # forever by design). Read line-by-line and exit when the milestone
    # arrives, with a deadline so an actual hang doesn't hang the script.
    while IFS= read -r line; do
        # rip-start carries the job_id; rip-complete is the terminal milestone.
        if [[ -z "${job_id}" && "${line}" == *'"msg": "rip-start'* ]]; then
            job_id=$(printf '%s' "${line}" | grep -oP 'job_id=\K[^ ]+' || true)
            [[ -n "${job_id}" ]] && log "rip started: ${job_id}"
        fi
        if [[ "${line}" == *'"msg": "rip-complete'* ]]; then
            ok "rip-complete observed"
            break
        fi
        if (( $(date +%s) > deadline )); then
            err "deadline exceeded (15 min); ripper container left running for inspection"
            exit 1
        fi
    done < <(docker logs -f "${RIPPER_CTR}" 2>&1)

    if [[ -z "${job_id}" ]]; then
        warn "rip-complete fired but no job_id observed in the stream — check the backend log"
        return
    fi

    echo
    ok "smoke complete — job_id=${job_id}"
    echo "    raw output:   ${V3_DIR}/raw/${job_id}/"
    echo "    apply transcode:"
    echo "      JWT=\$(curl -sk https://localhost:8081/api/auth/login \\"
    echo "        -H 'Content-Type: application/json' \\"
    echo "        -d '{\"username\":\"admin\",\"password\":\"<your password>\"}' \\"
    echo "        | python -c 'import sys,json; print(json.load(sys.stdin)[\"access_token\"])')"
    echo "      curl -sk -X POST https://localhost:8081/api/jobs/${job_id}/transcode \\"
    echo "        -H \"Authorization: Bearer \$JWT\" -H 'Content-Type: application/json' \\"
    echo "        -d '{\"session_id\":\"ses_builtin_movie_plex_1080p_gpu\",\"overwrite\":false}'"
    echo
    echo "    cleanup when done:"
    echo "      docker stop ${RIPPER_CTR}"
    echo "      cd ${V3_DIR} && docker compose up -d ${RIPPER_SERVICE}"
}

# ---- Main ---------------------------------------------------------------

require_stack_up
require_ripper_image
ensure_iso
key=$(resolve_makemkv_key)
stop_live_ripper
run_iso_ripper "${key}"
watch_until_complete
