#!/usr/bin/env bash
# Download + install MakeMKV's SDF (Service Decryption File).
#
# MakeMKV downloads its SDF from its own server on every launch; when that
# server is slow/unreachable the scan hangs ~90s then fails to enumerate
# titles on protected discs (→ ARM mislabels the disc as `data`). Pre-placing
# a current sdf.bin in the data dir stops the download attempt entirely.
#
# Gating: ARM_MAKEMKV_SDF env (the ripper injects it from the
# makemkv_sdf_enabled Config toggle). Default true when unset. --force bypasses
# both the age and enable gates.
# Age-gated via a `.sdf_refreshed` sentinel — NOT sdf.bin's mtime, because
# MakeMKV consumes sdf.bin into _private_data.tar on launch and deletes it.
# Non-fatal: every path exits 0 after emitting an `sdf-status:` line and
# preserving the existing/baked SDF. Atomic install via .tmp + mv.
#
# The final `sdf-status: <state> [age_days=<n>]` line is the contract parsed
# by arm_ripper/makemkv_sdf.py.
set -euo pipefail

SDF_URL_PRIMARY="https://www.makemkv.com/svq/sdf.bin"
SDF_URL_MIRROR="https://www.makemkv.info/svq/sdf.bin"
MAKEMKV_DIR="${HOME:-/home/arm}/.MakeMKV"
SDF_FILE="$MAKEMKV_DIR/sdf.bin"
SENTINEL="$MAKEMKV_DIR/.sdf_refreshed"
MAX_AGE_DAYS=7
CURL_CONNECT_TIMEOUT=15
CURL_MAX_TIME=120
MIN_SIZE=262144      # 256 KiB — reject HTML error pages
MAX_SIZE=16777216    # 16 MiB — sanity ceiling (real file ~2.1 MiB)

FORCE=false
[[ "${1:-}" == "--force" ]] && FORCE=true

# Enable gate — env only.
enabled="${ARM_MAKEMKV_SDF:-true}"
enabled="${enabled,,}"
if [[ "$FORCE" == false && "$enabled" != "true" ]]; then
    echo "sdf-status: disabled"
    exit 0
fi

# Age gate — keyed off the sentinel (survives MakeMKV consuming sdf.bin).
if [[ "$FORCE" == false && -f "$SENTINEL" ]]; then
    file_age=$(( ( $(date +%s) - $(stat -c %Y "$SENTINEL") ) / 86400 ))
    if (( file_age < MAX_AGE_DAYS )); then
        echo "sdf.bin sentinel is ${file_age}d old (< ${MAX_AGE_DAYS}d) — skipping" >&2
        echo "sdf-status: fresh_kept age_days=${file_age}"
        exit 0
    fi
fi

mkdir -p "$MAKEMKV_DIR"
TMP=$(mktemp "${SDF_FILE}.XXXXXX")
trap 'rm -f "$TMP"' EXIT

download_one() {
    local url="$1"
    curl -fsSL --connect-timeout "$CURL_CONNECT_TIMEOUT" --max-time "$CURL_MAX_TIME" -o "$TMP" "$url"
}

valid_sdf() {
    # Non-empty, within size bounds, and not an HTML page (first byte not '<').
    local size
    size=$(stat -c %s "$TMP" 2>/dev/null || echo 0)
    (( size >= MIN_SIZE && size <= MAX_SIZE )) || return 1
    local first
    first=$(head -c 1 "$TMP" 2>/dev/null || true)
    [[ "$first" != "<" ]] || return 1
    return 0
}

downloaded=false
for url in "$SDF_URL_PRIMARY" "$SDF_URL_MIRROR"; do
    if download_one "$url" && valid_sdf; then
        downloaded=true
        break
    fi
done

if [[ "$downloaded" == false ]]; then
    echo "sdf-status: download_failed"
    exit 0
fi

mv "$TMP" "$SDF_FILE" || { echo "sdf-status: download_failed"; exit 0; }
trap - EXIT
chown arm:arm "$SDF_FILE" 2>/dev/null || true
touch "$SENTINEL"
chown arm:arm "$SENTINEL" 2>/dev/null || true

echo "sdf-status: updated"
exit 0
