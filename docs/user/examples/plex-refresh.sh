#!/usr/bin/env bash
# arm-hook: Refresh a Plex library section when a transcode session finishes
# arm-input: PLEX_URL   label="Plex URL"     default="http://plex:32400"
# arm-input: SECTION    label="Library section id" required
# arm-input: PLEX_TOKEN label="Plex token"   secret required
set -euo pipefail

# Only act on completed sessions; other subscribed events exit quietly.
[[ "$ARM_EVENT_TYPE" == session.completed ]] || exit 0
# The token goes in a header, not the query string: URLs end up in logs.
curl -fsS -X POST -H "X-Plex-Token: ${PLEX_TOKEN}" "${PLEX_URL}/library/sections/${SECTION}/refresh"
