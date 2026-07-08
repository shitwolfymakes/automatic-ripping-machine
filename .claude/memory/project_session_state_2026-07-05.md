---
name: project_session_state_2026-07-05
description: Wind-down state 2026-07-05 — GPU encoder-probe + remote-offload verified live; branch/deploy/PR state; open items. Supersedes the 2026-06-29 session-state.
metadata:
  type: project
---

Development effort spun down 2026-07-05. This is the authoritative "where things
are" snapshot. Supersedes `project_session_state_2026-06-29` (deleted).

## Branch / deploy / PR state (all pushed, in sync)

- **Working + deploy branch:** `deploy/hifi-20260705`, tip **`c247c9bd`** (+
  memory commit on top) — 2026-07-05 late, from deploy-tester feedback:
  installer root-refusal + PUID/PGID preserve-on-rerun (`7d54e923`), log
  clarity (`7a404e45`), full adversarial review pass (`4d330378`:
  derived-gid-0 validation, per-field heal, root-install chown, CRLF-safe
  .env reads, entrypoint adopts existing PGID group e.g. gid 100 `users`,
  CI test-shell job), and ripper abandon-now-ejects (`c247c9bd`: eject ran
  only at the successful-rip tail; `_handle_abandon` now spawns a deduped
  eject when the abandoned job owns the pipeline or the idle drive still
  seats the disc). Pushed to BOTH `origin` and `wolfy`.
- **wolfy PR #41** = `feat/tier25-remote-transcode-offload`, tip **`04077f0b`**
  — RESTORED to pure remote-offload scope 2026-07-06 (the four fix commits
  were briefly stacked on it; user flagged the tangle, force-pushed back).
- **wolfy PR #49** = `fix/main-installer-puid-abandon-eject` — the four fixes
  BACKPORTED onto wolfy `main` (all four bugs verified present on main; fix
  PRs target main per repo convention). Backport dropped tier-26-only hunks
  (url_host, offload prompt), the deploy-only entrypoint-guard CI step, and
  the review-gate tests; 901-test main suite green. **PR #48 CLOSED as
  superseded.** The backport branch is merged into deploy (`d003a543`,
  content-identical ancestry merge) so the stack's eventual landing is a
  no-op here. When #41 reaches main it reconciles against these fixes —
  small, known (one import-position resolve).
- **Open-PR titles renumbered 2026-07-06** so tier number = merge order
  (#42→T27 … #46→T31; #47 stays T32) and ALL open-PR titles de-em-dashed
  (user preference: hyphens, never em dashes, in PR names). Branch names
  keep their original tier numbers — only titles moved.
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

## PR-stack pre-review sweep (2026-07-06, tiers 1-2 done)

8-finder + adversarial-verify pass over the bottom of the wolfy stack before
wolfy reviews. Per-PR outcomes:

- **PR #6 (Tier-1)**: 5 fixes COMMITTED on `feat/neu-ports` (`2b098a08`
  naming-preview session fallback via new shared
  `auto_session.resolve_effective_session_id` + track sort; `8d6074a9` omdb
  r.json() guard; `a125908a` iso year-first title + drop dead `exists` field
  + snapshot regen), merged into deploy (`d64e9e90`). PR comment maps the
  two superseded findings (makemkv regex → #11; omdb env-override → #12)
  and the open rescan-contract question (no-op POST /rescan + dead
  DriveStatus checks — wolfy decides WS-command vs GET demotion).
- **PR #7 (Tier-2)**: annotated only (comment 4899487061) — its files are
  rewritten by mid-stack tiers, so fixes at the bottom would cascade-
  conflict. Superseded-by refs: tmdb lookup dead-end + crc64 imdb_id → #10
  (`37443ae7`); pause invisible to ripper pre-scan → #27 (`54a74e07`);
  multi-disc get_release → music-matching work. Cross-ref comments posted
  on #10 and #27. REFUTED (don't relitigate): identify 4xx-non-retriable
  classifier is correct and required.
- **SURVIVORS past Tier-32 (verified at deploy tip; fix ONCE at stack top
  in a future batch)**: omdb `type=tv` (should be `series`); `events_unsent`
  lacks NOTIFIABLE filter (grows forever); `stats()` full-table scans
  Jobs+Events per poll; preflight `writable` false-green (backend-local
  W_OK, blocking on loop); music 404/502 by substring "not found"
  (metadata.py:265); MusicBrainz free-text Lucene term unescaped (AC/DC →
  400; `_escape_lucene` covers only AND-filters); pause-gate duplicated
  with fail-open vs 500 semantics (jobs.py:745); plain-pause (hold_for_review
  off) still strands seated discs after unpause even at deploy tip.
- **PR #8 (Tier-3, notifications)**: 8-finder pass + 5 verifiers; unlike
  Tier-2, findings survive the whole stack (notifications extended, not
  redesigned upstack) → fixes COMMITTED on `feat/notification-channels`
  (`d5779994..1abd3881`, 4 commits): notifier raises AppriseDeliveryError
  (apprise signals failure by return value — success was unfalsifiable);
  global toggle now gates apprise only via Message.apprise_enabled (bell
  works out of the box; needs_user_input no longer consumed unseen);
  per-event watermark commit (no batch re-sends); catalog-ordered URL
  composition + merge keeps stored url; config.url redacted scheme://****
  on read w/ PATCH echo-guard; migration 0015 imports channels enabled.
  Stack-coherence merges done first (neu-ports→tier2-ports→notification-
  channels, all clean; tier2's test_key rewrite intentionally supersedes
  the #6 omdb guard). Deploy merged (`1ff74f32`; deploy's notifier had
  evolved — asset branding — merge combined cleanly, tests adapted).
  DEFERRED (PR comment 4899705091): tick full-scan/inbox O(n)/no
  retention (needs fake IS NULL support or e2e coverage), last_error may
  embed credentialed URLs, fire-and-record duplication, event-type
  vocabulary in 5 places, config PATCH accepts dead apprise-urls field.
- **PR #9 (Tier-4, quickwins)**: fixes COMMITTED on `feat/tier4-quickwins`
  (`dcf0fd7d..d41de94a`): {disc} token now plumbed from the matched MB
  medium's position (was validate-ok/apply-fail everywhere); version
  endpoint reads ARM_VERSION env > VERSION file (Dockerfile bakes
  /app/VERSION) > pkg metadata, functools.cache'd (was 0.0.0 forever);
  NamingValidateRequest mirrors preview/save (min_length=1, preset
  default True); minors (existence-check guard, fake _Scalars.first(),
  test import hygiene). Deploy merged (`94aac7f6`, 1406 green — deploy's
  system.py resources block + new version chain coexist).
  **OPEN DECISION on #9 (comment 4899913780): DELETE /api/drives/{id}**
  — FK RESTRICT means 500 for any drive with job history; the fake-based
  test asserts the impossible 204; options (block-any-jobs 409 / SET NULL
  migration / tombstone) put to wolfy; also lifecycle gap (live ripper
  heartbeats 404 after delete, row resurrects on restart).
- **2026-07-07 review-response arc**: wolfy CHANGES_REQUESTED on #6 =
  cut the ISO-ingress feature (9 inline comments). Cut authored as
  `fix/tier1-cut-iso-ingress`, PR **#50** (opened per user's
  PR-against-PR preference after force-resetting feat/neu-ports to the
  reviewed tip) — wolfy merged it same day; all 9 threads replied
  "Cut in #50"; #6 re-review requested. Tier-2 companion: system paths
  drop ISO_INGRESS_ROOT. **DEPLOY DIVERGENCE: deploy keeps the ISO scan
  endpoint** (ui-neu import-jobs.ts consumes it) until the ephemeral-
  worker ISO design (docs/arch/10) replaces it — resolve future base
  absorptions by keeping deploy's iso files.
- **Tier-2 SPLIT (2026-07-07, user-requested)**: former #7 (+2,965) is
  now three single-feature PRs — **#51** Tier-2.1 metadata (+1,819),
  **#52** Tier-2.2 system (+659, incl. ISO companion), **#7** Tier-2.3
  pause gate (+482, retargeted to feat/tier2.2-system). feat/tier2-ports
  rebuilt = 2.2 + pause picks, tip byte-identical to pre-split
  (verified empty diff), force-pushed; #8 needed the -s ours history
  link (see [[deploy-branch-discipline]] rule 10). Merge order:
  #51 → #52 → #7 → #8.
- Tiers 5+ not yet swept. Stack-top survivor batch still pending
  (Tier-2 survivors + config.py apprise-urls deprecation).

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
- **F-8** (install.sh PUID/PGID/CDROM_GID re-derive lacks append-guard) — FULLY
  CLOSED by `7d54e923` + `4d330378`: append-guards for all three keys,
  preserve-on-rerun, root refusal, per-field heal, CRLF sanitize; 29-check
  suite (devtools/test-install-env.sh) now runs in CI (test-shell job).
- **Review leftovers (minor, deliberately unfixed)**: `confirm()`'s non-tty
  branch reads a line of the piped script under `curl | bash` (pre-existing,
  only --rotate-ca/nvidia prompts; fix = read from /dev/tty); a shell-exported
  PUID/PGID overrides .env at `docker compose up` time (compose interpolation
  precedence — same footgun class, benign when values match); entrypoint
  useradd can still collide with an image system UID (rare; gid side fixed).
- **Deploy-tester feedback still open** (2026-07-05): metadata misses are silent
  (no TMDB key ⇒ AWAITING_USER_ID with zero hint in UI); CD lookup silently
  disabled when config's musicbrainz_user_agent is NULL/blank (seeder only
  back-fills session_signing_key); consider maintainer contact email in the
  default MB user-agent (wolfy's call).

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
