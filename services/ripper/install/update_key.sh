#!/usr/bin/env bash
# Refresh the MakeMKV app_Key in ~/.MakeMKV/settings.conf.
#
# - If MAKEMKV_KEY is set in the environment (or passed as $1), use it.
#   Any value MakeMKV accepts — a purchased perma-key, a monthly beta
#   pasted in by the operator, or a beta key already scraped externally.
# - Otherwise scrape the current month's free beta key from the public
#   MakeMKV forum thread, mirroring v2's behaviour
#   (see scripts/update_key.sh in the v2 tree).
#
# Idempotent. Safe to invoke on every container start. Failures are
# non-fatal — the entrypoint masks the exit code so a transient scrape
# failure cannot block boot.
set -euo pipefail

makemkv_serial_url="https://forum.makemkv.com/forum/viewtopic.php?f=5&t=1053"
SUPPLIED_KEY="${MAKEMKV_KEY:-${1:-}}"

if [[ -n "$SUPPLIED_KEY" ]]; then
    echo "update_key: using MAKEMKV_KEY from env"
    KEY="$SUPPLIED_KEY"
else
    echo "update_key: scraping monthly beta key from forum"
    KEY="$(curl -fsSL "$makemkv_serial_url" | grep -oP 'T-[\w\d@]{66}' | head -n1 || true)"
    if [[ -z "$KEY" ]]; then
        echo "update_key: no beta key found in scrape; leaving settings.conf untouched" >&2
        exit 0
    fi
fi

MAKEMKV_DIR="${HOME:-/home/arm}/.MakeMKV"
mkdir -p "$MAKEMKV_DIR"
SETTINGS_FILE="$MAKEMKV_DIR/settings.conf"

if [[ ! -f "$SETTINGS_FILE" ]] || ! grep -q "app_Key" "$SETTINGS_FILE"; then
    echo "app_Key = \"$KEY\"" >> "$SETTINGS_FILE"
else
    sed -i "s|app_Key = \"T-.*\"|app_Key = \"$KEY\"|" "$SETTINGS_FILE"
fi

echo "update_key: settings.conf written at $SETTINGS_FILE"
