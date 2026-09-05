#!/usr/bin/env bash
# Optional internal-mirror seam — sourced, never executed.
#
# POSIX sh only: this is sourced both by bash scripts and by Dockerfile RUN
# steps (/bin/sh). Keep it free of bashisms.
#
# Everything mirror-related lives here so the feature can be removed in one
# step: delete this file, drop the `source` line + the mirror_url_for call
# from each consumer, and the callers fall back to their upstream URLs alone.
#
# Contract: upstream first, mirror LAST. The mirror is a fallback for when an
# upstream host is down (see the 2026-09 makemkv.com 525 outage), not a
# replacement — so an unset, stale, or broken mirror can never change the
# result of a build that upstream could satisfy on its own.
#
# MAKEMKV_MIRROR_URL      base URL; unset disables every mirror path.
# MAKEMKV_MIRROR_PASSWORD optional X-SHARE-PASSWORD header (Filebrowser
#                         password-protected shares).
#
# Layout expected under $MAKEMKV_MIRROR_URL (matches install_makemkv.sh):
#   LATEST, <ver>/makemkv-{sha,oss,bin}-<ver>.*, beta-key.txt, sdf.bin

# mirror_url_for <relative-path> — echo the mirror URL for an asset, or
# nothing when no mirror is configured. Callers append the result to their
# upstream candidates, so an empty value simply adds no candidate.
mirror_url_for() {
    [ -n "${MAKEMKV_MIRROR_URL:-}" ] || return 0
    printf '%s/%s\n' "${MAKEMKV_MIRROR_URL%/}" "$1"
}

# mirror_curl_args — echo extra curl args for mirror requests (the share
# password header, when set). Safe to use on upstream URLs too: the header is
# ignored by hosts that do not expect it, but callers should prefer applying
# it only to mirror URLs (see mirror_is_mirror_url).
mirror_curl_args() {
    [ -n "${MAKEMKV_MIRROR_PASSWORD:-}" ] || return 0
    printf '%s\n' "-H" "X-SHARE-PASSWORD: ${MAKEMKV_MIRROR_PASSWORD}"
}

# mirror_is_mirror_url <url> — true when the URL belongs to the configured
# mirror, so callers can send the share password to the mirror only and never
# leak it to an upstream host.
mirror_is_mirror_url() {
    [ -n "${MAKEMKV_MIRROR_URL:-}" ] || return 1
    case "$1" in "${MAKEMKV_MIRROR_URL%/}/"*) return 0 ;; *) return 1 ;; esac
}
