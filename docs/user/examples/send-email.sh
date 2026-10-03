#!/usr/bin/env bash
# arm-hook: Send an email through an SMTP relay with curl
# arm-input: TO        label="Recipient"     required
# arm-input: FROM      label="Sender"        default="arm@localhost"
# arm-input: SMTP_URL  label="SMTP URL"      default="smtp://smtp:25"
# arm-input: SMTP_USER label="SMTP user"
# arm-input: SMTP_PASS label="SMTP password" secret
# arm-input: SUBJECT   label="Subject"       default="ARM {event_type}: {job_title}"
# arm-input: PRIORITY  label="Priority"      values=low,normal,high default=normal
set -euo pipefail

title="$1"
body="$2"
case "$PRIORITY" in high) xprio=1 ;; low) xprio=5 ;; *) xprio=3 ;; esac

auth=()
if [[ -n "${SMTP_USER:-}" ]]; then auth=(--user "${SMTP_USER}:${SMTP_PASS:-}"); fi

printf 'From: %s\nTo: %s\nSubject: %s\nX-Priority: %s\n\n%s\n\n%s\n' \
  "$FROM" "$TO" "$SUBJECT" "$xprio" "$title" "$body" \
  | curl -fsS --url "$SMTP_URL" --mail-from "$FROM" --mail-rcpt "$TO" "${auth[@]}" -T -
