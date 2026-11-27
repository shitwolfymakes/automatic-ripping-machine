#!/usr/bin/env bash
# Refresh the MakeMKV app_Key in ~/.MakeMKV/settings.conf.
#
# - If MAKEMKV_KEY is set in the environment (or passed as $1), use it.
#   Any value MakeMKV accepts — a purchased perma-key, a monthly beta
#   pasted in by the operator, or a beta key already scraped externally.
# - Otherwise scrape the current month's free beta key from the public
#   MakeMKV forum thread.
#
# Idempotent. Safe to invoke on every container start. Failures are
# non-fatal — the entrypoint masks the exit code so a transient scrape
# failure cannot block boot.
set -euo pipefail

makemkv_serial_url="https://forum.makemkv.com/forum/viewtopic.php?f=5&t=1053"
SUPPLIED_KEY="${MAKEMKV_KEY:-${1:-}}"

# Optional internal mirror: when MAKEMKV_MIRROR_URL is set,
# $MAKEMKV_MIRROR_URL/beta-key.txt is the FALLBACK after the forum scrape —
# upstream first, so a stale key on the mirror never shadows a fresh one.
# MAKEMKV_MIRROR_PASSWORD (optional) is sent as an X-SHARE-PASSWORD header
# (Filebrowser password-protected shares).
mirror_key() {
    local args=(-fsSL)
    if [[ -n "${MAKEMKV_MIRROR_PASSWORD:-}" ]]; then
        args+=(-H "X-SHARE-PASSWORD: ${MAKEMKV_MIRROR_PASSWORD}")
    fi
    curl "${args[@]}" "${MAKEMKV_MIRROR_URL}/beta-key.txt" | grep -oP 'T-[\w\d@]{66}' | head -n1
}

if [[ -n "$SUPPLIED_KEY" ]]; then
    echo "update_key: using MAKEMKV_KEY from env"
    KEY="$SUPPLIED_KEY"
else
    echo "update_key: scraping monthly beta key from forum"
    KEY="$(curl -fsSL "$makemkv_serial_url" | grep -oP 'T-[\w\d@]{66}' | head -n1 || true)"
    if [[ -z "$KEY" && -n "${MAKEMKV_MIRROR_URL:-}" ]]; then
        echo "update_key: forum scrape failed; falling back to the mirror" >&2
        KEY="$(mirror_key || true)"
    fi
    if [[ -z "$KEY" ]]; then
        echo "update_key: no beta key found in scrape; leaving settings.conf untouched" >&2
        exit 0
    fi
fi

MAKEMKV_DIR="${HOME:-/home/arm}/.MakeMKV"
mkdir -p "$MAKEMKV_DIR"
SETTINGS_FILE="$MAKEMKV_DIR/settings.conf"

# One atomic rewrite (tmp in the same dir + mv): replaces any stored key form
# (T-, M-, ...) and cannot leave a half-written file when several rippers
# share the persisted ~/.MakeMKV volume. grep -v exits 1 when nothing is left
# to keep (new or empty file), which is fine.
tmp="$(mktemp "$SETTINGS_FILE.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
if [[ -f "$SETTINGS_FILE" ]]; then
    grep -v '^app_Key' "$SETTINGS_FILE" > "$tmp" || true
fi
echo "app_Key = \"$KEY\"" >> "$tmp"
mv "$tmp" "$SETTINGS_FILE"

echo "update_key: settings.conf written at $SETTINGS_FILE"
