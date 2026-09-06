# Bash hook scripts

A **Bash script** notification channel (a "hook") runs a script of yours when
a subscribed event fires. It is the v3 successor of v2's `BASH_SCRIPT`
setting with the same calling convention, plus declared inputs, per-event
overrides, and a test panel.

## Where scripts live

Put executable files in `arm/scripts/` under the install prefix (next to
`arm/media` and `arm/raw`). The backend sees the directory read-only at
`/scripts`. In Settings > Notifications, add a channel of type Bash script
and pick the file. Files without the execute bit are listed but cannot be
picked.

    cp docs/ops/examples/send-email.sh arm/scripts/
    chmod +x arm/scripts/send-email.sh

## Calling convention

    bash /scripts/<script> "<title>" "<body>"

`$1` is the rendered title and `$2` the rendered body after the channel's
per-event overrides. That is exactly what v2 passed.

Every render-context variable is also exported as an `ARM_*` variable:

| Variable | Meaning |
|---|---|
| `ARM_EVENT_TYPE` | `rip.completed`, `rip.partial`, `rip.failed`, `rip.needs_user_input`, `session.completed`, `session.partial`, `session.failed` |
| `ARM_JOB_ID`, `ARM_JOB_TITLE`, `ARM_JOB_YEAR`, `ARM_JOB_DISC_TYPE`, `ARM_DRIVE_ID`, `ARM_OCCURRED_AT` | job and event envelope |
| `ARM_STATUS`, `ARM_TRACKS_DONE`, `ARM_TRACKS_FAILED`, `ARM_TRACKS_TOTAL` | `rip.*` events |
| `ARM_STATUS`, `ARM_SESSION_ID`, `ARM_SESSION_APPLICATION_ID` | `session.*` events |
| `ARM_VOLUME_LABEL`, `ARM_DISC_TYPE` | `rip.needs_user_input` |
| `ARM_TITLE`, `ARM_BODY` | same values as `$1` and `$2` |
| `ARM_MEDIA_ROOT`, `ARM_RAW_ROOT` | `/media` and `/raw` inside the container |

Unknown values are empty strings. `GET /api/notifications/event-types` is
the authoritative per-event list. The Test panel in the UI shows the exact
values for a chosen event.

## Declaring inputs

Add comment lines to the top of the script (first 60 lines):

    # arm-hook: Send an email through an SMTP relay
    # arm-input: TO        label="Recipient"     required
    # arm-input: SUBJECT   label="Subject"       default="ARM {event_type}: {job_title}"
    # arm-input: PRIORITY  label="Priority"      values=low,normal,high default=normal
    # arm-input: SMTP_PASS label="SMTP password" secret

The UI renders one field per `arm-input` line, and the value reaches the
script as an environment variable with that exact name (`$TO`, `$SUBJECT`).

- `KEY` must be upper-case letters, digits, and underscores, and must not
  start with `ARM_` (reserved).
- `label="..."` is the field label (defaults to the key).
- `default="..."` is used when the field is left blank. Values may use the
  same `{variables}` as title and body.
- `values=a,b,c` renders a select and rejects anything else.
- `required` fails the run when the value is empty.
- `secret` renders a password field, stores the value masked, and cannot be
  overridden per event.

A script with no `arm-input` lines still works and gets `$1`, `$2`, and the
`ARM_*` variables.

## Per-event overrides

Each subscribed event can override the title, the body, and every non-secret
input. Blank fields inherit the hook's values. Typical use: one email hook
subscribed to `rip.completed` and `rip.failed`, with `rip.failed` sending to
an on-call address with `PRIORITY=high`.

## Where the script runs

Inside the `arm-backend` container, as the `PUID` user:

- tools: bash, coreutils, `curl`. No `rsync`, `rclone`, `ffmpeg`, or
  `mkvpropedit` unless you add them (see below)
- paths: `/scripts` (read-only), `/media`, `/raw`, `/logs`
- network: the compose network and outbound internet
- not available: host binaries, `systemctl`, `eject`, host paths that are
  not mounted

To use extra tools or paths, extend the backend image or add a bind mount in
`docker-compose.override.yml`:

    services:
      arm-backend:
        volumes:
          - /mnt/nas/movies:/mnt/nas/movies

The backend's own environment (database URL, service token) is never passed
to the script. Only `PATH`, `HOME`, `LANG`, `LC_ALL`, the `ARM_*` variables,
and the declared inputs are.

## Failures and timeouts

The script must exit 0 within the channel's timeout (default 30 seconds,
maximum 600). A non-zero exit, a timeout, a missing file, a missing execute
bit, a missing required input, or a template error is recorded on the
channel and in the dispatch log with the reason and the first 200 characters
of stderr. There is no retry. The Test panel shows the full stdout and stderr
(up to 4 KB each) of a test run.

## Examples

- [send-email.sh](examples/send-email.sh): email through an SMTP relay with
  curl; recipient, subject, and priority per event.
- [plex-refresh.sh](examples/plex-refresh.sh): refresh a Plex library section
  on `session.completed`.

## Migrating from v2 `BASH_SCRIPT`

Copy the file into `arm/scripts/`, make it executable, add a Bash script
channel that points at it, and subscribe it to every event. `$1` and `$2`
are unchanged. v2's `[ARM_NAME]` prefix and `NOTIFY_JOBID` suffix are not
applied; set them in the per-event title template instead.
