#!/usr/bin/env bash
# Download + filter the FindVUK community keydb.cfg for MakeMKV.
#
# MakeMKV's HK server is dead, so it can no longer derive AACS volume keys on
# its own. This fetches the community keydb.cfg from the FindVUK Online Database
# and strips | DK | / | PK | entries that conflict with MakeMKV's internal AACS
# engine, keeping only | V | (VUK) entries.
#
# Gating: ARM_COMMUNITY_KEYDB env var (the ripper injects it from the
# community_keydb_enabled Config toggle). Default true when unset.
# Age-gated: skips if the on-disk keydb is < MAX_AGE_DAYS old; --force bypasses
# both the age and enable gates.
# Non-fatal: every failure path exits 0 after emitting a `keydb-status:` line and
# preserving the existing keydb. Atomic install via .tmp + mv.
#
# The final `keydb-status: <state> [vuk=<n>] [age_days=<n>]` line is the contract
# parsed by arm_ripper/community_keydb.py.
set -euo pipefail

# Plain http:// is intentional — the FindVUK host offers no HTTPS at this URL.
# Integrity is checked structurally below (curl -f rejects error responses, the
# `file` ZIP check rejects HTML pages, and the VUK-entry assert rejects junk).
# Do not "upgrade" to https:// — it 404s.
KEYDB_URL="http://fvonline-db.bplaced.net/fv_download.php?lang=eng"
MAKEMKV_DIR="${HOME:-/home/arm}/.MakeMKV"
KEYDB_FILE="$MAKEMKV_DIR/keydb.cfg"
MAX_AGE_DAYS=7
MAX_RETRIES=3
CURL_CONNECT_TIMEOUT=15
CURL_MAX_TIME=600
CURL_SPEED_LIMIT=1024
CURL_SPEED_TIME=30

FORCE=false
[[ "${1:-}" == "--force" ]] && FORCE=true

# Enable gate — env only (v3 owns the toggle in the DB; no arm.yaml).
enabled="${ARM_COMMUNITY_KEYDB:-true}"
enabled="${enabled,,}"
if [[ "$FORCE" == false && "$enabled" != "true" ]]; then
    echo "keydb-status: disabled"
    exit 0
fi

# Age gate.
if [[ "$FORCE" == false && -f "$KEYDB_FILE" ]]; then
    file_age=$(( ( $(date +%s) - $(stat -c %Y "$KEYDB_FILE") ) / 86400 ))
    if (( file_age < MAX_AGE_DAYS )); then
        echo "keydb.cfg is ${file_age}d old (< ${MAX_AGE_DAYS}d) — skipping"
        echo "keydb-status: fresh_kept age_days=${file_age}"
        exit 0
    fi
fi

mkdir -p "$MAKEMKV_DIR"
TMPDIR_KDB=$(mktemp -d)
trap 'rm -rf "$TMPDIR_KDB"' EXIT
ZIP_FILE="$TMPDIR_KDB/keydb.zip"
RAW_KEYDB="$TMPDIR_KDB/keydb_raw.cfg"
FILTERED_KEYDB="$TMPDIR_KDB/keydb.cfg"

echo "Downloading keydb from FindVUK..."
download_ok=false
for attempt in $(seq 1 "$MAX_RETRIES"); do
    if curl -fsSL \
        --connect-timeout "$CURL_CONNECT_TIMEOUT" \
        --max-time "$CURL_MAX_TIME" \
        --speed-limit "$CURL_SPEED_LIMIT" \
        --speed-time "$CURL_SPEED_TIME" \
        -o "$ZIP_FILE" "$KEYDB_URL"; then
        download_ok=true
        break
    fi
    if [[ "$attempt" -lt "$MAX_RETRIES" ]]; then
        sleep $(( attempt * 5 ))
    fi
done
if [[ "$download_ok" == false ]]; then
    echo "keydb-status: download_failed"
    exit 0
fi

if ! file "$ZIP_FILE" | grep -q 'Zip archive'; then
    echo "keydb-status: empty"
    exit 0
fi

if ! ZIP_FILE="$ZIP_FILE" RAW_KEYDB="$RAW_KEYDB" python3 -c '
import os, zipfile, sys
with zipfile.ZipFile(os.environ["ZIP_FILE"]) as z:
    cfg = [n for n in z.namelist() if n.endswith("keydb.cfg")]
    if not cfg:
        sys.exit(1)
    with open(os.environ["RAW_KEYDB"], "wb") as fh:
        fh.write(z.read(cfg[0]))
'; then
    echo "keydb-status: empty"
    exit 0
fi

grep -v '| DK |' "$RAW_KEYDB" | grep -v '| PK |' > "$FILTERED_KEYDB" || true

vuk_count=$(grep -c '| V |' "$FILTERED_KEYDB" || true)
if [[ "${vuk_count:-0}" -lt 1 ]]; then
    echo "keydb-status: empty"
    exit 0
fi

cp "$FILTERED_KEYDB" "${KEYDB_FILE}.tmp"
mv "${KEYDB_FILE}.tmp" "$KEYDB_FILE"
chown arm:arm "$KEYDB_FILE" 2>/dev/null || true

echo "keydb-status: ok vuk=${vuk_count}"
exit 0
