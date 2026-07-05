---
name: project_session_state_2026-07-05
description: Wind-down state 2026-07-05 — GPU encoder-probe + remote-offload verified live; branch/deploy/PR state; open items. Supersedes the 2026-06-29 session-state.
metadata:
  type: project
---

Development effort spun down 2026-07-05. This is the authoritative "where things
are" snapshot. Supersedes `project_session_state_2026-06-29` (deleted).

## Branch / deploy / PR state (all pushed, in sync)

- **Working + deploy branch:** `deploy/hifi-20260705`, tip **`31d88ef1`**.
  Pushed to BOTH `origin` (`uprightbass360/arm-v3`) and `wolfy`
  (`shitwolfymakes/automatic-ripping-machine`) as a branch. All three (local,
  origin, wolfy) at `31d88ef1`.
- **wolfy PR #41** = `feat/tier25-remote-transcode-offload`, tip **`04077f0b`**.
  Carries the SAME 7 encoder-probe+fix commits as the deploy branch, but under
  cherry-picked SHAs (patch-id identical; verified via `git cherry`). PR #41 is
  the upstream-PR line; the deploy branch is the fork-local deploy line.
- **`deploy/hifi-20260705` = `deploy/hifi-20260704` + 30 commits** (linear, 04 is
  an ancestor of 05). The 30: Tier-33 per-host resource stats (~18, incl.
  migration 0027 hosts table), remote-offload plumbing (HOME/gosu fix, keyscan
  T1/T2/T3), and the 7 GPU encoder-probe commits (this session).

## hifi deployment (live, verified)

hifi is deployed from `deploy/hifi-20260705` @ `31d88ef1` (redeployed 2026-07-05:
rebuilt+recreated arm-backend/arm-ui-neu/arm-transcode:latest under ALL THREE
compose overlays — see [[project_hifi_v3_deploy]] for the three-`-f` gotcha).
**Remote NVENC transcode offload verified END-TO-END live:** backend spawns
`arm-transcode-*` containers on `ssh://sam@192.168.0.92` (transcoder-server),
which read `/raw` + write `/media` on the shared marvin NFS export as
**1001:1000**, HandBrakeCLI NVENC h265 transcoding, heartbeating back to
`https://192.168.0.68:8080/api/transcoder/tasks/.../heartbeat` (200 OK, cross-host
TLS). hifi's ARM_GPUS = the REMOTE nvenc box (offload); its local N97 QSV is not
wired in (correct for offload).

## The GPU encoder-probe feature (this session's main work — COMPLETE)

Replaces the installer's hardcoded `ARM_GPUS[].encoder_kinds=["h264","h265"]` with
values probed from the transcode image's real HandBrake (`--probe-encoders` mode).
Five findings surfaced+fixed, all live-verified on hifi's N97:
- **F-A** (`4568ffe0`): probe was targeting bare `arm-transcode:latest`
  (non-existent public image) → inert in prod. Fixed to
  `${ARM_IMAGE_PREFIX}/arm-transcode:${ARM_IMAGE_TAG}`.
- **F-B/F-C** (`c4f5591a`): compose+cert honor persisted `.env` offload state on
  re-run; offload prompt skipped under `--certs-only`.
- **F-F** (`fb406257`): a probe that RAN and found no HW encoder yields `[]`, not
  the over-claiming default (only a probe FAILURE falls back).
- **F-G** (`31d88ef1`): probe passes `-e RENDER_GID` so HandBrake can open the
  render node (gosu strips docker `--group-add`) — see
  [[project_qsv_render_gid_gosu_probe]]. **N97 genuinely does h264+h265 QSV; no
  driver update needed.** This closes the real root cause of task #7.
- Task 1 (HW AV1 map entries) DROPPED: real image has only software `svt_av1`.
- Full review doc: `../arm-ai/arm-v3/docs/reviews/2026-07-05-install-sh-composed-review.md`.

## Open / not done (for a future pickup)

- **task #7** (ARM_GPUS h265 over-claim → QSV rc=3): root-caused + fixed (F-G) and
  verified, but the task card is still open — close it after confirming a real
  local-QSV transcode on N97 (hifi currently offloads, so its local QSV path
  isn't exercised in production).
- **Settings config tab / enable-disable mechanism** — brainstorm was PAUSED early
  in the session (established: pull in configuration + clean enable/disable). Never
  resumed. Still open.
- **Deferred transcoder items:** dispatcher client reconnect/retry (no recovery
  from a failed remote-docker connection); UI/API surfacing of offload health.
- **F-8** (install.sh PUID/PGID/CDROM_GID re-derive lacks append-guard) — pre-existing,
  out of scope, documented in the review docs.

## Wolfy PR workflow reminders

`unset GITHUB_TOKEN` before EVERY wolfy git/gh (the fine-grained PAT overrides the
classic `gho_` token per-shell). Push branches INTO wolfy + open in-repo PRs
(cross-repo `--head uprightbass360:...` does not resolve). `git add` only named
files, never `-A`/`.` (tree has many untracked scratch .png/.bin files). Commit
trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## Diagnostic gotcha burned twice this session

`docker exec <c> python ...` gets the IMAGE default env (HOME=/root), NOT PID 1's
env — so offload/paramiko probes falsely "fail." Authoritative check reads
`/proc/1/environ`. Same class as [[project_entrypoint_home_gosu_paramiko]].
