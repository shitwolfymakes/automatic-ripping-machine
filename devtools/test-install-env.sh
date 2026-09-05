#!/usr/bin/env bash
# Plain-bash unit test for install.sh's PUID/PGID handling.
# No bats — the repo gates shell with shellcheck only. Runs with no Docker,
# no root: it sources install.sh (via ARM_INSTALL_SOURCE_ONLY) and drives
# require_unprivileged / resolve_puid_pgid / seed_env against a temp prefix.
#
# Covers the deploy-test regression: running the installer under sudo seeded
# PUID/PGID=0:0 (container groupadd --gid 0 collides with the root group), and
# re-runs sed-clobbered hand-fixed values back to the broken derivation.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL="${HERE}/../install.sh"

# The suite exercises the non-root derivation paths (fresh seed / heal expect
# id -u/id -g to be valid container ids). A root runner would fail them all.
if [[ "$(id -u)" -eq 0 ]]; then
    echo "SKIP: test-install-env.sh must run as a non-root user"
    exit 0
fi

# Fail fast if the source-only seam is missing: sourcing without it would run
# main() — prereq checks, cert generation, a GitHub API call — on this machine.
if ! grep -q 'ARM_INSTALL_SOURCE_ONLY' "$INSTALL"; then
    echo "FAIL - install.sh has no ARM_INSTALL_SOURCE_ONLY seam; refusing to source it" >&2
    exit 1
fi

export ARM_INSTALL_SOURCE_ONLY=1
# shellcheck disable=SC1090
source "$INSTALL"

# seed_env probes host GPUs via docker; stub the probes out.
# shellcheck disable=SC2329,SC2317  # invoked indirectly by the sourced seed_env
detect_gpus() { printf '[]'; }
# shellcheck disable=SC2329,SC2317  # invoked indirectly by the sourced seed_env
detect_render_gid() { printf ''; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail=0
check() {  # check <label> <expected> <actual>
    local label="$1" want="$2" got="$3"
    if [[ "$want" == "$got" ]]; then
        echo "ok   - ${label}"
    else
        echo "FAIL - ${label}: expected '${want}', got '${got}'" >&2
        fail=1
    fi
}

env_get() {  # env_get <file> <key>
    sed -nE "s/^$2=(.*)$/\1/p" "$1" | head -n1
}

MY_UID="$(id -u)"
MY_GID="$(id -g)"

# --- require_unprivileged ----------------------------------------------------

# 1. Normal unprivileged run passes.
rc=0; ( ARM_INSTALL_EUID="$MY_UID" require_unprivileged ) >/dev/null 2>&1 || rc=$?
check "unprivileged run accepted" 0 "$rc"

# 2. Root without explicit PUID/PGID is refused (the sudo footgun).
rc=0; ( ARM_INSTALL_EUID=0 PUID="" PGID="" require_unprivileged ) >/dev/null 2>&1 || rc=$?
check "root run refused" 1 "$rc"

# 3. Root with a valid explicit PUID/PGID is allowed (unattended escape hatch).
rc=0; ( ARM_INSTALL_EUID=0 PUID=1000 PGID=1000 require_unprivileged ) >/dev/null 2>&1 || rc=$?
check "root + explicit PUID/PGID accepted" 0 "$rc"

# 4. Root with an explicit 0 is still refused — 0 is never a valid gosu target.
rc=0; ( ARM_INSTALL_EUID=0 PUID=0 PGID=0 require_unprivileged ) >/dev/null 2>&1 || rc=$?
check "root + explicit 0:0 refused" 1 "$rc"

# --- resolve_puid_pgid ---------------------------------------------------------

# 5. Defaults to the invoking user.
got="$( PUID="" PGID="" resolve_puid_pgid; printf '%s:%s' "$ARM_PUID" "$ARM_PGID" )"
check "resolve defaults to id -u:id -g" "${MY_UID}:${MY_GID}" "$got"

# 6. Env override wins.
got="$( PUID=1234 PGID=4321 resolve_puid_pgid; printf '%s:%s' "$ARM_PUID" "$ARM_PGID" )"
check "resolve honors PUID/PGID env override" "1234:4321" "$got"

# 7. Non-numeric override is rejected.
rc=0; ( PUID=abc PGID=1000 resolve_puid_pgid ) >/dev/null 2>&1 || rc=$?
check "resolve rejects non-numeric PUID" 1 "$rc"

# 8. Zero override is rejected.
rc=0; ( PUID=1000 PGID=0 resolve_puid_pgid ) >/dev/null 2>&1 || rc=$?
check "resolve rejects PGID=0" 1 "$rc"

# 9. Leading-zero override is rejected (useradd/groupadd would re-parse it).
rc=0; ( PUID=010 PGID=1000 resolve_puid_pgid ) >/dev/null 2>&1 || rc=$?
check "resolve rejects leading-zero PUID" 1 "$rc"

# --- seed_env: fresh install ---------------------------------------------------

PREFIX="$TMP/fresh"
mkdir -p "$PREFIX"
PUID="" PGID="" resolve_puid_pgid
log_out="$(seed_env)"
check "fresh seed log states PUID:PGID" "yes" \
    "$( [[ "$log_out" == *"PUID:PGID ${MY_UID}:${MY_GID}"* ]] && echo yes || echo no )"
check "fresh seed PUID" "$MY_UID" "$(env_get "$PREFIX/.env" PUID)"
check "fresh seed PGID" "$MY_GID" "$(env_get "$PREFIX/.env" PGID)"
check "fresh seed has secrets" "yes" "$( [[ -n "$(env_get "$PREFIX/.env" ARM_SERVICE_TOKEN)" ]] && echo yes || echo no )"

# --- seed_env: re-run preserves operator-set PUID/PGID -------------------------

# 2345:6789 are arbitrary fixture values — deliberately unlike any real host's
# ids, so nobody mistakes them for a supported default.
PREFIX="$TMP/rerun"
mkdir -p "$PREFIX"
cat > "$PREFIX/.env" <<'EOF'
POSTGRES_PASSWORD=keepme
ARM_SERVICE_TOKEN=keepme-too
PUID=2345
PGID=6789
CDROM_GID=99
ARM_GPUS=[]
ARM_RENDER_GID=
EOF
PUID="" PGID="" resolve_puid_pgid
log_out="$(seed_env)"
check "rerun log states the preserved values" "yes" \
    "$( [[ "$log_out" == *"preserving secrets + PUID/PGID 2345:6789"* ]] && echo yes || echo no )"
check "rerun preserves hand-set PUID" "2345" "$(env_get "$PREFIX/.env" PUID)"
check "rerun preserves hand-set PGID" "6789" "$(env_get "$PREFIX/.env" PGID)"
check "rerun preserves secrets" "keepme" "$(env_get "$PREFIX/.env" POSTGRES_PASSWORD)"
check "rerun still re-derives CDROM_GID" "yes" "$( [[ "$(env_get "$PREFIX/.env" CDROM_GID)" != "99" ]] && echo yes || echo no )"

# --- seed_env: re-run heals a broken 0:0 seed ----------------------------------

PREFIX="$TMP/heal"
mkdir -p "$PREFIX"
cat > "$PREFIX/.env" <<'EOF'
POSTGRES_PASSWORD=keepme
PUID=0
PGID=0
CDROM_GID=44
EOF
PUID="" PGID="" resolve_puid_pgid
seed_env >/dev/null 2>&1
check "rerun heals PUID=0" "$MY_UID" "$(env_get "$PREFIX/.env" PUID)"
check "rerun heals PGID=0" "$MY_GID" "$(env_get "$PREFIX/.env" PGID)"

# --- seed_env: explicit env override beats existing .env values ----------------

PREFIX="$TMP/override"
mkdir -p "$PREFIX"
cat > "$PREFIX/.env" <<'EOF'
POSTGRES_PASSWORD=keepme
PUID=2345
PGID=6789
CDROM_GID=44
EOF
PUID=2000 PGID=2000 resolve_puid_pgid
seed_env >/dev/null
check "rerun explicit override wins over .env" "2000:2000" \
    "$(env_get "$PREFIX/.env" PUID):$(env_get "$PREFIX/.env" PGID)"

# --- seed_env: missing PUID/PGID lines get appended, not lost ------------------

PREFIX="$TMP/missing"
mkdir -p "$PREFIX"
cat > "$PREFIX/.env" <<'EOF'
POSTGRES_PASSWORD=keepme
CDROM_GID=44
EOF
PUID="" PGID="" resolve_puid_pgid
seed_env >/dev/null 2>&1
check "rerun appends missing PUID" "$MY_UID" "$(env_get "$PREFIX/.env" PUID)"
check "rerun appends missing PGID" "$MY_GID" "$(env_get "$PREFIX/.env" PGID)"

# --- seed_env: half-edited .env keeps its valid half ---------------------------

PREFIX="$TMP/mixed"
mkdir -p "$PREFIX"
cat > "$PREFIX/.env" <<'EOF'
POSTGRES_PASSWORD=keepme
PUID=2345
PGID=0
EOF
PUID="" PGID="" resolve_puid_pgid
seed_env >/dev/null 2>&1
check "mixed .env keeps valid PUID" "2345" "$(env_get "$PREFIX/.env" PUID)"
check "mixed .env heals only broken PGID" "$MY_GID" "$(env_get "$PREFIX/.env" PGID)"
check "mixed .env gets missing CDROM_GID appended" "yes" \
    "$( [[ -n "$(env_get "$PREFIX/.env" CDROM_GID)" ]] && echo yes || echo no )"

# --- seed_env: CRLF-edited .env values are sanitized, not clobbered ------------

PREFIX="$TMP/crlf"
mkdir -p "$PREFIX"
printf 'POSTGRES_PASSWORD=keepme\nPUID=2345\r\nPGID=6789\r\nCDROM_GID=44\n' > "$PREFIX/.env"
PUID="" PGID="" resolve_puid_pgid
seed_env >/dev/null 2>&1
check "CRLF .env keeps hand-set PUID" "2345" "$(env_get "$PREFIX/.env" PUID)"
check "CRLF .env keeps hand-set PGID" "6789" "$(env_get "$PREFIX/.env" PGID)"

# --- resolve: a non-root user whose PRIMARY GROUP is gid 0 must be rejected ----

# Shadow `id` with a function (wins over the binary) — no production seam needed.
# shellcheck disable=SC2329,SC2317  # invoked indirectly by the sourced resolve_puid_pgid
id() { case "${1:-}" in -u) echo 1000 ;; -g) echo 0 ;; *) command id "$@" ;; esac; }
rc=0; ( PUID="" PGID="" resolve_puid_pgid ) >/dev/null 2>&1 || rc=$?
unset -f id
check "resolve rejects derived primary gid 0" 1 "$rc"

exit "$fail"
