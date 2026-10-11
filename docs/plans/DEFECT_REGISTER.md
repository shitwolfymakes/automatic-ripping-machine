# ARM v3 PR stack defect register

Migrated 2026-10-11 from the `chore/defect-register` branch of uprightbass360/arm-v3, where these defects were first tracked. Issue links now point at this repository's tracker (each issue carries its original arm-v3 number). The stacked PRs and integration branches named below have all since been merged to `main`; any remaining fix belongs on `main`.

Date: 2026-10-03. Tip checked against: `origin/integration/all-prs-3` @ `71129cd9bf4c646547d0e6f7879b52aa1d3b8c58` (uprightbass360/arm-v3). Scope: the 26 stacked PRs #61..#102 plus off-stack #82 and #103 on shitwolfymakes/automatic-ripping-machine, reviewed bottom-up with each PR diffed against its own base (three-dot). Every row went through a tip check; rows fixed only by a tip commit that belongs to no open PR are recorded as **open** (see D-row on tip-only commits).

Totals: 118 rows — severity S1 3, S2 6, S3 40, S4 69; status open 93, fixed-later 9, hoisted 9, untested-needs-hardware 7. Status `untested-needs-hardware` marks a defect that is established from the code but whose live symptom needs a drive, GPU or Docker drill to confirm.

Conventions: ids `D-xxx` mirror the Automation Gap Register's `G-xx`. `Fixed in` names the lowest stack PR whose branch contains the fixing commit (computed with `git merge-base --is-ancestor` in stack order), or `tip-only <sha>` when the fix exists only on the integration branch. `Origin PR` is the PR whose diff introduces the defect; `stack` marks a stack-level row.

Baseline checks on the tip: `uv run pytest` 3619 passed / 6 skipped; ui-neu `npm run check` 0 errors, `vitest` 1934 passed. Every PR head was also checked with pytest, ruff, mypy, the OpenAPI snapshot regen + TypeScript codegen, and (where ui-neu changed) svelte-check + vitest; no PR head failed any of those, and no PR head shows OpenAPI drift.

Hygiene checks requested up front (no defect rows):
- CI runs on #89 and #90 showing `CANCELLED`: both are concurrency-cancelled duplicates. Run 36354866038 (#89) and 36354866037 (#90) were cancelled within seconds of runs 36354868063 and 36354866232 starting on the *same head SHAs* (`85f93b04`, `c01b1011`), and those sibling runs passed. Nothing to re-run; no red run exists for either head.
- `fix/parked-session-survives-rip` and `fix/rip-start-honours-session-preset` (both = commit `35ed68d8`, "keep a pre-rip session choice parked until rip-complete"): the fix is in the tip. It landed in #75 (`52ce650f`, which introduces `drain_parked_applications_after_rip`, the `no_tracks` skipped reason and the rip-complete drain). The two branches are redundant and can be deleted.
- `wolfy/v3-improvments`: see the stack-level decision row.


## Per-PR counts

| PR | Branch | Open | Fixed later | Untested (hardware) | Total |
|---|---|---|---|---|---|
| #61 | `feat/drive-lifecycle` | 3 | 2 | 0 | 5 |
| #62 | `feat/drive-lifecycle-2` | 3 | 2 | 0 | 5 |
| #64 | `feat/drive-lifecycle-3` | 1 | 4 | 2 | 7 |
| #65 | `feat/drive-lifecycle-4` | 0 | 2 | 0 | 2 |
| #66 | `feat/drive-lifecycle-6` | 4 | 2 | 0 | 6 |
| #75 | `feat/phase2-job-metadata` | 5 | 0 | 1 | 6 |
| #76 | `feat/phase3-session-routing` | 5 | 0 | 0 | 5 |
| #73 | `feat/notifications-bash-channel` | 7 | 0 | 0 | 7 |
| #74 | `chore/ui-neu-css-cleanup` | 5 | 0 | 0 | 5 |
| #81 | `feat/ws-origins-live-status` | 2 | 1 | 0 | 3 |
| #83 | `feat/setup-dev-stack-lifecycle` | 1 | 3 | 0 | 4 |
| #84 | `feat/gpu-inventory-alignment` | 7 | 0 | 1 | 8 |
| #85 | `feat/no-transcode-mode` | 3 | 0 | 1 | 4 |
| #87 | `feat/encoder-first-presets` | 3 | 1 | 1 | 5 |
| #89 | `chore/remove-vue-ui` | 2 | 0 | 0 | 2 |
| #90 | `chore/ui-neu-eslint-prettier` | 0 | 0 | 0 | 0 |
| #88 | `feat/docs-site` | 3 | 0 | 0 | 3 |
| #94 | `chore/ui-neu-ux-polish` | 2 | 0 | 0 | 2 |
| #95 | `fix/job-status-actions` | 5 | 0 | 0 | 5 |
| #96 | `fix/optional-template-tokens` | 2 | 0 | 0 | 2 |
| #97 | `feat/identity-core` | 2 | 1 | 0 | 3 |
| #98 | `feat/identity-disc-hints` | 1 | 0 | 1 | 2 |
| #99 | `feat/identity-episode-matcher` | 3 | 0 | 0 | 3 |
| #100 | `feat/identity-settings` | 4 | 0 | 0 | 4 |
| #101 | `feat/iso-source-rip` | 9 | 0 | 0 | 9 |
| #102 | `feat/first-run-setup` | 6 | 0 | 0 | 6 |
| #82 | `feat/matrix256-fingerprint` | 2 | 0 | 0 | 2 |
| #103 | `fix/pin-makemkv-1.18.4` | 1 | 0 | 0 | 1 |
| stack-level | — | 2 | 0 | 0 | 2 |

## Summary

| ID | Issue | Sev | Status | Area | Origin PR | Fixed in | Title |
|---|---|---|---|---|---|---|---|
| D-001 | [#123](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/123) | S1 | open | devtools | #61 | — | install.sh (the canonical installer) still generates rippers without `ARM_DRIVE_ID`, which #61 made a required setting — every installer-deployed ripper crash-loops at Settings() and nothing can rip. |
| D-002 | [#124](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/124) | S1 | hoisted | backend | #64 | #64 | `/api/ripper/register` returns a body without `updated_at`; the ripper's `Drive.model_validate` raises and the container crash-loops — no enrolled drive can ever register. |
| D-003 | [#125](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/125) | S1 | open | ripper | #82 | — | Skeleton materializer trusts disc-supplied path components: a `..`/`/`-bearing filename escapes the temp root and truncates arbitrary files writable by the ripper. |
| D-004 | [#126](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/126) | S3 | open | ripper | #61 | — | Port-identity drive renumbered away from `ARM_DRIVE_DEV` flaps absent/present every two polls, re-running boot probe, device-path PATCH and `InsertDetector.reset()` each cycle. |
| D-005 | [#127](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/127) | S4 | open | ripper | #61 | — | "node outside ARM_OPTICAL_*_MAX" warning fires on every 2 s poll, contradicting the PR's log-once-per-transition design. |
| D-006 | [#128](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/128) | S4 | fixed-later | devtools | #61 | #64 | PR body claims the compose block grants the device cgroup rules; nothing in the diff wires `ARM_DRIVE_ID`/`device_cgroup_rules`/`/host-disk`, so the hotplug path is dead for every stack this PR can generate. |
| D-007 | [#129](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/129) | S4 | fixed-later | common | #61 | #62 | `DriveMediaStatus.DETACHED` comment documents backend behaviour ("derives DriveStatus.OFFLINE from this") that does not exist in this PR. |
| D-008 | [#130](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/130) | S3 | fixed-later | backend | #62 | #64 | Every ripper-served drive appears twice: the hostname-registered ENROLLED row and a scanner-created DETECTED duplicate. |
| D-009 | [#131](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/131) | S4 | fixed-later | backend | #62 | #66 | `GET /api/drives/diagnostic` reports every scanner-detected (never-enrolled) drive as unhealthy "no media-status heartbeat recorded". |
| D-010 | [#132](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/132) | S4 | open | backend | #62 | — | `POST /api/drives/rescan` "online/stale" badge counts every detected and ignored drive as stale. |
| D-011 | [#133](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/133) | S4 | open | backend | #62 | — | Stale "0029" references after the migration was renumbered to 0030. |
| D-012 | [#134](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/134) | S4 | open | backend | #62 | — | The e2e harness boots the real `DriveScanner` against the host's `/sys`, making the real-DB tier environment-dependent. |
| D-013 | [#135](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/135) | S2 | hoisted | backend | #64 | #64 | Enroll creates the container, then 500s on `DriveView.model_validate` (expired `updated_at`); row stays `enrolled` while the UI reports failure. |
| D-014 | [#136](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/136) | S2 | hoisted | devtools | #64 | #64 | Nothing builds `ARM_RIPPER_IMAGE` (`arm-ripper:latest`): on a compose-built install every enroll is 502 "ImageNotFound". |
| D-015 | [#137](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/137) | S2 | hoisted | devtools | #64 | #64 | setup-dev.sh / iso-smoke.sh still launch rippers without `ARM_DRIVE_ID` (and with the removed `ARM_DRIVE_SERIAL`); every generated `arm-ripper-srN` crash-loops at Settings() and conflicts with the manager's containers. |
| D-016 | [#138](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/138) | S3 | untested-needs-hardware | backend | #64 | — | Unenroll only refuses while `RIPPING`; a job mid-scan/identify is orphaned when the manager SIGTERMs and removes its ripper. |
| D-017 | [#139](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/139) | S3 | untested-needs-hardware | backend | #64 | — | Container name/hostname is the udev short serial; two drives sharing a serial (common on USB bridges) collide and the second enroll fails with a confusing 502. |
| D-018 | [#140](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/140) | S4 | open | docs | #64 | — | Protocol doc still documents the hostname-keyed register body. |
| D-019 | [#141](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/141) | S4 | fixed-later | docs | #65 | #88 | `arm_wiki/` (synced to the GitHub wiki by `publish-wiki.yml`) still describes the per-drive `arm-ripper-srN` compose model this PR removes from setup-dev/compose template. |
| D-020 | [#142](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/142) | S4 | fixed-later | devtools | #65 | #101 | `iso-smoke.sh` leaves the borrowed drive's managed ripper stopped when the ISO ripper never came up, while its comment claims the trap fires "on every exit path … never stays paused just because a later step blew up". |
| D-021 | [#143](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/143) | S3 | open | ui-neu | #66 | — | Detected list offers "Enroll" on a drive that is not present, which the backend always refuses (409), and the row gives no presence indication. |
| D-022 | [#144](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/144) | S4 | open | ui-neu | #66 | — | "Look for issues" flags healthy rows as issues: an ignored PORT-identity drive (notes `['ignored', _PORT_NOTE]`, `healthy: true`) and any present-but-unenrolled drive (`healthy: true`, one informational note) turn the status bar to "Issues Found", contradicting the backend's `healthy` verdict and the PR-body claim. |
| D-023 | [#145](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/145) | S4 | fixed-later | ui-neu | #66 | #102 | Ignored-section toggle uses one-off text glyphs `▾`/`▸` where the shared `Glyph` component (`chevron-down` / `chevron-right`) already exists. |
| D-024 | [#146](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/146) | S4 | fixed-later | ui-neu | #66 | #74 | Diagnostic notes render an inline SVG warning path that duplicates `Glyph name="warning"`. |
| D-025 | [#147](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/147) | S4 | open | ui-neu | #66 | — | `deleteDrive()` API wrapper left dead after DriveCard's Remove button was replaced by Unenroll. |
| D-026 | [#148](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/148) | S4 | open | ui-neu | #66 | — | Unenroll uses the native `confirm()` while the same PR introduces the shared `ConfirmDialog` for the sibling destructive action (Remove Missing Drives). |
| D-027 | [#149](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/149) | S3 | open | backend | #75 | — | A partial placeholder rip (`RIPPED_PARTIAL` + `flags.unidentified`) never gets its routed session applied: rip-complete gates `after_rip` off, and resolve only runs `after_rip` for `RIPPED_AWAITING_IDENTIFY`. |
| D-028 | [#150](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/150) | S3 | untested-needs-hardware | backend | #75 | — | identify writes the ripper-supplied `pending_session_id` straight into an FK column without an existence check — a session deleted between manual trigger and identify turns identify into a 500 that the ripper retries forever. |
| D-029 | [#151](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/151) | S4 | open | docs | #75 | — | Stale migration numbers and stale "inert" / "reads metadata_json['disc']" comments left in code the PR itself changed. |
| D-030 | [#152](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/152) | S4 | open | ui-neu | #75 | — | `readJobMetadata` prefers the stale `provider_raw.arm_server.video_type` over the new authoritative `job.media_type` column, and legacy rows lose their Type/multi_title/source_type entirely. |
| D-031 | [#153](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/153) | S4 | open | migrations | #75 | — | 0032's downgrade is a no-op although its upgrade moves `artist`/`album`/`tracks` out of the top level — after `alembic downgrade 0031` the base-branch code can no longer name or list music tracks. |
| D-032 | [#154](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/154) | S4 | open | backend | #75 | — | New uncovered backend statements: resolve's `tvdb` / `musicbrainz_release` external-id overlay branches. |
| D-033 | [#155](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/155) | S3 | open | backend | #76 | — | Unidentified music CD (media_type=None, disc_type=cd) is still routed to the drive's video default; the seeded music routes never fire for it. |
| D-034 | [#156](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/156) | S3 | open | ui-neu | #76 | — | SessionRoutesCard cannot display or create a route to a compatible-but-different-media-type session the backend accepts (e.g. movie → iso-dump session, movie → tv session). |
| D-035 | [#157](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/157) | S4 | open | backend | #76 | tip-only `0048ca44` (no PR) | Three new backend statements are uncovered (100%-statement policy): factory-raise branch and old-client close guard in the SSH-rebuild path; blank-output_path skip in find_collisions. |
| D-036 | [#158](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/158) | S4 | open | docs | #76 | — | Stale migration references in model docstrings/comments after the 0034/0035 renumber and the conditional seed-marker UPDATE. |
| D-037 | [#159](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/159) | S4 | open | backend | #76 | — | Concurrent `PUT /api/session-routes` for the same `(media_type, disc_type)` turns the NULLS-NOT-DISTINCT unique violation into a 500 (acknowledged follow-up). |
| D-038 | [#160](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/160) | S2 | open | backend | #73 | — | Stored bash secret can be unmasked through PATCH with a script name that is not on disk (claimed-impossible `secret_keys` forgery). |
| D-039 | [#161](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/161) | S3 | open | backend | #73 | — | `POST /scripts/preview` with `run: true` returns script stdout/stderr/error unredacted, including stored secret values merged in via `channel_id`. |
| D-040 | [#162](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/162) | S3 | open | backend | #73 | — | Timeout kills only the `bash` process; the script's children keep running (no process group / `killpg`). |
| D-041 | [#163](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/163) | S3 | open | backend | #73 | — | A hook that exits 0 but leaves a background child holding stdout/stderr is recorded as a timeout failure. |
| D-042 | [#164](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/164) | S3 | open | backend | #73 | — | `OSError` from `create_subprocess_exec` (e.g. E2BIG from an input template with a width spec) is uncaught: 500 on preview, and the listener skips bookkeeping and the remaining bash channels for that event. |
| D-043 | [#165](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/165) | S3 | open | devtools | #73 | — | `install.sh` (the canonical installer) neither creates `scripts/` nor mounts `/scripts` into `arm-backend`, so installer-deployed stacks cannot use bash hooks without a hand-written override. |
| D-044 | [#166](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/166) | S3 | open | backend | #73 | — | An unreadable file in `/scripts` makes `GET /api/notifications/scripts` 500 for every script (PermissionError not handled). |
| D-045 | [#167](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/167) | S4 | open | devtools | #74 | — | Style lint misses `style={…}` bindings and value-less `style:prop` shorthand; the PR itself relies on the gap. |
| D-046 | [#168](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/168) | S4 | open | devtools | #74 | — | Lint is a ban-list, not the allow-list the body and the `ALLOWED` table describe; ~437 sizing/position utilities pass unchecked. |
| D-047 | [#169](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/169) | S4 | open | docs | #74 | — | `THEME_TEMPLATE.md` still requires the alias tokens this PR removed and nothing consumes. |
| D-048 | [#170](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/170) | S4 | open | docs | #74 | — | `.claude/memory/MEMORY.md` index drops the em-dash entry and omits three new memory files. |
| D-049 | [#171](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/171) | S4 | open | ui-neu | #74 | — | Markup rewrite leaves ARIA state/label attributes on role-less elements (files-page root tabs, channel-type label). |
| D-050 | [#172](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/172) | S3 | open | ui-neu | #81 | — | `wsClient.start()` during the reconnect back-off clears the "Live updates unavailable" banner with no backend change (and opens a duplicate socket). |
| D-051 | [#173](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/173) | S3 | hoisted | devtools | #81 | #81 | Emptying the `ARM_ALLOWED_ORIGINS` default breaks WS for the Vue `arm-ui` on 8081 (the image install.sh deploys and the dev compose's 8081 service), whose nginx never forwards `X-Forwarded-Host`. |
| D-052 | [#174](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/174) | S4 | open | backend | #81 | — | Stale test docstring: "empty allowlist means service-token only" contradicts the same PR's same-origin default. |
| D-053 | [#175](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/175) | S2 | hoisted | devtools | #83 | #83 | `setup-dev.sh up` force-removes rippers/transcoders with work in flight — a routine redeploy kills a running rip. |
| D-054 | [#176](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/176) | S3 | hoisted | devtools | #83 | #83 | `setup-dev.sh up` removes every ripper container but nothing respawns them when compose leaves the backend running. |
| D-055 | [#177](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/177) | S3 | hoisted | devtools | #83 | #83 | `arm-data:/data` named volume is created root-owned, so the EACCES this commit claims to fix persists. |
| D-056 | [#178](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/178) | S4 | open | docs | #83 | — | Contributor docs still tell people to use bare `docker compose up -d`, which this PR's CLAUDE.md says never to do. |
| D-057 | [#179](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/179) | S3 | untested-needs-hardware | backend | #84 | — | Removing the boot-time truncate makes orphaned BUSY GPU rows permanent: `cancel_running`'s docker-stop path (and deleting a spawned-but-unclaimed task) deletes the task row without releasing its GPU. |
| D-058 | [#180](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/180) | S3 | open | ui-neu | #84 | — | Transcoder page per-device GPU rows are fetched once on mount and never refreshed, so their busy/available state contradicts the polled summary count. |
| D-059 | [#181](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/181) | S3 | open | ui-neu | #84 | — | GpusCard never shows the "in use by a running transcode" message on a 409: it string-matches `'409'` in a message the API client has already replaced with the server `detail`. |
| D-060 | [#182](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/182) | S3 | open | backend | #84 | — | Fresh install: the config seeder creates the singleton and returns before the `max_parallel_transcodes` backfill, so the column stays NULL until the second boot; meanwhile `/api/config` reports `1` while the dispatcher uses the env value. |
| D-061 | [#183](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/183) | S4 | open | backend | #84 | — | `/api/transcodes/stats.gpus_available` counts disabled GPUs as available. |
| D-062 | [#184](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/184) | S4 | open | ui-neu | #84 | — | "Manage GPUs in Settings" links to `/settings`, which opens the Metadata tab; the GPUs card lives under `#transcoding`. |
| D-063 | [#185](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/185) | S4 | open | ui-neu | #84 | — | GPU inventory row markup (status-dot + vendor badge + mono device path + state label) is duplicated inline in GpusCard and the Transcoder page instead of a shared component. |
| D-064 | [#186](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/186) | S4 | open | devtools | #84 | — | install.sh's `.env` template and docker-compose.yml.example still tell operators to "Re-run install.sh after a GPU/driver change" — the backend now ignores `ARM_GPUS` once the table is populated. |
| D-065 | [#187](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/187) | S3 | open | backend | #85 | — | Transcode re-enable PATCH 500s when a per-job re-drain fails: `job.id` read after `rollback()` (MissingGreenlet). |
| D-066 | [#188](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/188) | S3 | untested-needs-hardware | backend | #85 | — | Cancelling an in-process passthrough task does not stop the copy: the file still lands in `/media` and the raw source is unlinked after the user deleted the task. |
| D-067 | [#189](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/189) | S3 | open | ui-neu | #85 | — | Ripper-only (`ARM_TRANSCODE_CAPABLE=false`) hides the Transcoder page and nav while the backend silently holds previously queued encode tasks forever. |
| D-068 | [#190](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/190) | S4 | open | backend | #85 | — | `GET /api/config` reports `transcode_enabled: true` on a ripper-only deployment where encode is effectively disabled. |
| D-069 | [#191](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/191) | S3 | hoisted | ui-neu | #87 | #87 | GpusCard subscribes to `gpu.probed` without starting the WebSocket and shows no in-progress state after Re-probe, so on a directly loaded Settings page the row stays "Never probed"/stale forever. |
| D-070 | [#192](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/192) | S3 | untested-needs-hardware | backend | #87 | — | An infrastructure failure during a re-probe (container could not start, docker wait error, 120 s timeout) is written as `encoder_kinds=[]`, wiping a previously verified device so queued vendor-pinned tasks terminally fail and `any_*` work silently drops to CPU. |
| D-071 | [#193](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/193) | S3 | open | transcode | #87 | — | A `vaapi_*` (or AMD-resolved `any_*`) preset with `container=webm` passes preset validation but every task fails at run time because the ffmpeg VAAPI engine only muxes MKV/MP4. |
| D-072 | [#194](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/194) | S3 | open | devtools | #87 | — | install.sh-generated compose does not forward `ARM_TRANSCODE_IMAGE_QSV` / `_VAAPI` / `_NVENC` to the backend, so the PR's operator instruction for air-gapped/private-registry installs has no effect. |
| D-073 | [#195](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/195) | S4 | open | devtools | #87 | — | install.sh still runs the now-deprecated `--probe-encoders` container at install time; its `{}` output is discarded by the backend, so the step only costs an image pull plus up to 60 s. |
| D-074 | [#196](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/196) | S4 | open | docs | #89 | — | The docs sweep changed Settings `/config` -> `/settings` in one place but left the same wrong route in `docs/README-OMDBAPI.md`. |
| D-075 | [#197](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/197) | S4 | open | ci | #89 | — | The published `arm-ui` image no longer ships `/LICENSE`: ui-neu's Dockerfile lacks the `COPY LICENSE /LICENSE` every other image (and the removed Vue arm-ui image) has. |
| D-076 | [#198](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/198) | S4 | open | ci | #88 | — | New `site/` npm lockfile has no Dependabot coverage, unlike every other dependency manifest in the repo. |
| D-077 | [#199](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/199) | S4 | open | docs | #88 | — | `project_docs_site.md` memory (and the PR body) record the wrong stacking base: "on `feat/encoder-first-presets` (#87)" with a stack list that omits #89/#90. |
| D-078 | [#200](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/200) | S4 | open | docs | #88 | — | Former `docs/ops/` pages now published to the GitHub wiki carry relative `../../services/...` repo links that cannot resolve on the wiki. |
| D-079 | [#201](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/201) | S4 | open | ui-neu | #94 | — | `dismissAllNotifications` doc comment states the opposite of the backend behaviour this same PR introduced. |
| D-080 | [#202](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/202) | S4 | open | docs | #94 | — | Status-Roadmap describes maintenance "buttons" for orphaned log files and clearing the raw rip area that do not exist in the UI; this PR deleted their last stubs. |
| D-081 | [#203](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/203) | S3 | open | backend | #95 | — | A parked application that stays parked after rip-complete makes a `ripped` job read "Transcoding 0/0" forever (and stay live/polling). |
| D-082 | [#204](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/204) | S3 | open | ui-neu | #95 | — | Parked-session line promises "applies when the rip finishes" on failed and abandoned jobs; nothing ever cancels a parked application when the rip fails or the job is abandoned. |
| D-083 | [#205](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/205) | S4 | open | common | #95 | — | `REDRAIN_JOB_STATUSES` includes pre-rip statuses whose parked applications the redrain can never promote; every transcode re-enable logs a WARN per such row. |
| D-084 | [#206](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/206) | S4 | open | ui-neu | #95 | — | Detail-page metadata says `State: In progress` for an idle `ripped` job with no session applied. |
| D-085 | [#207](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/207) | S4 | open | ui-neu | #95 | — | `JobStatsPanel.svelte` and `JobStatsPanel.test.ts` left behind after their last consumer was removed. |
| D-086 | [#208](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/208) | S4 | open | backend | #96 | — | New `except TemplateValidationError: raise` makes the `malformed template` re-wrap branch uncovered; backend 100%-statement policy regresses. |
| D-087 | [#209](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/209) | S4 | open | docs | #96 | — | Architecture docs that `path_template.py` says it mirrors were not updated for the `{token?}` syntax or the new built-in defaults. |
| D-088 | [#210](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/210) | S3 | open | backend | #97 | — | `test_identify_repost_on_held_disc_keeps_operator_exclusion` passes without ever reaching the resolver it claims to test. |
| D-089 | [#211](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/211) | S4 | open | docs | #97 | — | `04-data-model.md` tracks section still documents `role_source` and free-text `role`; new columns undocumented. |
| D-090 | [#212](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/212) | S4 | fixed-later | backend | #97 | #99 | PR body promises `put_source` keeps last-good claims on a same-inputs error; the code is a plain overwrite. |
| D-091 | [#213](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/213) | S3 | untested-needs-hardware | ripper | #98 | tip-only `89a5cf53`+`2837d671` (no PR) | BDMT disc-title probe silently yields nothing for UDF-only Blu-ray sources (no ISO 9660 PVD) — pycdlib refuses to open them and the probe soft-fails to None. |
| D-092 | [#214](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/214) | S4 | open | backend | #98 | — | `parse_label` leaves a year token inside the "cleaned" hint title (e.g. `THE_OFFICE_2005_S1_D2` → `"the office 2005"`), so the first-searched candidate carries the year as query text and the TV search has no year filter to compensate. |
| D-093 | [#215](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/215) | S3 | open | backend | #99 | — | `/identity/match apply=true` → `invalidate()` → the rerun-once starts while the router is still computing and later overwrites the operator's stored match with a default-input recompute. |
| D-094 | [#216](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/216) | S4 | open | backend | #99 | — | Operator-supplied external ids are interpolated unescaped into provider URL paths. |
| D-095 | [#217](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/217) | S4 | open | docs | #99 | — | `02-job-lifecycle.md` still says Play-All titles are "not auto-detected" while this PR's matcher detects them (sum-of-episodes and sum-of-other-titles) and roles them `extra`. |
| D-096 | [#218](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/218) | S3 | open | ui-neu | #100 | — | Emptying an int setting now sends `null`; for `thediscdb_refresh_days` and `manual_wait_seconds` the backend has no None check, so Save ends in an unhandled NOT NULL IntegrityError (HTTP 500). |
| D-097 | [#219](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/219) | S3 | open | backend | #100 | — | Changing `episode_sources` / `disc_hint_sources` does not re-resolve existing jobs, so a disabled source's already-applied fields stay on the job until an unrelated trigger runs the resolver. |
| D-098 | [#220](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/220) | S4 | open | ui-neu | #100 | — | `RankedListField`'s "Needs <source> key" chip hardcodes the `Metadata` tab in its deep link instead of deriving it from the required key's field metadata. |
| D-099 | [#221](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/221) | S4 | open | ui-neu | #100 | — | Two recurring visual patterns are re-implemented inline instead of shared: the TV-episodes summary strip copies SessionCard's recipe strip, and the "Advanced" label copies `.session-card-recipe-label` (`feedback_standard_ui_patterns.md`: a pattern in two places is extracted). |
| D-100 | [#222](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/222) | S2 | open | ripper | #101 | — | The extract fallback (`iso_extract`) needs 7-Zip, but this PR's ripper image never installs it; every image MakeMKV cannot open fails as "no titles". |
| D-101 | [#223](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/223) | S3 | open | backend | #101 | — | An ISO (or disc folder) whose name contains `:` cannot be ripped: the bind spec docker-py builds is `host:container:mode`, so the extra colon makes the spawn fail with 500 and the drive is retired. |
| D-102 | [#224](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/224) | S4 | open | backend | #101 | — | New uncovered backend statement: `_virtual_source_drive`'s `drive_id is None` guard is unreachable from `rip_start` and has no test or pragma. |
| D-103 | [#225](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/225) | S4 | open | ripper | #101 | — | `ARM_SOURCE_KIND` is set by the backend, declared by the ripper and documented as "selects the MakeMKV source scheme", but nothing in the ripper reads it. |
| D-104 | [#226](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/226) | S4 | open | docs | #101 | — | Status-Roadmap lists "Extracted disc folders as a rip source" as "Next up" while this PR ships Rip from folder. |
| D-105 | [#227](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/227) | S4 | open | docs | #101 | — | Configuring-ARM recommends a relative `ARM_HOST_ISO_LIBRARY_PATH` ("e.g. `./iso-library`") that the backend deliberately treats as "not configured". |
| D-106 | [#228](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/228) | S4 | open | ui-neu | #101 | — | IsoPicker re-implements byte formatting inline instead of using the shared `formatBytes` helper. |
| D-107 | [#229](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/229) | S4 | open | ui-neu | #101 | — | The picker's "not configured" card tells every operator to redeploy with `bash devtools/setup-dev.sh up`, a dev-only script. |
| D-108 | [#230](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/230) | S4 | open | ripper | #101 | — | `_scan_extracted` removes a multi-GB extraction with a synchronous `shutil.rmtree` on the event loop. |
| D-109 | [#231](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/231) | S3 | open | ui-neu | #102 | — | MakeMKV step records done/attention from a config snapshot taken before the key was entered or verified. |
| D-110 | [#232](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/232) | S4 | open | docs | #102 | — | Docs and Finish summary written in this PR describe a guest-access choice on step 1 that the same PR removed. |
| D-111 | [#233](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/233) | S4 | open | backend | #102 | — | Public `/api/setup/status` exposes the ARM version unauthenticated although the UI never reads it and `/api/system/version` is JWT-gated. |
| D-112 | [#234](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/234) | S4 | open | backend | #102 | — | After "Run setup again", resuming from `/setup` lands on the Finish step, not the first step. |
| D-113 | [#235](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/235) | S4 | open | ui-neu | #102 | — | nginx comment for the `/docs-data/` 404 rule now sits above the new `/arm-ca.crt` block. |
| D-114 | [#236](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/236) | S4 | open | ripper | #102 | — | `backend_client.py` reads `ARM_DRIVE_ID` straight from `os.environ` instead of the ripper's `settings.ARM_DRIVE_ID` every other module uses. |
| D-115 | [#237](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/237) | S4 | open | common | #82 | — | `DiscFingerprintInput` docstring still calls matrix256 "ARM-native" (and omits `thediscdb`) although the PR body claims the schema comment was updated. |
| D-116 | [#238](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/238) | S4 | open | docs | #103 | — | `docs/ops/makemkv.md` "What the install scripts do" still says the script "Scrapes the current MakeMKV version" after this PR makes a pinned version the default. |
| D-117 | [#239](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/239) | S3 | open | ci | stack | — | The integration tip carries 30 commits that are in no open PR; merging the 27 PRs does not reproduce the tested tip. |
| D-118 | [#240](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/240) | S4 | open | ci | stack | — | `wolfy/v3-improvments` (upstream only) carries 89 commits of v2-era UI/model work that exist nowhere in the stack; keep-or-kill decision needed. |
| D-120 | [#242](https://github.com/shitwolfymakes/automatic-ripping-machine/issues/242) | S4 | open | ui-neu | main | — | With guest access disabled, an unauthenticated visit fires the whole dashboard load before the 401 redirect and keeps polling on `/login` (20 x 401 per visit). |

## Detail

### D-001  S1  open  devtools  origin #61

**Title.** install.sh (the canonical installer) still generates rippers without `ARM_DRIVE_ID`, which #61 made a required setting — every installer-deployed ripper crash-loops at Settings() and nothing can rip.

**Where.** `install.sh:1262-1290` (`emit_ripper_block`: environment lists only `ARM_DRIVE_DEV`, `ARM_BACKEND_URL`, `ARM_SERVICE_TOKEN`, `ARM_LOG_LEVEL`, `PUID`, `PGID`, `CDROM_GID`; `devices:` binds, no `/dev/disk:/host-disk:ro`, no `ARM_RIPPER_IMAGE` for the backend) at `71129cd9`, unchanged since `main`; the requirement is `services/ripper/arm_ripper/config.py:22` `ARM_DRIVE_ID: str` introduced in `325c4f9d` ("feat(ripper): drive identity settings + device-path/get-drive client calls", PR #61).

**What.** `arm_ripper.config.settings = Settings()` runs at import; with `ARM_DRIVE_ID` unset pydantic raises a `ValidationError`, the container exits and `restart: unless-stopped` loops it forever (`services/ripper/tests/test_config_drive_identity.py::test_drive_id_is_required` pins the raise). The installer is the source of truth for deployment values (memory `feedback_ui_port_8081.md`), and the stack's drive-lifecycle model moved ripper creation into the backend (`ripper_manager`), but no PR in the stack rewrites `install.sh`: #65 only documents it (`docs/developers/architecture/06-deployment.md:271` "install.sh predates the drive-lifecycle model and still emits per-drive services; it is scheduled for a rewrite before release"). An operator who runs `install.sh` from the merged stack gets a backend that cannot enrol (no `arm-ripper` image reference, no backend-managed spawn path) plus N crash-looping legacy rippers. Only `devtools/setup-dev.sh` works.

**Repro / evidence.**

```
$ git show origin/integration/all-prs-3:install.sh | sed -n '1262,1290p' | grep -c ARM_DRIVE_ID   # 0
$ git show origin/integration/all-prs-3:services/ripper/arm_ripper/config.py | grep -n 'ARM_DRIVE_ID: str'   # 22
$ bash install.sh on any host, then: docker compose ps   # armv3-ripper-srN restarting; logs: ValidationError ARM_DRIVE_ID Field required
```

**Tip check.** Still present at `71129cd9`: `install.sh:1262-1290` (`emit_ripper_block` unchanged; `ARM_HOST_ISO_LIBRARY_PATH` was added to the backend env by #101 but the ripper block was not touched). No PR and no straggler rewrites the installer. Independently flagged by the #61, #64 and #65 reviewers; recorded once here.

**Suggested fix location.** feat/drive-lifecycle (#61) — the PR that made `ARM_DRIVE_ID` required must either keep a `ARM_DRIVE_DEV`-only fallback or update `install.sh` (drop `emit_ripper_block`, add the build-only/pulled `arm-ripper` image reference and `ARM_RIPPER_IMAGE` so the backend-managed spawn works). Alternatively a dedicated installer-rewrite PR must merge before or with the stack.

**Verification.** Code read of the installer heredoc and the ripper Settings at the tip (zero-infra). End-to-end: `bash install.sh` on a Linux host with one optical drive, then `docker compose logs armv3-ripper-sr0` — untested-needs-hardware.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/123

### D-002  S1  hoisted  backend  origin #64

**Title.** `/api/ripper/register` returns a body without `updated_at`; the ripper's `Drive.model_validate` raises and the container crash-loops — no enrolled drive can ever register.

**Where.** `services/backend/arm_backend/routers/ripper.py:328-336` at `5f4b3d6a` (head `1be121d8`): `session.add(drive); await session.commit(); … return drive`.

**What.** `drives.updated_at` is `onupdate=func.now()` (server-generated, `packages/arm_common/arm_common/models/_columns.py:98-104`). After the UPDATE flush the attribute is expired even with `expire_on_commit=False`; FastAPI serialises the ORM row with the key missing. The ripper does `Drive.model_validate(r.json())` (`services/ripper/arm_ripper/backend_client.py:71`), where `updated_at` is required (see the comment in `services/ripper/tests/test_backend_client_drive.py::test_get_drive_parses_a_drive`), so `register_with_retry` raises `ValidationError` (not `httpx.HTTPError`/`RegisterRefused`) out of `amain()` → process exit → `restart: unless-stopped` loop. The previous code re-selected the row after the upsert, so this is a regression introduced here.

**Repro / evidence.** Ad-hoc e2e test (real-DB SQLite harness, `app_client` fixture): seed `Drive(id="drv_e2e", lifecycle=ENROLLED)`, `POST /api/ripper/register` with `Bearer tok-service` →
```
REGISTER 200 {"id":"drv_e2e",…,"created_at":"2026-10-02T23:14:23","sysfs_port":null,"status":"online"}   # no "updated_at" key
Drive.model_validate(body) -> pydantic ValidationError (updated_at missing)
```
FakeSession never expires attributes, so the tier-1 `test_register_*` tests cannot see it.

**Tip check.** Fixed by #65 (`feat/drive-lifecycle-4`) in `2a0600eb` ("refresh drive rows after commit before serialising them": adds `await session.refresh(drive)` before `return drive`, tip `routers/ripper.py:525`). `git branch -r --contains 2a0600eb` → origin/feat/drive-lifecycle-4 (not a straggler). Recommend: **move down** — #64 merged alone ships a ripper that can never register.

**Suggested fix location.** feat/drive-lifecycle-3 — cherry-pick the ripper.py hunk of `2a0600eb` (and add a real-DB e2e register test; none exists).
**Hoisted.** 2026-10-03: `0f387e727` on `feat/drive-lifecycle-3`. The copy in the later PR becomes empty on restack.

**Verification.** Reproduced on the e2e harness at head as above; fix commit read.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/124

### D-003  S1  open  ripper  origin #82

**Title.** Skeleton materializer trusts disc-supplied path components: a `..`/`/`-bearing filename escapes the temp root and truncates arbitrary files writable by the ripper.

**Where.** `services/ripper/arm_ripper/scan/matrix256_fp.py:65-68` at `132c5d23` (`target = root / relative` → `target.touch()` → `os.truncate(target, size)`).

**What.** `fingerprint_records` materialises a sparse skeleton of the disc tree by doing `target = root / relative; target.touch(); os.truncate(target, size)` for every (path, size) record pycdlib enumerated, with no containment check. pycdlib passes UDF/Rock Ridge names through verbatim, so a crafted disc or ISO whose file name is `..`-bearing or contains `/` escapes the temp root and truncates any file the `arm` user can write (`/raw` rips in progress, `/media`, config). The reviewer's PoC reproduced this (victim file 1000 -> 0 bytes, digest returned normally). Reclassified S1 by the coordinator: this is data loss driven by untrusted input, and #101 adds a library of operator-supplied ISO files as a rip source, which widens the input surface; the tip's 7-Zip fallback (`udf_image.py`, straggler `89a5cf53`) feeds the same function.

**Repro / evidence.** Run with the PR's venv (`cd services/ripper && ../../.venv/bin/python poc.py`):
```python
import os, tempfile, pathlib
from arm_ripper.scan.matrix256_fp import fingerprint_records
victim_dir = tempfile.mkdtemp(prefix="arm-victim-"); victim = pathlib.Path(victim_dir) / "title_t00.mkv"
victim.write_bytes(b"x" * 1000)
fingerprint_records([(f"../{os.path.basename(victim_dir)}/title_t00.mkv", 0), ("BDMV/index.bdmv", 5)])
print(victim.stat().st_size)   # -> 0  (was 1000); digest is returned normally, no error
```
Observed output: `victim size after: 0 (was 1000)`. Severity note: data loss + crafted-input security per the brief would read S1; held at S2 because it needs hostile media (a crafted ISO in the ISO library or a burned disc) — the operator-supplied ISO library is exactly such an input surface.

**Tip check.** Still present at `71129cd9`: `services/ripper/arm_ripper/scan/matrix256_fp.py:65-68` is byte-identical (the tip's `89a5cf53` changed only `probe_matrix256`). The tip makes it *wider*: the 7-Zip fallback `udf_image.list_files` feeds `path.replace("\\", "/").lstrip("/")` records (`scan/udf_image.py:66`) into the same `fingerprint_records`. Not fixed on main (file does not exist there) nor on the tip.

**Suggested fix location.** feat/matrix256-fingerprint (#82) — the materializer is introduced here; a containment check in `fingerprint_records` fixes both the pycdlib and the later 7z record sources.

**Verification.** Reproduced locally with the PoC above against the PR head's venv (no hardware needed).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/125

### D-004  S3  open  ripper  origin #61

**Title.** Port-identity drive renumbered away from `ARM_DRIVE_DEV` flaps absent/present every two polls, re-running boot probe, device-path PATCH and `InsertDetector.reset()` each cycle.

**Where.** `services/ripper/arm_ripper/main.py:197-205` (`_current_hint`) and `:244-246` (`poll_loop` hint selection) at `fc3dd30e` (refresh the port-identity hint on real absence, and throttle it); head `8141a6c9`.

**What.** With `ARM_DRIVE_BY_ID` unset, `_current_hint` returns the backend's `Drive.device_path` only on a tick whose *previous* state was ABSENT; the very next tick (`absent=False`) returns the static `settings.ARM_DRIVE_DEV` again. If the drive now lives at a different node (e.g. backend says `/dev/sr2`, config says `/dev/sr0`, and `/sys/class/block/sr0` is gone), tick k resolves sr2 → "reattached" → `detector.reset()` → `_report_node` → `_on_reattached`/`boot_probe`; tick k+1 resolves sr0 → None → "drive absent"; tick k+2 refreshes again → "reattached" … forever (period = 2 × POLL_INTERVAL = 4 s). Each cycle logs a WARNING + INFO, PATCHes the backend, runs `boot_probe`, and re-arms the detector so a seated DISC_OK disc starts a new `handle_disc_inserted` pipeline every time the previous one finishes. Expected: once the backend-supplied hint resolves, keep using it (e.g. remember the last hint that resolved, or have `_current_hint` fall back to the last-resolved node rather than `ARM_DRIVE_DEV`).

**Repro / evidence.** `uv run python scratchpad/pr61_flap_repro.py` (fake resolve: `/dev/sr2` iff hint == `/dev/sr2`, else None; backend `get_drive` → `/dev/sr2`; status DISC_OK; 12 ticks):
```
ticks=12 absent_warnings=6 present_infos=6 boot_probes=6 rips_started=6 device_path_patches=6 get_drive_calls=6
  drive absent (by_id=None) — polling until it returns
  drive present at /dev/sr2 via hint (reattached)
  boot probe after reattach on /dev/sr2
  drive absent (by_id=None) — polling until it returns
  drive present at /dev/sr2 via hint (reattached)   ... (repeats every 2 ticks)
```
The existing test `test_port_identity_refreshes_hint_from_backend_while_absent` only asserts the hint was *passed* once and ends the script on the tick it resolves, so it cannot see the next-tick regression (and its `real = ripper_main.resolve_drive_device` captures the already-patched fake, not the real resolver).

**Tip check.** Still present at `71129cd9`: `services/ripper/arm_ripper/main.py:234-243` (`if settings.ARM_DRIVE_BY_ID or not absent: return settings.ARM_DRIVE_DEV or ""`) and `:282`. Same repro on a tip worktree (with `ARM_DRIVE_ID=drv_1`, now required) prints the identical `absent_warnings=6 present_infos=6 boot_probes=6 rips_started=6`. On the tip the backend scanner does update `device_path` on enrolled port-identity rows (`drive_scanner.py:163-164`) and `ripper_manager.py` recreates containers only for a stale image, so the path is reachable there.

**Suggested fix location.** feat/drive-lifecycle (#61) — the loop and `_current_hint` are introduced here; fix is self-contained in main.py (track the last hint that resolved).

**Verification.** Reproduced at head and tip with the scripted poll loop above (zero infra). Hardware confirmation: `devtools/drive-hotplug-drill.md` with a drive that has no `/dev/disk/by-id` link, replugged so it renumbers — untested-needs-hardware for that part.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/126

### D-005  S4  open  ripper  origin #61

**Title.** "node outside ARM_OPTICAL_*_MAX" warning fires on every 2 s poll, contradicting the PR's log-once-per-transition design.

**Where.** `services/ripper/arm_ripper/drive_resolve.py:54-62` (`_optical_node`, `warn_if_missing=True` from `:84`) at `9ce93849`; called from `poll_loop` every tick (`main.py:246`).

**What.** When udev's by-id link points at e.g. `sr9` but the entrypoint only pre-created `sr0..sr7`, `resolve_drive_device` logs `logger.warning("drive node %s is not present under %s …")` unconditionally. `poll_loop` re-resolves every `POLL_INTERVAL_SECONDS` (2 s), so the warning repeats ~43,000 times/day in the per-drive log file, alongside the single "drive absent" line the PR advertises. Expected: throttle like the ABSENT/MISCONFIGURED transitions (once per transition, or once per N ticks).

**Repro / evidence.**

```
grep -n "warn_if_missing" services/ripper/arm_ripper/drive_resolve.py   # 51, 54, 84 — no state, no throttle
grep -n "resolve_drive_device(settings.ARM_DRIVE_BY_ID, hint" services/ripper/arm_ripper/main.py  # 246, inside while True
```

**Tip check.** Still present at `71129cd9`: `services/ripper/arm_ripper/drive_resolve.py:58` (`logger.warning(` with no throttle), called from `main.py:284` each tick.

**Suggested fix location.** feat/drive-lifecycle (#61) — the warning is introduced here.

**Verification.** Code reading; no hardware needed to confirm the call cadence (poll loop test harness shows `resolve_drive_device` is invoked once per tick).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/127

### D-006  S4  fixed-later  devtools  origin #61

**Title.** PR body claims the compose block grants the device cgroup rules; nothing in the diff wires `ARM_DRIVE_ID`/`device_cgroup_rules`/`/host-disk`, so the hotplug path is dead for every stack this PR can generate.

**Where.** `devtools/setup-dev.sh:292` (`devices:` bind, unchanged) and `install.sh:1268` (same) vs `services/_common/docker-entrypoint.sh:272` (`if [[ -n "${ARM_DRIVE_ID:-}" ]]`) at `81e73988` / head `8141a6c9`.

**What.** Merged alone, #61 ships the entrypoint pre-creation, by-id resolution and DETACHED heartbeat, but no generated compose sets `ARM_DRIVE_ID`, grants `b 11:* rmw`/`c 21:* rmw`, or mounts `/dev/disk`; rippers still start with `devices:` (so an absent drive still fails container creation — the exact failure in "Why") and by-id resolution is never configured. The PR body presents the cgroup grant as delivered; the drill doc tells the operator to hand-edit an override instead.

**Repro / evidence.**

```
git diff origin/main...origin/feat/drive-lifecycle --stat -- devtools/setup-dev.sh install.sh docker-compose*.yml   # (empty)
grep -n "device_cgroup_rules\|ARM_DRIVE_ID\|host-disk" devtools/setup-dev.sh install.sh                              # (none)
```

**Tip check.** Fixed by #64 (feat/drive-lifecycle-3) in `4d235fca` (RipperManager spawns per-drive ripper containers from the backend with `device_cgroup_rules`, `ARM_DRIVE_ID`, `ARM_DRIVE_BY_ID`, `/host-disk` mount; `git branch -r --contains 4d235fca` → lowest `origin/feat/drive-lifecycle-3`). On the tip `devtools/setup-dev.sh` no longer emits ripper blocks at all. Recommend: **leave** — the delivery depends on later backend code; but the #61 body should be reworded ("the compose block grants…" → "Plan 3 grants…") so the PR is not misread as self-sufficient. Note: `install.sh:1268` on the tip still emits `devices:` ripper blocks — see cross-PR notes.

**Suggested fix location.** feat/drive-lifecycle (#61) — PR description only.

**Verification.** Diff inspection; `bash devtools/setup-dev.sh` output structure unchanged by this PR.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/128

### D-007  S4  fixed-later  common  origin #61

**Title.** `DriveMediaStatus.DETACHED` comment documents backend behaviour ("derives DriveStatus.OFFLINE from this") that does not exist in this PR.

**Where.** `packages/arm_common/arm_common/enums.py:33-36` at `e692b9f3`.

**What.** The comment states the backend derives `DriveStatus.OFFLINE` from a DETACHED heartbeat. In this PR the backend's heartbeat handler (`services/backend/arm_backend/routers/ripper.py:168`) just stores the value; only `jobs.py:_MEDIA_STATUS_DETAIL` references DETACHED. Docs ahead of code within the same PR.

**Repro / evidence.** `git grep -n DETACHED origin/feat/drive-lifecycle -- services/backend/arm_backend` → only `routers/jobs.py:87`.

**Tip check.** Fixed by #62 (feat/drive-lifecycle-2) in `066d4ccf` ("ripper drive endpoints; DETACHED heartbeat derives OFFLINE" — `routers/ripper.py:340-342` on the tip; `git branch -r --contains 066d4ccf` → lowest `origin/feat/drive-lifecycle-2`). Recommend: **leave** — comment describes the stack's design and #62 lands immediately above; alternatively reword to "(Plan 2)".

**Suggested fix location.** feat/drive-lifecycle (#61) — one comment line.

**Verification.** grep at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/129

### D-008  S3  fixed-later  backend  origin #62

**Title.** Every ripper-served drive appears twice: the hostname-registered ENROLLED row and a scanner-created DETECTED duplicate.

**Where.** `services/backend/arm_backend/drive_scanner.py:196-217` at `704bfdd0` (reconcile matches rows only by `by_id_name` / `sysfs_port`), against `services/backend/arm_backend/routers/ripper.py:317-333` at `95ae6568` (the Plan-1 `/register` upsert writes `hostname`, `device_path`, `serial`, `status` only — never `by_id_name`/`sysfs_port`).

**What.** At this head the ripper from #61 still registers by hostname, producing an ENROLLED row with `by_id_name=NULL, sysfs_port=NULL`. The scanner cannot match that row, so on its first tick it inserts a second row for the same physical drive (`scan-<id>`, DETECTED, same `/dev/srN`, same serial). The Drives UI lists the drive twice; "Enroll" on the duplicate yields two ENROLLED rows for one device (no container effect at Plan 2). Should match on serial / by-id, or the register path should carry identity.

**Repro / evidence.**

```
# SQLite, real reconcile_drives(): seed what /register writes, then scan the same drive
ScanSummary(detected=1, ignored=0, enrolled=1, absent=0, pruned=0)
('arm-ripper-sr0', '/dev/sr0', '123', 'enrolled', None)
('scan-drv_01M3ZEAC...', '/dev/sr0', '123', 'detected', 'usb-ASUS_BW-16D1HT_123-0:0')
```

**Tip check.** Fixed by #64 (`feat/drive-lifecycle-3`) in `5f4b3d6a` "feat(backend): register rippers by drive_id with an identity check; delete the hostname upsert" — `/register` now looks the row up by `ARM_DRIVE_ID`, refuses non-ENROLLED rows and checks `by_id_name`; `git branch -r --contains 5f4b3d6a` lists `origin/feat/drive-lifecycle-3` and everything above, so it is in an open PR (not a straggler); recommend: leave — the fix is the Plan 3 contract (backend-spawned ripper with `ARM_DRIVE_ID`) and cannot be hoisted without #64's ripper manager; but #62 must not be released alone (the PR body's own "retarget to main" note should say it ships with #64).

**Suggested fix location.** feat/drive-lifecycle-3 — already there.

**Verification.** Code reading + the SQLite reproduction above (zero-infra). Full behaviour with a real ripper: untested-needs-hardware — bring up #62 alone with one ripper and open the Drives page (or `bash devtools/iso-smoke.sh`, then `GET /api/drives`).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/130

### D-009  S4  fixed-later  backend  origin #62

**Title.** `GET /api/drives/diagnostic` reports every scanner-detected (never-enrolled) drive as unhealthy "no media-status heartbeat recorded".

**Where.** `services/backend/arm_backend/routers/drives.py:66-80` at `95ae6568` (pre-existing health rule, untouched) + `services/backend/arm_backend/drive_scanner.py:211-217` at `704bfdd0` (new DETECTED rows with `status=online` via server default and no heartbeat).

**What.** Detected/ignored rows have no ripper, so `media_status_at` is always `None` and the diagnostic marks them `healthy=false`. A freshly plugged-in drive the operator has not decided about shows as a problem; an ignored drive shows as a problem forever. The rule should be lifecycle-aware.

**Repro / evidence.** `test_diagnostic_reports_drives` + any DETECTED row: `drives.py:72 if d.media_status_at is None: healthy=False; notes.append("no media-status heartbeat recorded")`.

**Tip check.** Fixed by #66 (`feat/drive-lifecycle-6`) in `8027b154` "fix(drives): … diagnostics lists every drive; Detected is a panel" — the diagnostic is now branched on `d.lifecycle` (DETECTED → "not enrolled: enroll it…", `healthy = d.present`; IGNORED → healthy). `git branch -r --contains 8027b154` lists `origin/feat/drive-lifecycle-6` upward — open PR, not a straggler; recommend: leave — cosmetic, and the fix is part of a larger diagnostics rework that depends on #64/#65 container checks.

**Suggested fix location.** feat/drive-lifecycle-6 — already there.

**Verification.** Code reading; tests pass at head because no test asserts a detected row's health.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/131

### D-010  S4  open  backend  origin #62

**Title.** `POST /api/drives/rescan` "online/stale" badge counts every detected and ignored drive as stale.

**Where.** `services/backend/arm_backend/routers/drives.py:108-119` at `9914afad`.

**What.** The handler now runs the scanner (which creates DETECTED rows) and then re-counts *all* rows with the heartbeat-freshness rule. Rows with no ripper can never be fresh, so each detected/ignored drive adds one to `stale`. The body claims the badge is "unchanged"; it now lies as soon as a non-enrolled drive exists. Count only ENROLLED rows (or drop the legacy counts).

**Repro / evidence.** `drives.py:112-117 for d in drives: fresh = d.media_status_at is not None …; else: stale += 1` with `drives = select(Drive)` (no lifecycle filter). `test_rescan_runs_the_scanner_and_reports_counts` only asserts `"stale" in body`, so it does not catch this.

**Tip check.** Still present at `71129cd9`: `services/backend/arm_backend/routers/drives.py:236-245` — the select is now filtered to `DriveKind.OPTICAL` but still not by lifecycle; `stale += 1` for every non-fresh row.

**Suggested fix location.** feat/drive-lifecycle-2 — the regression is introduced here.

**Verification.** Code reading at head and tip; zero-infra.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/132

### D-011  S4  open  backend  origin #62

**Title.** Stale "0029" references after the migration was renumbered to 0030.

**Where.** `services/backend/tests/test_migration_0030.py:21,34,42` (`test_0029_upgrade_adds_every_column`, `test_0029_downgrade_drops_every_column`, `test_0029_matches_the_models`) and `services/backend/arm_backend/drive_scanner.py:266` ("in-memory rows predating 0029") at `ab932a0b`.

**What.** `ab932a0b` renamed the file and revision to `0030_drive_lifecycle` but left the test names and the `_tunables` docstring pointing at 0029, which is `0029_thediscdb` on this chain. Anyone grepping failures by revision lands on the wrong migration.

**Repro / evidence.** `grep -n 0029 services/backend/tests/test_migration_0030.py services/backend/arm_backend/drive_scanner.py`.

**Tip check.** Still present at `71129cd9`: `test_migration_0030.py:21,34,42` (`def test_0029_*`) and `drive_scanner.py:273` ("predating 0029").

**Suggested fix location.** feat/drive-lifecycle-2 — same commit that renumbered.

**Verification.** Grep at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/133

### D-012  S4  open  backend  origin #62

**Title.** The e2e harness boots the real `DriveScanner` against the host's `/sys`, making the real-DB tier environment-dependent.

**Where.** `services/backend/arm_backend/main.py:246-250` at `9914afad` (scanner started unconditionally with `settings.ARM_SYSFS_ROOT="/sys"`), with no override in `services/backend/tests/e2e/conftest.py` (the fixture pins `_build_docker_client`, `load_configured_gpus`, `_run_migrations` and the log dir precisely to avoid this class of problem, lines 137-160).

**What.** Under `app_client`, the scanner's first tick runs immediately and reads the developer's real `/sys/class/block/sr*` (and `/host-disk`, absent → port identity). On a dev box with an optical drive — the normal case for ARM developers — it inserts DETECTED rows into the test SQLite DB, and the suite's result depends on host hardware. CI has no `sr*` (this host: 0), so it passes there. The fixture should set `ARM_SYSFS_ROOT`/`ARM_HOST_DISK_ROOT` to `tmp_path` dirs (or monkeypatch `DriveScanner`).

**Repro / evidence.** `grep -n "SYSFS\|HOST_DISK\|drive_scanner" services/backend/tests/e2e/*.py` → no matches at head; `main.py:246-249` constructs the scanner from settings; `drive_scanner.py:296-303` scans on the first loop pass.

**Tip check.** Still present at `71129cd9`: `services/backend/arm_backend/main.py:354-355` (same constructor) and no `ARM_SYSFS_ROOT`/`drive_scanner` override in `tests/e2e/` at the tip.

**Suggested fix location.** feat/drive-lifecycle-2 — where the scanner joins the lifespan.

**Verification.** Code reading; cannot reproduce on this host (no `sr*` devices). A human with a drive: `uv run pytest -q -k e2e` then inspect `app_client`'s SQLite for `scan-drv_*` rows.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/134

### D-013  S2  hoisted  backend  origin #64

**Title.** Enroll creates the container, then 500s on `DriveView.model_validate` (expired `updated_at`); row stays `enrolled` while the UI reports failure.

**Where.** `services/backend/arm_backend/routers/drives.py:280` at `b2516755` (head `1be121d8`): `return await _view_for(db, drive)` after `db.commit()` + `manager.ensure_running`.

**What.** Same expiry as C1: `_to_view` → `DriveView.model_validate(drive)` fails with `MissingGreenlet` on `updated_at` → 500. Because the exception is not `RipperManagerError`, the revert branch does not run: the container exists and the row is `enrolled`, but the client sees an error. The commit-then-`_view_for` shape already exists at BASE (#62) for enroll/ignore/unignore (so the bare 500 is #62's), but #64 adds the "container already created, state now lies" half.

**Repro / evidence.** Ad-hoc e2e test: seed `Drive(lifecycle=DETECTED, present=True)`, stub `app.state.ripper_manager`, `POST /api/drives/{id}/enroll` with admin JWT →
```
pydantic_core.ValidationError: 1 validation error for DriveView
updated_at  Error extracting attribute: MissingGreenlet: greenlet_spawn has not been called … (services/backend/arm_backend/routers/drives.py:43)
```

**Tip check.** Fixed by #65 in `2a0600eb` (`await db.refresh(drive)` before `_view_for`, tip `routers/drives.py:422,440,509`). Not a straggler. Recommend: **move down** (the ignore/unignore hunks belong to #62; the enroll/unenroll hunks to this PR).

**Suggested fix location.** feat/drive-lifecycle-3 for enroll/unenroll; feat/drive-lifecycle-2 for ignore/unignore.
**Hoisted.** 2026-10-03: `0f387e727` on `feat/drive-lifecycle-3` (ignore/unignore half: `5d3be876c` on feat/drive-lifecycle-2). The copy in the later PR becomes empty on restack.

**Verification.** Reproduced on the e2e harness at head; fix commit read.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/135

### D-014  S2  hoisted  devtools  origin #64

**Title.** Nothing builds `ARM_RIPPER_IMAGE` (`arm-ripper:latest`): on a compose-built install every enroll is 502 "ImageNotFound".

**Where.** `docker-compose.yml.example:62-96,145-151` and `services/backend/arm_backend/config.py:141-143` at `749b9496`/head `1be121d8`.

**What.** `RipperManager.ensure_running` runs `containers.run(image="arm-ripper:latest")`; the compose template has no `arm-ripper` build-only service (the comment claiming `deploy.replicas: 0` is false at this head), and setup-dev.sh builds the ripper only inside its per-drive `arm-ripper-srN` services (tagged `armv3-arm-ripper-srN`, not `arm-ripper:latest`). Enroll flips the row, fails on `ImageNotFound`, reverts with `last_error`; diagnostics shows the `ripper_manager` warning. Manual `docker build -t arm-ripper:latest` is the only workaround.

**Repro / evidence.** `grep -n "arm-ripper" docker-compose.yml.example` at head → only the generated-region sentinels; `grep -n replicas` → only `arm-transcode`.

**Tip check.** Fixed by #65 in `27405d14` ("build-only arm-ripper service; setup-dev stops enumerating drives": adds `arm-ripper:` with `deploy.replicas: 0`, tip `docker-compose.yml.example:245-251`). Not a straggler. Recommend: **move down**.

**Suggested fix location.** feat/drive-lifecycle-3.
**Hoisted.** 2026-10-03: `f81bc061f` on `feat/drive-lifecycle-3`. The copy in the later PR becomes empty on restack.

**Verification.** Code/compose read; untested-needs-hardware for the end-to-end enroll (`docker compose up -d --build` on a fresh clone, then enroll from the UI; `devtools/iso-smoke.sh`).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/136

### D-015  S2  hoisted  devtools  origin #64

**Title.** setup-dev.sh / iso-smoke.sh still launch rippers without `ARM_DRIVE_ID` (and with the removed `ARM_DRIVE_SERIAL`); every generated `arm-ripper-srN` crash-loops at Settings() and conflicts with the manager's containers.

**Where.** `devtools/setup-dev.sh:279-318` (`emit_ripper_block`, `ARM_DRIVE_SERIAL: "${serial}"`, no `ARM_DRIVE_ID`), `devtools/iso-smoke.sh:300-318` (`-e ARM_DRIVE_DEV=/dev/sr0`, no `ARM_DRIVE_ID`) at head `1be121d8`; ripper side `services/ripper/arm_ripper/config.py:21` (`ARM_DRIVE_ID: str`, required) at `a5262a8b`.

**What.** `arm_ripper.config.settings = Settings()` runs at import; with no `ARM_DRIVE_ID` pydantic raises → container exits → `restart: unless-stopped` loop. The dev stack therefore has zero working rippers until the operator enrolls via the UI, and the compose services keep `devices:` binds on the same nodes. The PR body lists this as deferred to Plan 5, but merged alone it breaks `bash devtools/setup-dev.sh && docker compose up -d` and both drills.

**Repro / evidence.** `grep -n "ARM_DRIVE_SERIAL\|ARM_DRIVE_ID" devtools/setup-dev.sh devtools/iso-smoke.sh` at head → only `ARM_DRIVE_SERIAL` lines; `services/ripper/tests/test_config_drive_identity.py::test_drive_id_is_required` shows the ValidationError.

**Tip check.** Fixed by #65: `27405d14` (setup-dev stops emitting ripper services) and `4ad41905` ("iso-smoke borrows an enrolled drive and registers by id"); both `git branch -r --contains` → origin/feat/drive-lifecycle-4. (Tip's later iso-smoke rewrite `5ed5c5c9` is a straggler, but the breakage is already gone at #65.) Recommend: **move down** — or at minimum merge #64 and #65 together.

**Suggested fix location.** feat/drive-lifecycle-3.
**Hoisted.** 2026-10-03: `d78fc0b91` on `feat/drive-lifecycle-3`. The copy in the later PR becomes empty on restack.

**Verification.** Code read; untested-needs-hardware (`bash devtools/setup-dev.sh && docker compose up -d && docker compose ps`).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/137

### D-016  S3  untested-needs-hardware  backend  origin #64

**Title.** Unenroll only refuses while `RIPPING`; a job mid-scan/identify is orphaned when the manager SIGTERMs and removes its ripper.

**Where.** `services/backend/arm_backend/routers/drives.py:331-349` at `b2516755` (head `1be121d8`): the guard selects `Job.status == JobStatus.RIPPING` only, then `manager.remove(drive.id)` stops (30 s) and removes the container.

**What.** Before this PR unenroll only flipped a row; now it kills the process. A disc in `created`/`awaiting_user_id`/`identified`/`awaiting_review` (scan posting, identify running, review countdown — the ripper runs the AWAITING_REVIEW countdown in-process) has a live ripper pipeline that is terminated; the job stays non-terminal with no owning ripper and the row goes `detected`. `delete_drive` has the same RIPPING-only predicate, and #66 mirrors it in the UI gate (`services/ui-neu/frontend/src/lib/utils/drives.ts:17-19` `isRipping`, `DriveCard.svelte:405`), so the Unenroll button is offered while a pre-rip job is live. Workaround: abandon the job via `/jobs/{id}/abandon` first, hence S3. (The #66 reviewer reported the same defect independently; merged here.)

**Repro / evidence.**

```python
.where(col(Job.status) == JobStatus.RIPPING)   # drives.py:337 — TERMINAL_JOB_STATUSES is imported at :16 but not used here
```

**Tip check.** Still present at `71129cd9`: `services/backend/arm_backend/routers/drives.py:481-496` (same RIPPING-only select, then `manager.remove`).

**Suggested fix location.** feat/drive-lifecycle-3 — refuse when any non-terminal job exists for the drive (`~col(Job.status).in_(TERMINAL_JOB_STATUSES)`), or fail the job on unenroll.

**Verification.** Code read; untested-needs-hardware (insert a disc, unenroll during identify, observe job state).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/138

### D-017  S3  untested-needs-hardware  backend  origin #64

**Title.** Container name/hostname is the udev short serial; two drives sharing a serial (common on USB bridges) collide and the second enroll fails with a confusing 502.

**Where.** `services/backend/arm_backend/ripper_manager.py:83-85` at `4d235fca` (head `1be121d8`): `raw = drive.serial or drive.id[-12:]` → `arm-ripper-<slug>`.

**What.** `drive_scanner.parse_short_serial` takes the last `_` token of the by-id name, so `usb-VENDA_MODELA_0123456789-0:0` and `ata-VENDB_MODELB_0123456789` are distinct identities with identical `serial`. Enrolling the second drive: row flips to `enrolled`, `containers.run` → docker 409 name conflict, `_labelled(drive.id)` finds nothing (the winner carries the other drive's label) → `RipperManagerError("APIError: 409 … Conflict")`, row reverted, `last_error` set. No UI workaround (name is not configurable); `drive.hostname` UNIQUE would collide the same way on register.

**Repro / evidence.** `test_ensure_running_reraises_a_409_when_no_container_shows_up` is exactly this path; `container_name` has no uniqueness fallback.

**Tip check.** Still present at `71129cd9`: `services/backend/arm_backend/ripper_manager.py` `container_name` (`raw = drive.serial or drive.id[-12:]`, unchanged apart from the virtual-drive branch).

**Suggested fix location.** feat/drive-lifecycle-3 — include the drive-id suffix in the name (`arm-ripper-<serial>-<id[-6:]>`) or fall back to the id when another row shares the serial.

**Verification.** Code read; untested-needs-hardware (two USB enclosures with identical descriptor serials).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/139

### D-018  S4  open  docs  origin #64

**Title.** Protocol doc still documents the hostname-keyed register body.

**Where.** `docs/arch/03-protocol.md:32` at head `1be121d8`: `Body: {hostname, device_path, ripper_version, hw_caps}. Response: {drive_id, drive_config, service_token_verified}`.

**What.** The wire contract changed in this PR (`drive_id` required, `by_id_name`, 404/409 refusals, full `Drive` response); no doc in the diff was updated.

**Repro / evidence.** `git diff origin/feat/drive-lifecycle-2...origin/feat/drive-lifecycle-3 --stat -- docs` → empty.

**Tip check.** Still present at `71129cd9`: `docs/developers/architecture/03-protocol.md:32` (same line, file moved by `a1b0c7c3`).

**Suggested fix location.** feat/drive-lifecycle-3.

**Verification.** grep.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/140

### D-019  S4  fixed-later  docs  origin #65

**Title.** `arm_wiki/` (synced to the GitHub wiki by `publish-wiki.yml`) still describes the per-drive `arm-ripper-srN` compose model this PR removes from setup-dev/compose template.

**Where.** `arm_wiki/Contribute.md:36-38`, `arm_wiki/Web-UI.md:37-38`, `arm_wiki/Troubleshooting.md:9,30`, `arm_wiki/MakeMKV.md:34` at `1d89e1ee` (unchanged by this PR; made wrong by `27405d14` "build-only arm-ripper service; setup-dev stops enumerating drives").

**What.** Contribute.md says the dev compose `setup-dev.sh` generates has "one `arm-ripper-srN` per drive"; Web-UI.md says `/drives` lists "one per `arm-ripper-srN` container"; Troubleshooting/MakeMKV tell users to `docker compose logs -f arm-ripper-sr0` / `docker compose exec arm-ripper-sr0`. After this PR the dev compose has a single build-only `arm-ripper` service and the real containers are `arm-ripper-<serial>` outside the compose project, so none of those commands work on a dev stack. The PR claims the contributor runbooks were rewritten.

**Repro / evidence.**

```
$ grep -rn "arm-ripper-sr" arm_wiki/
arm_wiki/Contribute.md:38:`arm-ripper-srN` per drive) keeps `build:` blocks (vs the installer's `image:`
arm_wiki/Web-UI.md:38:`arm-ripper-srN` container — with their current state (idle, reading, ripping,
arm_wiki/Troubleshooting.md:9:docker compose logs -f arm-backend    # or arm-ripper-sr0, arm-ui, arm-db
arm_wiki/MakeMKV.md:34:cd ~/arm && docker compose exec arm-ripper-sr0 grep app_Key ...
```

**Tip check.** Gone at `71129cd9`: `git ls-tree origin/integration/all-prs-3 arm_wiki` is empty and `git grep arm-ripper-sr origin/integration/all-prs-3 -- arm_wiki` matches nothing. Fixed by #88 (`feat/docs-site`) in `a1b0c7c3` "docs: split the docs by audience into docs/user and docs/developers" — `git branch -r --contains a1b0c7c3` lists `origin/feat/docs-site` (and `chore/ui-neu-ux-polish`, `feat/first-run-setup` above it), so it is in an open PR, not a straggler. Recommend: **leave** — the fix is a wholesale docs reorganisation that depends on the docs-site work; a targeted edit of the four wiki lines in #65 would be nice-to-have only (Getting-Started.md's `arm-ripper-srN` lines still match the legacy `install.sh` and are not wrong at this point).

**Suggested fix location.** feat/docs-site (#88) already has it; optionally patch the four lines in feat/drive-lifecycle-4.

**Verification.** grep at head and tip, as above.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/141

### D-020  S4  fixed-later  devtools  origin #65

**Title.** `iso-smoke.sh` leaves the borrowed drive's managed ripper stopped when the ISO ripper never came up, while its comment claims the trap fires "on every exit path … never stays paused just because a later step blew up".

**Where.** `devtools/iso-smoke.sh:610-623` (`on_exit`) and `:372-397` (`run_iso_ripper`) at `1d89e1ee` (introduced in `4ad41905`, comment wording from `31a36df0`).

**What.** `pause_managed_ripper` (`:668`) stops the enrolled drive's container, then `trap on_exit EXIT` (`:669`), then `run_iso_ripper` (`:672`). If `docker run --rm -d …` (`:379`) fails (network `armv3_default` missing, bad `.env`, port/name clash, etc.), `set -e` exits; `on_exit` sees `ISO_RIPPER_DOWN == 0` and takes the "ISO ripper is still up" branch: it prints `docker stop armv3-ripper-iso` (a container that does not exist) + `docker start <managed>` and returns without resuming. The managed ripper stays stopped although nothing conflicts with it. Should resume (or at least not print a `docker stop` for a container that never started) when `RIPPER_CTR` is not running. Workaround: run the printed `docker start`.

**Repro / evidence.**

```
# iso-smoke.sh:614-623
    if (( DO_CLEANUP == 0 )) || (( ISO_RIPPER_DOWN == 0 )); then
        ...
        if (( ISO_RIPPER_DOWN == 0 )); then
            echo "      docker stop ${RIPPER_CTR}"
        fi
        echo "      docker start ${ctr:-<managed-ripper-container>}"
        return
    fi
```
Static trace only (needs a running stack to exercise).

**Tip check.** Gone at `71129cd9`: the tip's `iso-smoke.sh` has no `pause_managed_ripper`/`ARM_SMOKE_DRIVE_ID` — it drives `POST /api/iso/rips` (virtual drives) instead. The patch that replaced it is `e4477d60` "feat(devtools): ISO library mount and the API-driven iso-smoke" on `origin/feat/iso-source-rip` (#101) (`git log -S'pause_managed_ripper' origin/feat/drive-lifecycle-4..origin/feat/iso-source-rip`); the tip carries the same patch re-sha'd as straggler `5ed5c5c9`, but the content is in an open PR, so this is fixed-later, not open. Recommend: **leave** — the whole borrow-a-drive mechanism is deleted by #101; a fix in #65 would be thrown away.

**Suggested fix location.** feat/drive-lifecycle-4 only if #65 is expected to merge and ship alone for a while: gate the resume on `docker ps --format '{{.Names}}' | grep -qx "${RIPPER_CTR}"` rather than on `ISO_RIPPER_DOWN`.

**Verification.** Static read of `on_exit`/`run_iso_ripper`; untested-needs-hardware for the live path (`bash devtools/iso-smoke.sh` with the compose network removed).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/142

### D-021  S3  open  ui-neu  origin #66

**Title.** Detected list offers "Enroll" on a drive that is not present, which the backend always refuses (409), and the row gives no presence indication.

**Where.** `services/ui-neu/frontend/src/lib/components/DriveLifecycleLists.svelte:31-44` (row snippet; Enroll button `:42`) at `1693775f` (introduced `dcad6e56`).

**What.** A DETECTED row with `present: false` (unplugged, within the 7-day prune window) renders identically to a connected one except for `last_seen_at`; Enroll is enabled. `enroll_drive` refuses with `cannot enroll a drive that is not present` (`routers/drives.py:360-363`), so the click only yields an error line. The row should either disable Enroll (with a "not connected" hint) or show presence so the action reflects what the backend will accept — the diagnostic endpoint already emits `not connected since …` for the same row.

**Repro / evidence.** Render `DriveLifecycleLists` with `detected=[{lifecycle:'detected', present:false, …}]` → `getByTestId('enroll-<id>')` is enabled; `POST /api/drives/<id>/enroll` → 409. No `present` reference in the component (`grep present DriveLifecycleLists.svelte` → none).

**Tip check.** Still present at `71129cd9`: tip `DriveLifecycleLists.svelte` Enroll button is disabled only by `busy[d.id] || enrollDisabledReason` (ripper-service-down), still no `present` check or indicator (`connectionLabel` is the bus type, not presence); backend tip `routers/drives.py:403` still refuses `not present`.

**Suggested fix location.** feat/drive-lifecycle-6 (#66) — the component is new in this PR; the tip's straggler rewrite (`5bd2fe9f`) would need the same `present` gate.

**Verification.** Code read at head and tip; DriveLifecycleLists.test.ts has no absent-drive case.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/143

### D-022  S4  open  ui-neu  origin #66

**Title.** "Look for issues" flags healthy rows as issues: an ignored PORT-identity drive (notes `['ignored', _PORT_NOTE]`, `healthy: true`) and any present-but-unenrolled drive (`healthy: true`, one informational note) turn the status bar to "Issues Found", contradicting the backend's `healthy` verdict and the PR-body claim.

**Where.** `services/ui-neu/frontend/src/routes/settings/+page.svelte:614` at `1693775f` (`8027b154`); backend note emission `services/backend/arm_backend/routers/drives.py:137-140` at `1693775f` (`d1a3bbf8`).

**What.** The UI derives `unhealthy` as `!d.healthy || (notes.length > 0 && !(notes.length === 1 && notes[0] === 'ignored'))`, i.e. "any note except exactly `ignored`". The backend appends `_PORT_NOTE` to every PORT-identity row regardless of lifecycle while only marking ENROLLED ones unhealthy, and gives present DETECTED rows the `not enrolled: …` note with `healthy: true`. Either the UI should trust `healthy` (and render notes as info) or the backend should not add `_PORT_NOTE` to ignored rows. Coverage confirms the ignored/detected PORT branch is untested (`drives.py` partial branch `139->141`).

**Repro / evidence.** `_drive(DriveLifecycle.IGNORED, identity_kind=PORT, serial=None, by_id_name=None)` → diagnostic item `healthy: true, notes: ['ignored', 'no by-id link, …']`; UI filter at `:614` includes it in `unhealthy` → "Issues Found".

**Tip check.** Still present at `71129cd9`: `+page.svelte:722-723` (same filter), `routers/drives.py:167-169` (`_PORT_NOTE` appended for every PORT row).

**Suggested fix location.** feat/drive-lifecycle-6 (#66) — both halves are introduced here.

**Verification.** Code read; backend behaviour confirmed by the coverage partial-branch report; not run in a browser.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/144

### D-023  S4  fixed-later  ui-neu  origin #66

**Title.** Ignored-section toggle uses one-off text glyphs `▾`/`▸` where the shared `Glyph` component (`chevron-down` / `chevron-right`) already exists.

**Where.** `services/ui-neu/frontend/src/lib/components/DriveLifecycleLists.svelte:62` at `1693775f` (`dcad6e56`); `Glyph.svelte` + `glyph-names.ts` (`chevron-down`, `chevron-right`) exist at the same commit.

**What.** Violates the standard-UI-patterns rule (`.claude/memory/feedback_standard_ui_patterns.md` on the tip, owner directive 2026-09-05; this PR's commits are dated 2026-09-04 but the branch was restacked 2026-09-23).

**Repro / evidence.** `DriveLifecycleLists.svelte:62  Ignored ({ignored.length}) {ignoredOpen ? '▾' : '▸'}`

**Tip check.** Gone at `71129cd9` (tip uses `<Glyph name={ignoredOpen ? 'chevron-down' : 'chevron-right'} …/>`). The fixing commit on the tip is `5bd2fe9f` (`feat(ui): drive enrollment states, connection/media chips, essentials card, 3-state mode`), which is a rebased copy of `33390730` on `feat/first-run-setup` (same subject, same diffstat) — so Fixed by #102. Recommend: **leave** — cosmetic, and the fix is part of #102's drive-list rewrite.

**Suggested fix location.** feat/drive-lifecycle-6 (#66) — swap the two characters for `Glyph`; or land the straggler `5bd2fe9f` in an open PR.

**Verification.** Code read at head and tip; containment via `git branch -r --contains`.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/145

### D-024  S4  fixed-later  ui-neu  origin #66

**Title.** Diagnostic notes render an inline SVG warning path that duplicates `Glyph name="warning"`.

**Where.** `services/ui-neu/frontend/src/routes/settings/+page.svelte:658-660` at `1693775f` (block rewritten in `dcad6e56`/`8027b154`; the path pre-existed in the base and was carried into the new per-drive loop).

**What.** `GLYPH_PATHS.warning` is byte-identical to the inline `d="M12 9v2m0 4h.01…"`; the shared component should be used.

**Repro / evidence.** `+page.svelte:659` vs `glyph-names.ts` `warning:` entry.

**Tip check.** Fixed by #74 (chore/ui-neu-css-cleanup) in `390ea291` (`feat(ui-neu): styling system: tokens, block vocabulary, themed schemes, no inline styling` — the diag block was rebuilt on shared components); recommend: leave — cosmetic and the fix rides on #74's styling system.

**Suggested fix location.** chore/ui-neu-css-cleanup (#74) already has it.

**Verification.** `git log -S'M12 9v2m0 4h' …` + `git branch -r --contains 390ea291`.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/146

### D-025  S4  open  ui-neu  origin #66

**Title.** `deleteDrive()` API wrapper left dead after DriveCard's Remove button was replaced by Unenroll.

**Where.** `services/ui-neu/frontend/src/lib/api/drives.ts:12` at `1693775f`; only remaining caller is `src/lib/__tests__/drives-api.test.ts:61-64` (removed production use: `DriveCard.svelte` in `dcad6e56`).

**What.** The backend `DELETE /api/drives/{id}` remains valid, but no ui-neu surface calls it; the wrapper and its test survive only to cover each other.

**Repro / evidence.** `grep -rn deleteDrive services/ui-neu/frontend/src | grep -v test` → only the definition.

**Tip check.** Still present at `71129cd9`: `api/drives.ts:14` with the same lone test caller.

**Suggested fix location.** feat/drive-lifecycle-6 (#66) — remove with the Remove button, or keep deliberately with a comment.

**Verification.** grep at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/147

### D-026  S4  open  ui-neu  origin #66

**Title.** Unenroll uses the native `confirm()` while the same PR introduces the shared `ConfirmDialog` for the sibling destructive action (Remove Missing Drives).

**Where.** `services/ui-neu/frontend/src/lib/components/DriveCard.svelte:170` at `1693775f` (`dcad6e56`); `DriveMaintenance.svelte:60-68` uses `ConfirmDialog` in the same PR.

**What.** Two destructive drive actions on the same tab confirm through different mechanisms; `ConfirmDialog` is a listed standard (`feedback_standard_ui_patterns.md`). The native dialog also cannot be tested with the testing-library patterns the PR uses elsewhere (DriveCard.test.ts stubs `window.confirm`).

**Repro / evidence.** `DriveCard.svelte:170  if (!confirm(`Unenroll ${name}? …`)) return;`

**Tip check.** Still present at `71129cd9`: `DriveCard.svelte:260` (`!confirm(`).

**Suggested fix location.** feat/drive-lifecycle-6 (#66).

**Verification.** Code read at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/148

### D-027  S3  open  backend  origin #75

**Title.** A partial placeholder rip (`RIPPED_PARTIAL` + `flags.unidentified`) never gets its routed session applied: rip-complete gates `after_rip` off, and resolve only runs `after_rip` for `RIPPED_AWAITING_IDENTIFY`.

**Where.** `services/backend/arm_backend/routers/ripper.py:1137-1145` (rip-complete skips `after_rip` for any unidentified ripped job) and `services/backend/arm_backend/routers/jobs.py:960,991-998` (`was_ripped_placeholder = job.status == JobStatus.RIPPED_AWAITING_IDENTIFY`; the `else` branch only calls `fan_out_waiting_identify_applications`, never `maybe_auto_apply_session`) at `7fe7b5e7` (introduced in 3c46f57d "gate after_rip on the unidentified flag for partial rips too").

**What.** Fix 75-3 correctly stops rip-complete from fanning out an unidentified partial rip under the volume-label title, and the comment promises "a parked application still drains safely once resolve lands". But the other half of `after_rip` — `maybe_auto_apply_session` (the manual-trigger `pending_session_id` choice or the drive default) — is never run for this job: rip-complete skipped it because of the flag, and resolve takes the non-placeholder branch because the status is `RIPPED_PARTIAL`, not `RIPPED_AWAITING_IDENTIFY`. Result: a manual-trigger rip with an explicit session (`POST /api/jobs/manual {session_id}`) that identifies late and loses one track ends resolved with no transcode tasks and no indication why; the same disc with zero failed tracks would be auto-applied. Workaround: operator applies the session by hand, hence S3.

**Repro / evidence.** Fake-session path: identify with `block_on_miss=false` (sets `flags.unidentified`) and `pending_session_id=S`; rip-complete with one failed track -> status `RIPPED_PARTIAL`, `after_rip` skipped (ripper.py:1137); `POST /resolve {title:...}` -> jobs.py:998 branch -> only parked applications are drained; no `SessionApplication` for S is ever created. No test covers resolve of an unidentified RIPPED_PARTIAL job with a pending_session_id (`grep -n "RIPPED_PARTIAL" services/backend/tests/test_jobs_router.py` has none in the resolve tests).

**Tip check.** Still present at `71129cd9`: `routers/ripper.py:1276-1283` (same gate) and `routers/jobs.py:1020,1074-1079` (`if was_ripped_placeholder: ... after_rip` / else fan-out only).

**Suggested fix location.** feat/phase2-job-metadata — the gate and the resolve branch are both introduced here; make the resolve branch key on "rip already finished AND was unidentified" (e.g. `job.status in {RIPPED_AWAITING_IDENTIFY, RIPPED_PARTIAL} and flag_is_set(old_metadata, "unidentified")`, captured before Fix 75-6 clears the flag).

**Verification.** Code trace at head and tip; not executed against hardware (would need `devtools/iso-smoke.sh` with a forced track failure to see end-to-end).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/149

### D-028  S3  untested-needs-hardware  backend  origin #75

**Title.** identify writes the ripper-supplied `pending_session_id` straight into an FK column without an existence check — a session deleted between manual trigger and identify turns identify into a 500 that the ripper retries forever.

**Where.** `services/backend/arm_backend/routers/ripper.py:546-547` (`job.pending_session_id = req.pending_session_id`, committed at the identify `session.commit()`) at `7fe7b5e7`; FK from `migrations/versions/0031_job_identity_columns.py:50-57`.

**What.** Before this PR the id was a free-form metadata key. Now the column carries `FOREIGN KEY (pending_session_id) REFERENCES sessions(id)`. `manual_trigger` validates the session exists (jobs.py:800-806), but identify trusts whatever the ripper sends. `DELETE /api/sessions/{id}` only refuses built-ins and drive defaults (sessions.py:187-201), so a session chosen for one manual rip can be deleted while the disc is scanning; identify's commit then raises `IntegrityError` (unhandled -> 500). The ripper's identify loop treats 5xx as retriable (`job_controller.py:480-497`: only 4xx is "not retriable; parking pipeline"), so it re-POSTs identify with the same dangling id with exponential backoff until restarted, holding the drive. Window is seconds to a minute; workaround is to re-create the session or restart the ripper, hence S3 (race window). The routed-session resolver already tolerates a missing row (`_load_routed_session` logs and falls back), so the fix is a one-line existence check (or `SELECT ... FOR` the id and drop it with a warning).

**Repro / evidence.** Fake-session tests cannot see FK violations; on a real DB: `POST /api/jobs/manual {drive_id, session_id:S}`, `DELETE /api/sessions/S` before the ripper's identify POST, observe 500 `IntegrityError ... fk_jobs_pending_session_id` and the ripper log "identify failed (...); retrying in Ns" repeating.

**Tip check.** Still present at `71129cd9`: `routers/ripper.py:643-644` (unconditional assignment, no existence check).

**Suggested fix location.** feat/phase2-job-metadata — the FK and the column write are both introduced here.

**Verification.** untested-needs-hardware (needs a real Postgres + ripper); code trace only. Drill: `bash devtools/iso-smoke.sh` with a session deleted between trigger and identify.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/150

### D-029  S4  open  docs  origin #75

**Title.** Stale migration numbers and stale "inert" / "reads metadata_json['disc']" comments left in code the PR itself changed.

**Where.** `packages/arm_common/arm_common/schemas/job_metadata.py:21` and `:95` ("rows written before migration 0031" — the sections/flags lift is 0032), `services/backend/arm_backend/transcode_apply.py:68` ("pre-0031 fallback" — music section is 0032) and `:100` ("metadata-mirror scrub (migration 0032)" — it is 0033), `services/backend/arm_backend/routers/jobs.py:961` ("pre-0031 top-level key" — 0032), `packages/arm_common/arm_common/enums.py:78-81` (says both "Set by rip-complete when a placeholder disc rips…" and "Inert today — no code path sets this yet" — rip_complete now sets it at `routers/ripper.py:1108`), `services/backend/arm_backend/metadata/musicbrainz.py:111-114` ("transcode_apply reads metadata_json['disc']" — transcode_apply now reads `job.disc_number`, lifted at identify `routers/ripper.py:586-589`). All at `7fe7b5e7`.

**What.** Commit 35a77144 renumbered the migrations 0030-0032 -> 0031-0033 and 4c8eb7b7 claims to "fix stale migration-renumber prose", but these references still point at the pre-renumber ids, and the enum comment contradicts itself inside a single comment block that this PR edited. A future reader following "before migration 0031" to decide whether a fallback can be removed would look at the wrong migration.

**Repro / evidence.** `grep -n "003[0-9]" packages/arm_common/arm_common/schemas/job_metadata.py services/backend/arm_backend/transcode_apply.py services/backend/arm_backend/routers/jobs.py`; `grep -n "Inert today" packages/arm_common/arm_common/enums.py`.

**Tip check.** Still present at `71129cd9`: `job_metadata.py:21,105` ("migration 0031"), `transcode_apply.py:80` ("pre-0031"), `routers/jobs.py:1021` ("pre-0031"), `enums.py:106-111` ("Inert today — no code path sets this yet"), `metadata/musicbrainz.py:113`.

**Suggested fix location.** feat/phase2-job-metadata — the renumber commit is in this PR.

**Verification.** grep at head and tip, as above.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/151

### D-030  S4  open  ui-neu  origin #75

**Title.** `readJobMetadata` prefers the stale `provider_raw.arm_server.video_type` over the new authoritative `job.media_type` column, and legacy rows lose their Type/multi_title/source_type entirely.

**Where.** `services/ui-neu/frontend/src/lib/utils/job-fields.ts:64-80` at `7fe7b5e7`; migration `services/backend/migrations/versions/0032_job_metadata_sections.py:88-91` (unhandled strays go to `provider_raw["legacy"]`).

**What.** The PR makes `media_type` the routing input and `TitleSearch.svelte:123-127` now writes it (`media_type: editType === 'series' ? 'tv' : 'movie'`) instead of `metadata.video_type`. But the details panel still reads `armServer.video_type` first and only falls back to `job.media_type` when that is absent — so after an operator re-identifies a 1337server-matched disc from movie to series, the Type field keeps showing the arm_server payload's "movie" (the backend's `JobMetadata` docstring says `provider_raw` is "never read for behaviour"). Separately, 0032 files pre-PR arm_server extras under `provider_raw.legacy`, not `provider_raw.arm_server`, and 0031 does not backfill `media_type`, so every job identified before the upgrade shows no Type / multi_title / source_type after it. UI state disagreeing with the column is a lie about backend state, but it is display-only, hence S4.

**Repro / evidence.** `services/ui-neu/frontend/src/lib/utils/job-fields.ts`: `const vt = asScalarString(armServer.video_type); if (vt !== undefined) { out.video_type = vt; } else if (job?.media_type) {...}`. Unit repro: `readJobMetadata({provider_raw:{arm_server:{video_type:'movie'}}}, {media_type:'tv', season:null, pending_session_id:null}).video_type === 'movie'`.

**Tip check.** Still present at `71129cd9`: `job-fields.ts:64,73-77` (same precedence; `provider_raw.arm_server` only).

**Suggested fix location.** feat/phase2-job-metadata — the column fallback was added here; flip the precedence (column first) and either read `provider_raw.legacy` too or backfill `media_type` in 0031 from the legacy `video_type`/`kind` keys.

**Verification.** Code read at head and tip; svelte-check/vitest pass so no test asserts either way.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/152

### D-031  S4  open  migrations  origin #75

**Title.** 0032's downgrade is a no-op although its upgrade moves `artist`/`album`/`tracks` out of the top level — after `alembic downgrade 0031` the base-branch code can no longer name or list music tracks.

**Where.** `services/backend/migrations/versions/0032_job_metadata_sections.py:111-112` (`def downgrade(): pass`) at `7fe7b5e7`.

**What.** The docstring argues "the sections remain readable by the pre-migration code's fallbacks", but the pre-migration code (base `transcode_apply._build_track_ctx`, base ui-neu `extractMusicTracks`) reads `metadata_json["artist"|"album"|"tracks"]` at the top level and has no `music.*` fallback — the fallbacks only exist in the *new* code. Likewise `imdb_id`/`tmdb_id` move under `identity.external_ids` and the base `job-fields.ts` reads `md.imdb_id`. So the migration is reversible in schema terms only; a rollback silently blanks `{artist}`/`{album}`/`{track_title}` for every migrated music job. 0031's downgrade has the smaller, documented equivalent (dropped `season`/`disc` keys are not restored). Data-only, rollback-only, hence S4 under the "migrations must be reversible" invariant.

**Repro / evidence.** `git show origin/feat/drive-lifecycle-6:services/backend/arm_backend/transcode_apply.py | grep -n 'metadata.get("artist")'` vs 0032 `_reshape` moving the key into `out["music"]`.

**Tip check.** Still present at `71129cd9`: `0032_job_metadata_sections.py:111-112` (`downgrade(): pass`).

**Suggested fix location.** feat/phase2-job-metadata — implement the inverse reshape (copy `music.artist/album/tracks`, `identity.external_ids.*` and `flags.*` back to the top level, re-spread `provider_raw.legacy`) or document the irreversibility in the migration docstring instead of claiming readability.

**Verification.** Code read; not executed (no Postgres in the sandbox).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/153

### D-032  S4  open  backend  origin #75

**Title.** New uncovered backend statements: resolve's `tvdb` / `musicbrainz_release` external-id overlay branches.

**Where.** `services/backend/arm_backend/routers/jobs.py:940` and `:942` at `7fe7b5e7` (introduced in 52ce650f / 365b8638).

**What.** `uv run coverage run -m pytest -q && uv run coverage report -m` reports `routers/jobs.py` 99% with lines 940 and 942 missing. Both are new in this PR (the per-field `model_fields_set` overlay from Fix 75-5); only the `imdb`/`tmdb` members are exercised by `test_jobs_router.py`. The Backend holds a 100%-statement policy, and the uncovered lines are exactly the "explicit null clears" semantics the PR body advertises, so a regression there would be invisible.

**Repro / evidence.** `uv run coverage report -m --include='services/backend/arm_backend/routers/jobs.py'` -> `Missing: 940, 942`.

**Tip check.** Still present at `71129cd9`: `routers/jobs.py:1003-1006` (same branches); `git grep -n "tvdb\|musicbrainz_release" origin/integration/all-prs-3 -- services/backend/tests` finds no resolve test touching either member (only config key-check / identity-settings tests), so no later PR or straggler covered them.

**Suggested fix location.** feat/phase2-job-metadata — add the two members to the existing `external_ids` resolve test.

**Verification.** coverage run at head (whole suite, 2169 tests).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/154

### D-033  S3  open  backend  origin #76

**Title.** Unidentified music CD (media_type=None, disc_type=cd) is still routed to the drive's video default; the seeded music routes never fire for it.

**Where.** `services/backend/arm_backend/auto_session.py:533-534` (`if job.media_type is None: return drive.default_session_id`) and `:548-549` (routes skipped when media_type is None) at `4580f65a` (head `517defe3`); `services/backend/arm_backend/routers/ripper.py:580` sets `job.media_type` only when MusicBrainz returned a result.

**What.** For a CD the backend knows `disc_type=cd` at identify regardless of MusicBrainz, but `job.media_type` is only set on a MusicBrainz hit. When lookup fails (no disc id, no match, offline), `resolve_routed_session_id` short-circuits to the drive default (typically a movie session) because `job.media_type is None`, bypassing the compatibility gate and the `(music, cd)` / `(music, NULL)` seeded routes. At rip-complete `maybe_auto_apply_session` then applies a video session to audio tracks → `compute_outputs` resolves nothing → an empty WAITING_IDENTIFY application is parked (`auto_session.py:454-470`, `skipped_reason="no_outputs"`) that no drain can ever fill, and the user must hand-apply the music session. G-17's "a drive default must not permanently swallow a media type it was never meant for" is only enforced when identification succeeded; `disc_type=cd` alone is a sufficient signal that the job is music.

**Repro / evidence.** `services/backend/tests/test_session_routing.py::test_unknown_job_media_type_still_prefers_drive_default` enshrines the behaviour (job media_type=None, drive default returned even with a route present); combine with `routers/ripper.py:574-580` (media_type assignment inside `if result is not None:`). Equivalent manual drill: insert a CD not in MusicBrainz on a drive whose default session is a movie session with `auto_transcode_on_idle=true`; observe a parked empty application for the movie session instead of the Music FLAC route.

**Tip check.** Still present at `71129cd9`: `services/backend/arm_backend/auto_session.py:1041-1043` (`if job.media_type is None: return drive.default_session_id`) and `:1057-1058`; tip `routers/ripper.py` still has no CD→MUSIC fallback (only `DiscType.CD: "rpr_builtin_music_standard"` for the rip preset).

**Suggested fix location.** feat/phase3-session-routing — either set `job.media_type = MediaType.MUSIC` at identify when `disc_type == CD` and lookup failed, or make the drive-default gate/route lookup use `disc_type == CD ⇒ music` when `media_type is None`.

**Verification.** Code trace + existing test; `untested-needs-hardware` for the live drill (a real CD absent from MusicBrainz).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/155

### D-034  S3  open  ui-neu  origin #76

**Title.** SessionRoutesCard cannot display or create a route to a compatible-but-different-media-type session the backend accepts (e.g. movie → iso-dump session, movie → tv session).

**Where.** `services/ui-neu/frontend/src/lib/components/settings/SessionRoutesCard.svelte:38-40` (`sessionsFor` strict `s.media_type === mediaType`) and `:159-176` (select `value={route?.session_id ?? ''}` over those options) at `4580f65a`/`88eee5de` (head `517defe3`).

**What.** Commit 79969314 made `PUT /api/session-routes` accept any `_media_types_compatible` pairing (tests `test_upsert_movie_route_to_iso_session_accepted`, `..._to_tv_session_accepted`), and the resolver honours such routes. The card only offers sessions whose media_type equals the row's media_type, so (a) an admin cannot create a movie→iso route from the UI, and (b) an existing one (created via API, or a tv session routed for movie discs) renders in the Movie grid row with a `<select>` whose value matches no option — the row reads as none/blank while the backend route is live and winning resolution. The "Other routes" fallback (88eee5de) only catches rows whose *media_type/disc_type* are off-grid, not off-filter sessions. Workaround: the Clear button still appears for the row.

**Repro / evidence.** `curl -X PUT /api/session-routes -d '{"media_type":"movie","disc_type":null,"session_id":"<iso session id>"}'` (200), then open Settings › Sessions: the Movie / Any disc select shows no selected session. Backend test proving acceptance: `services/backend/tests/test_session_routes_router.py::test_upsert_movie_route_to_iso_session_accepted`.

**Tip check.** Still present at `71129cd9`: `SessionRoutesCard.svelte:39-41` (`return sessions.filter((s) => s.media_type === mediaType);`).

**Suggested fix location.** feat/phase3-session-routing — filter options with the same compatibility matrix the backend uses (movie/tv ∪ iso/data for video rows), or at least include the currently-routed session in the option list.

**Verification.** Code read at head and tip; backend acceptance confirmed by the PR's own router tests.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/156

### D-035  S4  open  backend  origin #76

**Title.** Three new backend statements are uncovered (100%-statement policy): factory-raise branch and old-client close guard in the SSH-rebuild path; blank-output_path skip in find_collisions.

**Where.** `services/backend/arm_backend/transcode_dispatcher.py:594-600` and `:620-621`, `services/backend/arm_backend/transcode_apply.py:191` at `4580f65a` (PR head `517defe3`).

**What.** `uv run coverage run -m pytest -q && uv run coverage report` at the PR head reports these lines as missed. They are new in this PR (`git blame` → 4580f65a) and carry no `pragma: no cover`. The `except Exception as factory_exc: ... raise` branch (docker factory raising), the `except Exception: pass` around `old_docker.close()`, and the `if not row.output_path: continue` guard have no test at this PR's head.

**Repro / evidence.**

```
services/backend/arm_backend/transcode_apply.py           142      1     58      2    98%   191, 193->189
services/backend/arm_backend/transcode_dispatcher.py      294      5     82      2    98%   217->239, 558->563, 594-600, 620-621
```

**Tip check.** OPEN. On the tip the lines are covered by tests added in `0048ca44` ("test(backend): cover the remaining 45 uncovered statements": `test_transcode_dispatcher.py` asserts "rebuild failed" and `dead.close.side_effect = RuntimeError(...)`; `test_transcode_apply_full.py::test_find_collisions_skips_live_rows_without_output_path`). `git branch -r --contains 0048ca44` → only `origin/integration/all-prs-3` — fixed only on the integration tip by `0048ca44`, which is in no open PR.

**Suggested fix location.** feat/phase3-session-routing — cherry-pick the three tests from 0048ca44 (or add `pragma: no cover` with justification on the two best-effort except blocks).

**Verification.** Ran coverage at head; grep'd tip tests; branch containment checked.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/157

### D-036  S4  open  docs  origin #76

**Title.** Stale migration references in model docstrings/comments after the 0034/0035 renumber and the conditional seed-marker UPDATE.

**Where.** `packages/arm_common/arm_common/models/session_route.py:89` ("see migration 0033's docstring") and `packages/arm_common/arm_common/models/config.py:97-98` ("See migration 0035_session_routes_seed_marker for why it defaults true on any already-deployed Postgres DB") at `345892b8`/`96aa8fcc` (head `517defe3`).

**What.** The routing table migration is `0034_session_routes`, not 0033 (`0033_drop_metadata_mirrors` is PR #75's). And 0035 sets `session_routes_seeded=true` only `WHERE EXISTS (SELECT 1 FROM session_routes)` (96aa8fcc) — on an already-deployed DB without routes it stays `false`; the config.py comment still describes the pre-96aa8fcc unconditional behaviour and contradicts the migration's own docstring.

**Repro / evidence.** `grep -n "0033" packages/arm_common/arm_common/models/session_route.py`; `grep -n "defaults true" packages/arm_common/arm_common/models/config.py` vs `migrations/versions/0035_session_routes_seed_marker.py:66-72`.

**Tip check.** Still present at `71129cd9`: `session_route.py:25` ("see migration 0033's docstring"), `config.py:127` ("why it defaults true on any already-deployed Postgres DB").

**Suggested fix location.** feat/phase3-session-routing — same PR introduced both comments.

**Verification.** grep at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/158

### D-037  S4  open  backend  origin #76

**Title.** Concurrent `PUT /api/session-routes` for the same `(media_type, disc_type)` turns the NULLS-NOT-DISTINCT unique violation into a 500 (acknowledged follow-up).

**Where.** `services/backend/arm_backend/routers/session_routes.py:52-87` at `4580f65a` (head `517defe3`).

**What.** The upsert is select-then-insert with no `IntegrityError` handling; two writers racing on a new key both pass the `existing is None` check and the second `commit()` raises `IntegrityError` → unhandled 500 (jobs.py's apply path handles the same class → 409). The PR body lists "IntegrityError → 409 on concurrent route upserts" as a deliberate follow-up; recorded here so it does not fall off the register. Workaround: retry the PUT (it then updates in place).

**Repro / evidence.** Needs real Postgres (the fake-session tier has no unique index): two parallel `PUT /api/session-routes` with identical body for an unrouted key; second returns 500.

**Tip check.** Still present at `71129cd9`: `routers/session_routes.py` upsert has no `except IntegrityError` (grep).

**Suggested fix location.** feat/phase3-session-routing — mirror jobs.py's `except IntegrityError: rollback; 409`.

**Verification.** Code read; not executed (needs Postgres).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/159

### D-038  S2  open  backend  origin #73

**Title.** Stored bash secret can be unmasked through PATCH with a script name that is not on disk (claimed-impossible `secret_keys` forgery).

**Where.** `services/backend/arm_backend/notifications/bash_hook.py:188-191` (`storage_config` FileNotFoundError fallback trusts `incoming["secret_keys"]`) and `:161-172` (`merge_bash_config` substitutes the stored value for `<hidden>` before that), called from `services/backend/arm_backend/routers/notifications.py:271-276` at `1db7341b` (introduced in `961e6327` "secret_keys is server-owned and script errors are redacted").

**What.** An authenticated writer (admin role) PATCHes a bash channel with `{"config": {"type":"bash","script":"does-not-exist.sh","inputs":{"SMTP_PASS":"<hidden>", ...}}}`. `merge_bash_config` replaces `<hidden>` with the stored clear-text secret; `storage_config` cannot read a header for the missing file and takes `secret_keys` from the request, which `BashChannelConfig` defaults to `[]`. The stored config now has the secret in `inputs` with `secret_keys == []`, so `mask_bash_config` on the next GET returns it in clear (the attacker then PATCHes the script name back). Expected: when the script header cannot be read, keep the *existing* channel's `secret_keys` (and never let the request body shrink the set), or refuse a `<hidden>` input whose key is not in the resulting secret set.

**Repro / evidence.** Scratch fake-session router test at head (not committed) using the PR's own `_bash_channel()` fixture (stored `inputs.SMTP_PASS="pw"`, `secret_keys=["SMTP_PASS"]`):
```
PATCH /api/notifications/channels/ncl_b  {"config":{"type":"bash","script":"does-not-exist.sh","inputs":{"TO":"me@x","SMTP_PASS":"<hidden>"}}}  -> 200
BEFORE {'script': 'ok.sh', 'inputs': {'TO': 'me@x', 'SMTP_PASS': '<hidden>'}, 'secret_keys': ['SMTP_PASS']}
AFTER  {'script': 'does-not-exist.sh', 'inputs': {'TO': 'me@x', 'SMTP_PASS': 'pw'}, 'secret_keys': []}
```
The PR's own test `test_storage_config...` (test_notifications_bash_hook.py:173-177) asserts the fallback "keeps the caller's secret_keys" — i.e. it tests the forgeable behaviour. Severity S2 rather than S1 because `require_writer` is admin-only (`auth.py:124-129`), so this is admin→admin read-back of a value the same role could overwrite; it is still a stated security property that is not delivered and a persisted clear-text secret.

**Tip check.** Still present at `71129cd9`: `git diff 1db7341b origin/integration/all-prs-3 -- services/backend/arm_backend/notifications/bash_hook.py` is empty; router bash paths unchanged (only `inbox_dismiss_all` differs). No straggler fixes it.

**Suggested fix location.** feat/notifications-bash-channel — the PR introduces `storage_config`; in `patch_channel` pass the existing channel's `secret_keys` as the fallback (union with incoming) instead of the request's.

**Verification.** Reproduced with the scratch test above at head (3 runs), then file removed; `git status` clean.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/160

### D-039  S3  open  backend  origin #73

**Title.** `POST /scripts/preview` with `run: true` returns script stdout/stderr/error unredacted, including stored secret values merged in via `channel_id`.

**Where.** `services/backend/arm_backend/routers/notifications.py:380-384` at `1db7341b` (`result = await run_script(...)` returned as-is; `redact_secrets` is applied only in `_bash_send` at `:463` and in `BashListener` at `bash_listener.py:65`).

**What.** The preview endpoint deliberately lets a caller fill `<hidden>` inputs from the stored channel (`channel_id`) and run the script. If the script echoes an input (`set -x`, `env`, a curl error quoting `--user`), the stored secret comes back in `result.stdout`/`stderr`/`error` and is rendered in the Test panel (`BashTestPanel.svelte:290-291`). The dispatch and `/channels/{id}/test` paths redact the same output before persisting; the preview should apply `redact_secrets` to all three fields.

**Repro / evidence.** Scratch router test at head: script `echo "pass=$SMTP_PASS"; echo "err=$SMTP_PASS" >&2; exit 1`, stored channel with `SMTP_PASS="pw"`; `POST /scripts/preview {"channel_id":"ncl_b","run":true,"config":{...,"inputs":{"SMTP_PASS":"<hidden>"}}}` → 200 with `result.stdout == "pass=pw\n"`, `result.stderr == "err=pw\n"`, `result.error == "script exit code 1: err=pw"`, while `inputs.SMTP_PASS == "<hidden>"` in the same response.

**Tip check.** Still present at `71129cd9`: `services/backend/arm_backend/routers/notifications.py:380-384` identical (router diff head→tip touches only `inbox_dismiss_all`).

**Suggested fix location.** feat/notifications-bash-channel — wrap `result` fields with `redact_secrets(..., run)` in `preview_script`.

**Verification.** Reproduced with scratch test at head; file removed afterwards.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/161

### D-040  S3  open  backend  origin #73

**Title.** Timeout kills only the `bash` process; the script's children keep running (no process group / `killpg`).

**Where.** `services/backend/arm_backend/notifications/bash_runner.py:67-81` at `1db7341b` (`create_subprocess_exec(...)` without `start_new_session=True`; `proc.kill()` on timeout).

**What.** On timeout `proc.kill()` SIGKILLs bash; whatever bash was waiting on (`curl`, `sleep`, an SMTP client) is reparented and keeps running with the backend's resources, every tick, for every stuck hook. The PR body claims "timeout kill/reap". Expected: start the hook in its own session/process group and `os.killpg(proc.pid, SIGKILL)` on timeout.

**Repro / evidence.** Scratch script against head's `run_script` (Python 3.14.8): hook `sleep 8`, `timeout_seconds=1` → result `script timed out after 1s` returned at 1.03s, and `pgrep -af 'sleep 8'` immediately after shows the orphaned `sleep 8` still alive. The PR's `test_run_script_timeout` (test_notifications_bash_runner.py:119-122) asserts only the result object, not the tree.

**Tip check.** Still present at `71129cd9`: `bash_runner.py` byte-identical to head.

**Suggested fix location.** feat/notifications-bash-channel.

**Verification.** Empirical, see above.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/162

### D-041  S3  open  backend  origin #73

**Title.** A hook that exits 0 but leaves a background child holding stdout/stderr is recorded as a timeout failure.

**Where.** `services/backend/arm_backend/notifications/bash_runner.py:78-89` at `1db7341b` (`wait_for(proc.communicate(), timeout)` — completion is gated on pipe EOF, not process exit).

**What.** The v2 `BASH_SCRIPT` idiom of kicking off long work in the background (`long-task &` / `nohup ... &`, `exit 0`) keeps the inherited stdout/stderr pipes open, so `communicate()` never returns until the child exits; the run is reported "script timed out after Ns", `last_error` is set, the dispatch-log row is `success=false`, and the channel shows red, although the script succeeded. The docs never mention that background children must redirect their fds. Expected: await process exit and treat open pipes after exit as success (drain with a short grace), or document the `>/dev/null 2>&1 &` requirement.

**Repro / evidence.** Scratch script at head: hook `sleep 8 &\nexit 0`, `timeout_seconds=1` → `ok=False, error="script timed out after 1s: bg.sh"` after 1.0s, even though bash had exited 0 immediately.

**Tip check.** Still present at `71129cd9`: `bash_runner.py` identical.

**Suggested fix location.** feat/notifications-bash-channel (same hunk as C3).

**Verification.** Empirical, see above.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/163

### D-042  S3  open  backend  origin #73

**Title.** `OSError` from `create_subprocess_exec` (e.g. E2BIG from an input template with a width spec) is uncaught: 500 on preview, and the listener skips bookkeeping and the remaining bash channels for that event.

**Where.** `services/backend/arm_backend/notifications/bash_hook.py:64-68` (`_render_input` has no output cap, unlike `resolve_title_body`'s 4000/16000 caps at `notification_format.py:95-100`) and `bash_runner.py:67-76` (no `except OSError`), surfaced at `routers/notifications.py:380-383` (`preview_script`) and `bash_listener.py:61-67` (only `HookError` is caught) at `1db7341b`.

**What.** An input value like `{job_title:>300000}` (any writer can type it) renders to a 300 kB env var; Linux `MAX_ARG_STRLEN` (128 kB) makes `execve` fail with `OSError: [Errno 7] Argument list too long`. `preview_script(run=True)` returns 500; in `BashListener.handle` the exception escapes the per-channel try (which only catches `HookError`), so `last_*`/dispatch-log are not written for that channel and the `for channel in targets` loop aborts before later bash channels; the dispatcher logs it and marks the event notified. Expected: cap rendered input length like title/body, and convert `OSError` from spawn into a `BashRunResult(ok=False, error=...)`.

**Repro / evidence.** `prepare_run(config={"script":"echo.sh","inputs":{"TO":"{job_title:>300000}"}}, ...)` then `run_script(...)` at head → `OSError [Errno 7] Argument list too long: '/usr/bin/env'`. Scratch router test: `POST /scripts/preview {"run": true, "config": {..., "inputs": {"TO": "{job_title:>300000}"}}}` → HTTP 500.

**Tip check.** Still present at `71129cd9`: `bash_hook.py`, `bash_runner.py`, `bash_listener.py` identical to head.

**Suggested fix location.** feat/notifications-bash-channel.

**Verification.** Empirical at head (python script + scratch router test).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/164

### D-043  S3  open  devtools  origin #73

**Title.** `install.sh` (the canonical installer) neither creates `scripts/` nor mounts `/scripts` into `arm-backend`, so installer-deployed stacks cannot use bash hooks without a hand-written override.

**Where.** `install.sh:311` (creates/chmods only `raw media logs`) and `install.sh:1393-1399` (arm-backend `volumes:` block: `./raw`, `./media`, `./logs`, certs, docker.sock — no `./scripts:/scripts:ro`) at `1db7341b`; the mount exists only in `docker-compose.yml.example:98` (used by `devtools/setup-dev.sh`).

**What.** Memory `feedback_ui_port_8081.md`: "the installer is the source of truth for deployment values". With `install.sh` the backend has no `/scripts`; `list_scripts` returns `[]` and the picker says "No scripts found" forever. The PR body acknowledges this ("install.sh is untouched (legacy); the mount is logged for the installer rewrite") and documents a `docker-compose.override.yml` workaround in `docs/ops/notification-scripts.md:20-31`, hence S3 not S2.

**Repro / evidence.** `grep -n "scripts" install.sh` at head → no mount, no mkdir; same at tip (`git show origin/integration/all-prs-3:install.sh | grep -n "scripts:ro\|arm/scripts"` → empty).

**Tip check.** Still present at `71129cd9`: tip `install.sh:1396` block still lacks the mount; no PR in the stack adds it.

**Suggested fix location.** feat/notifications-bash-channel (or #83 feat/setup-dev-stack-lifecycle, which touches deployment scripts) — add `mkdir -p "$PREFIX/scripts"` next to line 311 and `- ./scripts:/scripts:ro` to the backend volumes template.

**Verification.** Code reading of both heads; untested on a live installer run.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/165

### D-044  S3  open  backend  origin #73

**Title.** An unreadable file in `/scripts` makes `GET /api/notifications/scripts` 500 for every script (PermissionError not handled).

**Where.** `services/backend/arm_backend/notifications/script_meta.py:121-123` (`_read_head` opens every entry) called unguarded from `list_scripts` at `:158` and from `read_script_info` at `:134`; `get_scripts` at `routers/notifications.py:331-333` and `get_script` at `:388-394` (catches only `ValueError, FileNotFoundError`) at `1db7341b`.

**What.** The mount is a host directory edited as root; a file copied with `sudo cp` under a 077 umask, or deliberately `chmod 700 root:root` because it embeds a token, is listed by `iterdir()`/`is_file()` but `open("rb")` raises `PermissionError` for the PUID user. The whole listing 500s, so the picker shows "Could not list scripts" and no bash channel can be created or edited until the operator finds the offending file. Expected: skip unreadable entries (or report them `executable: false` with a reason) and 404/422 on detail.

**Repro / evidence.** Code path: `list_scripts` → `_read_head(p)` → `path.open("rb")`; no `except OSError` anywhere in `script_meta.py` (`grep -n "PermissionError\|OSError" script_meta.py` → none). Cannot trigger EACCES as root in this sandbox.

**Tip check.** Still present at `71129cd9`: `script_meta.py` identical to head.

**Suggested fix location.** feat/notifications-bash-channel.

**Verification.** Code reading; to confirm on a host: `sudo install -m 700 -o root /dev/null arm/scripts/x.sh` then `GET /api/notifications/scripts` as admin.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/166

### D-045  S4  open  devtools  origin #74

**Title.** Style lint misses `style={…}` bindings and value-less `style:prop` shorthand; the PR itself relies on the gap.

**Where.** `devtools/ui-neu-style-lint.mjs:66-73` at `2ed17bf2` (introduced in `390ea291`); escapees at `services/ui-neu/frontend/src/routes/jobs/[id]/+page.svelte:295`, `src/lib/components/PosterImage.svelte:34,47`, `src/lib/components/Skeleton.svelte:14-15`.

**What.** Rule 1 is `/\sstyle="([^"]*)"/` and rule 2 is `/\sstyle:([a-zA-Z-]+)=/`. A Svelte `style={expr}` attribute, a single-quoted `style='…'`, and the shorthand directive `style:width` (no `=`) are never visited, so arbitrary inline CSS passes the gate. At base the job page had `style="aspect-ratio: {…}"` (`+page.svelte:302` at `1db7341b`), which this lint WOULD flag; commit `390ea291` changed it to `style={`aspect-ratio: ${…}`}` and the lint reports 0. Themes cannot override these inline declarations, which is exactly what the body says the system prevents.

**Repro / evidence.**

```
cd services/ui-neu/frontend && npm run lint:styles            # 0 violation(s) in 120 file(s)
grep -nE "\sstyle=\{|\sstyle:(width|height)\b" src/routes/jobs/[id]/+page.svelte src/lib/components/PosterImage.svelte src/lib/components/Skeleton.svelte
# +page.svelte:295  style={`aspect-ratio: ${job.disc_type === 'cd' ? '1/1' : '2/3'}`}
# PosterImage.svelte:34,47  style={styleStr || undefined}
# Skeleton.svelte:14-15  style:width / style:height
node -e "import('./devtools/ui-neu-style-lint.mjs').then(m=>console.log(m.lintSource('<div style={x} style:width></div>','a.svelte')))"   # []
```

**Tip check.** Still present at `71129cd9`: lint regexes unchanged (`git diff 2ed17bf2 71129cd9 -- devtools/ui-neu-style-lint.mjs` only adds comment-stripping in rule 4d, straggler `f4375669`, in no PR branch); escapees at tip `routes/jobs/[id]/+page.svelte:375`, `PosterImage.svelte:42,64`, `Skeleton.svelte:11` (`style:width style:height`).

**Suggested fix location.** chore/ui-neu-css-cleanup — extend rule 1 to `style=\{` and `style='`, rule 2 to `style:([a-zA-Z-]+)(?=[\s=>/])`, then convert the job-page `aspect-ratio` to a `data-disc-type` rule (PosterImage/Skeleton dynamic sizes can go through `style:--w`/`style:--h` custom properties, which the lint already allows).

**Verification.** Ran lint and the greps above at head; read tip files.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/167

### D-046  S4  open  devtools  origin #74

**Title.** Lint is a ban-list, not the allow-list the body and the `ALLOWED` table describe; ~437 sizing/position utilities pass unchecked.

**Where.** `devtools/ui-neu-style-lint.mjs:25,57-58` at `2ed17bf2` (`// anything else is a vocabulary or local class: allowed`).

**What.** Tokens that match neither `ALLOWED` nor `BANNED_FAMILIES` are accepted. Tailwind families `w-*`/`h-*` (other than full/auto), `fixed`, `top-*`/`right-*` (other than 0), `object-*`, `aspect-*`, `line-clamp-*`, `basis-*`, `h-screen`, fractional sizes are all in that gap. A future `w-[37px]`-free but still arbitrary `w-96 fixed top-1 right-1` will pass, contradicting "bans utility styling outside the allowed layout families" and the "0 violations" table. (Icon sizing `h-4 w-4` is explicitly intended per `Glyph.svelte` comment; the rest is not.)

**Repro / evidence.**

```
cd services/ui-neu/frontend && node /tmp/claude-0/-home-user/e06fb963-3780-5816-b936-b6d6249b1440/scratchpad/pr74-leak.mjs
# distinct leaked tokens 51 total 437
# table-cell:84 table-header:69 w-4:34 h-4:33 ... fixed:4 top-1:2 right-1:2 h-screen:1 aspect-square:1 object-cover:1 line-clamp-2:2 basis-full:2 h-2/5:1 w-2/5:1 max-w-0:1
# e.g. src/lib/components/PosterImage.svelte:11 'poster-image h-28 w-20 shrink-0 object-cover'; TitleSearch.svelte:239 'line-clamp-2'; DriveMaintenance.svelte:53 'basis-full'
```

**Tip check.** Still present at `71129cd9`: `ALLOWED`/`BANNED_FAMILIES` unchanged; `object-cover` (2 files), `h-screen`, `aspect-square`, `line-clamp-2`, `basis-full`, `top-1`/`right-1` (2 files), `h-2/5` all still in tip `.svelte` sources.

**Suggested fix location.** chore/ui-neu-css-cleanup — either add the sizing/position families to `ALLOWED` explicitly (and say so in `docs/ui-neu-theming.md`) or flip the default to "unknown Tailwind-shaped token = violation"; the body's claim should match the code either way.

**Verification.** Script above at head; `git grep` on the tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/168

### D-047  S4  open  docs  origin #74

**Title.** `THEME_TEMPLATE.md` still requires the alias tokens this PR removed and nothing consumes.

**Where.** `services/ui-neu/THEME_TEMPLATE.md:95-105` (JSON skeleton), `:112` ("13 required CSS custom properties"), `:131-140` (Token Reference) at `2ed17bf2` (file untouched by the PR).

**What.** The template tells theme authors to set `--color-primary-dark`, `--color-primary-light-bg`, `--color-primary-light-bg-dark`, `--color-primary-border` ("Deep accent for borders/outlines", "highlighted row/card bg"). After this PR `tokens.css` drops them (`tokens.test.ts` asserts they stay gone) and no CSS anywhere reads them: `grep -rn "var(--color-primary-light-bg\|var(--color-primary-border\|var(--color-primary-dark" src static docs` → 0 hits at head. `applyTokens` (`colorScheme.ts`) still writes whatever keys a scheme supplies, so the tokens are set but dead. The new `docs/ui-neu-theming.md` never mentions `THEME_TEMPLATE.md`, so authors following the template get silently ignored tokens and no pointer to the real contract.

**Repro / evidence.**

```
sed -n 95,105p services/ui-neu/THEME_TEMPLATE.md      # lists the 4 dead tokens as required
git grep -n "var(--color-primary-light-bg\|var(--color-primary-border\|var(--color-primary-dark" 2ed17bf2 -- services/ui-neu docs   # (no output)
```

**Tip check.** Still present at `71129cd9`: `git diff 2ed17bf2 71129cd9 -- services/ui-neu/THEME_TEMPLATE.md` is empty; same `git grep` on the tip returns nothing.

**Suggested fix location.** chore/ui-neu-css-cleanup — rewrite the template's token list to the `tokens.css` roles (or delete it and point at `docs/ui-neu-theming.md`), since this is the PR that retired the aliases.

**Verification.** greps above at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/169

### D-048  S4  open  docs  origin #74

**Title.** `.claude/memory/MEMORY.md` index drops the em-dash entry and omits three new memory files.

**Where.** `.claude/memory/MEMORY.md:16` at `2ed17bf2`; dropped by `d863ba2a` ("memory: special-character rule is correction only, not rewording"), first contained in `origin/chore/ui-neu-css-cleanup`.

**What.** The PR's diff replaces the `[No em-dashes in UI copy](feedback_no_em_dashes_in_ui_copy.md)` index line with the Standard-UI-patterns line instead of adding it, while the em-dash file is still present (and modified in this same diff). The diff also adds `feedback_glyph_icons_not_emoji.md`, `feedback_install_sh_legacy.md`, `feedback_no_session_links.md` without index lines. CLAUDE.md: "When saving a new memory … update MEMORY.md there" and "read MEMORY.md — it's a short index (one line per entry)". Un-indexed entries are never read at session start.

**Repro / evidence.**

```
comm -13 <(grep -oE "\]\([a-z_0-9-]+\.md\)" .claude/memory/MEMORY.md | tr -d '](' | tr -d ')' | sort) <(ls .claude/memory | grep -v MEMORY.md | sort)
# feedback_glyph_icons_not_emoji.md  feedback_install_sh_legacy.md  feedback_no_em_dashes_in_ui_copy.md  feedback_no_session_links.md
git diff origin/feat/notifications-bash-channel...2ed17bf2 -- .claude/memory/MEMORY.md   # -No em-dashes line / +Standard UI patterns line
```

**Tip check.** Partially fixed: `feedback_no_session_links.md` is indexed on the tip (`MEMORY.md:23`); `feedback_no_em_dashes_in_ui_copy.md`, `feedback_glyph_icons_not_emoji.md`, `feedback_install_sh_legacy.md` are still un-indexed at `71129cd9` → OPEN (partial fix noted).

**Suggested fix location.** chore/ui-neu-css-cleanup — restore the em-dash line and add the three missing lines.

**Verification.** Commands above at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/170

### D-049  S4  open  ui-neu  origin #74

**Title.** Markup rewrite leaves ARIA state/label attributes on role-less elements (files-page root tabs, channel-type label).

**Where.** `services/ui-neu/frontend/src/routes/files/+page.svelte:480` and `src/lib/components/notifications/AddChannelForm.svelte:83` at `2ed17bf2` (both from `390ea291`).

**What.** The files page's `<nav aria-label="File root tabs">` (base `1db7341b`) became `<div class="tabs" aria-label="File root tabs">` with no `role`: `aria-label` is prohibited on a generic element (ARIA 1.2; axe `aria-prohibited-attr`) and the navigation landmark is lost, while every other tab strip in the PR kept a role (`role="tablist"` in SessionsArea:237, `role="radiogroup"` in LogView:146/160 and InterfaceSettings:50, `<nav>` in settings:315). `AddChannelForm` gained `<label … aria-checked={…}>` as a styling hook; `aria-checked` is not permitted on `label` (the hidden radio input already carries the state). The body's "unruled `role` additions … resolved" removed roles but left the orphaned ARIA attributes.

**Repro / evidence.**

```
grep -n 'aria-label="File root tabs"' src/routes/files/+page.svelte        # 480: <div class="tabs" aria-label="File root tabs">
grep -n 'aria-checked' src/lib/components/notifications/AddChannelForm.svelte   # 83: <label class="channel-type-option" aria-checked={type === t.key}>
```

**Tip check.** Still present at `71129cd9`: `routes/files/+page.svelte:496` (`<div class="tabs" aria-label="File root tabs">`), `AddChannelForm.svelte:110` (`aria-checked` on `<label>`), styled via `.channel-type-option[aria-checked='true']` at `:255`.

**Suggested fix location.** chore/ui-neu-css-cleanup — restore `<nav>` (or `role="tablist"` as SessionsArea does) on the files tabs; swap the label hook to `data-selected` or `:has(input:checked)`.

**Verification.** Read head and tip sources.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/171

### D-050  S3  open  ui-neu  origin #81

**Title.** `wsClient.start()` during the reconnect back-off clears the "Live updates unavailable" banner with no backend change (and opens a duplicate socket).

**Where.** `services/ui-neu/frontend/src/lib/api/ws.ts:49-53` (`start()`: `if (this.ws !== null) return; … statusStore.set('connecting'); this.connect();`) at `b2b7dad5`; status machine at `ws.ts:113`.

**What.** After a drop, the close handler sets `this.ws = null` and arms `reconnectTimer`; after the second failure `wsStatus` is `'offline'` and the banner shows. `start()` only guards on `this.ws !== null`, so any later `start()` call made while the timer is pending (a) resets `wsStatus` to `'connecting'`, hiding the banner although the backend is exactly as unreachable as before, and (b) opens a socket immediately while the pending timer fires a second one. `start()` is reached on every page mount: dashboard `routes/+page.svelte:228,233` (`startWS()`, `startRipperEvents()`), job detail `routes/jobs/[id]/+page.svelte:179`; `stopWS()` (`stores/rips.svelte.ts:50`) never calls `wsClient.stop()`, so the client is never in `idle` once started and every dashboard<->job navigation re-enters `start()`. The banner should stay until a connection actually authenticates, as the PR body and the component comment promise ("holds until a connection actually authenticates"). The duplicate-socket half is pre-existing at BASE (same guard); the status reset is new in this PR.

**Repro / evidence.** Added `services/ui-neu/frontend/src/lib/api/__tests__/ws.repro-pr81.test.ts` (same FakeWS harness as `ws.test.ts`); passes at head, i.e. the defect reproduces:
```ts
wsClient.start(); authAck(FakeWS.instances[0]);
FakeWS.instances[0].emit('close', {}); vi.advanceTimersByTime(1000);
FakeWS.instances[1].emit('close', {});
expect(get(wsStatus)).toBe('offline');            // banner up
wsClient.start();                                  // page mount during back-off
expect(get(wsStatus)).toBe('connecting');          // banner gone, backend unchanged
expect(FakeWS.instances.length).toBe(3);           // immediate extra socket
vi.advanceTimersByTime(2000);
expect(FakeWS.instances.length).toBe(4);           // pending timer fires a 4th
```

**Tip check.** Still present at `71129cd9`: `services/ui-neu/frontend/src/lib/api/ws.ts:50-52` identical; callers multiplied — `routes/jobs/[id]/+page.svelte:241,249`, `lib/stores/encoders.svelte.ts:76`, `lib/components/settings/GpusCard.svelte:156`, `lib/components/setup/steps/FinishStep.svelte:39` all call `wsClient.start()` on mount. `git log -S"statusStore.set('connecting')" origin/chore/ui-neu-css-cleanup..origin/integration/all-prs-3` shows only b2b7dad5.

**Suggested fix location.** feat/ws-origins-live-status — in `start()` return early when `this.reconnectTimer !== null` (the back-off already owns the retry), and only set `'connecting'` from the idle state (`retryIdx === 0`), so the banner is cleared solely by the auth-ack path at `ws.ts:137`.

**Verification.** Reproduced with the vitest above at head (1560 passed including it); same code at tip by `git show`.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/172

### D-051  S3  hoisted  devtools  origin #81

**Title.** Emptying the `ARM_ALLOWED_ORIGINS` default breaks WS for the Vue `arm-ui` on 8081 (the image install.sh deploys and the dev compose's 8081 service), whose nginx never forwards `X-Forwarded-Host`.

**Where.** `.env.example:45` (`ARM_ALLOWED_ORIGINS=`) at `b2b7dad5`, against `services/ui/nginx.conf:38-46` (`location = /ws { … proxy_set_header Host arm-backend; }`, no `X-Forwarded-Host`), `docker-compose.yml.example:140-149` (`arm-ui` -> `services/ui/Dockerfile`, `8081:443`), `.github/workflows/release.yml:49` (`service: [backend, ripper, transcode, ui]`).

**What.** `devtools/setup-dev.sh:251-265` creates `.env` from `.env.example`, and `setup-dev.sh:345` tells the developer to open `https://localhost:8081`, which at this commit is the Vue UI. Its nginx rewrites `Host` to `arm-backend` and this PR only adds `X-Forwarded-Host/-Proto` to ui-neu's `nginx.conf:55-56` and the vite proxy. The backend therefore compares Origin `https://localhost:8081` to `https://arm-backend` and closes with 1008 — exactly the "silent retry forever" the PR set out to fix, now on the canonical port with a fresh dev `.env`. The installed deployment is unaffected only because `install.sh:1159` still hardcodes `https://localhost:8081`, which also means G-28 (LAN IP / hostname) remains open for the published `arm-ui` image at this commit. Workaround: set `ARM_ALLOWED_ORIGINS` manually.

**Repro / evidence.**

```bash
# at b2b7dad5
grep -n "X-Forwarded-Host" services/ui/nginx.conf      # no output
grep -n "^ARM_ALLOWED_ORIGINS=" .env.example           # 45:ARM_ALLOWED_ORIGINS=
DATABASE_URL=postgresql://x:x@localhost/x ARM_SERVICE_TOKEN=x uv run python -c "from arm_backend.ws.router import _origin_allowed, settings; settings.ARM_ALLOWED_ORIGINS=[]; print(_origin_allowed('https://localhost:8081', [], request_host='arm-backend'))"   # prints False (verified at head)
```

**Tip check.** Fixed by #89 (chore/remove-vue-ui) in `daddb6a4` ("chore(ui): remove the Vue UI; ui-neu becomes arm-ui on 8081" — deletes `services/ui/`, compose has a single `arm-ui` on `8081:443` built from ui-neu whose nginx carries the forwarded headers); `git branch -r --contains daddb6a4` -> origin/chore/remove-vue-ui and above. Recommend: **move down** — merged alone, #81 leaves the 8081 UI (the one install.sh ships and setup-dev.sh points at) with no live updates on every fresh dev `.env`; a two-line `proxy_set_header X-Forwarded-Host $http_host; X-Forwarded-Proto $scheme;` in `services/ui/nginx.conf` (or keeping the 8081 default in `.env.example` until #89) closes it.

**Suggested fix location.** feat/ws-origins-live-status — same nginx hunk as `services/ui-neu/nginx.conf:52-56`, applied to `services/ui/nginx.conf`.
**Hoisted.** 2026-10-03: `9444a2291` on `feat/ws-origins-live-status`. The copy in the later PR becomes empty on restack.

**Verification.** Static (nginx config + `_origin_allowed` evaluation); end-to-end confirmation needs the compose stack (`bash devtools/setup-dev.sh up`, open `https://localhost:8081`, watch the backend log for "origin not allowed") — untested here, no Docker.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/173

### D-052  S4  open  backend  origin #81

**Title.** Stale test docstring: "empty allowlist means service-token only" contradicts the same PR's same-origin default.

**Where.** `services/backend/tests/test_ws_origin.py:41` at `b2b7dad5`.

**What.** The test keeps the Phase-4 wording while the PR changes the semantics: an empty allowlist now accepts same-origin browsers; the assertion only still passes because no `request_host` is supplied (the `if not host: return False` branch at `router.py:83-84`). The docstring should say "no host context and empty allowlist -> rejected".

**Repro / evidence.**

```
41:    """Phase 4 default: empty allowlist means service-token only."""
```

**Tip check.** Still present at `71129cd9`: `services/backend/tests/test_ws_origin.py:41` identical (`git log -S"Phase 4 default: empty allowlist" origin/chore/ui-neu-css-cleanup..origin/integration/all-prs-3` is empty).

**Suggested fix location.** feat/ws-origins-live-status — one-line docstring edit.

**Verification.** Read at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/174

### D-053  S2  hoisted  devtools  origin #83

**Title.** `setup-dev.sh up` force-removes rippers/transcoders with work in flight — a routine redeploy kills a running rip.

**Where.** `devtools/setup-dev.sh:50-60` (`docker rm -f ${ids}`) invoked unconditionally from the `up` branch at `:400`, at `42cf7ea7` (introduced in `9e5828c9`).

**What.** `remove_spawned_containers` does not look at container state or at what is running inside it. On `up` it SIGKILLs any ripper mid-`makemkvcon`/`abcde`/`dd` and any transcoder mid-HandBrake. The previous documented path (`docker compose up -d --build`) never touched these containers, and CLAUDE.md in this same PR now mandates the new path, so the change makes the standard redeploy strictly more destructive with no check and no warning. The transcode is requeued by the dispatcher's stale threshold (attempt++ toward `ARM_TRANSCODE_MAX_ATTEMPTS`); the rip stays `RIPPING` until a backend restart runs `sweep_in_flight_jobs` (`main.py:194-200`) — and with C1 the backend may not restart, so the job is stuck with no ripper.

**Repro / evidence.** Diff hunk at head:
```
if [[ "${ACTION}" == "up" ]]; then
    remove_spawned_containers        # no running/active check
    echo "==> building + starting the stack"
    compose up -d --build
```

**Tip check.** Fixed by #85 (`feat/no-transcode-mode`, which carries the setup-dev hardening commits) in `34260a69` "harden setup-dev.sh up (build-first, DB backup, ripper guard, health wait)" + `d67096f2` (guards ACTIVE work only, idle rippers still replaced) + `3ecd0e58` (dd detection, bounded exec waits): tip `devtools/setup-dev.sh:483-519` `guard_running_spawned` refuses with exit 1 unless `--force` when a running `arm.task_id` container exists or a running ripper has makemkvcon/abcde/dd. `lowest_pr.sh 34260a69` -> #85 (the reviewer's `git branch -r --contains` reading of #89 was an alphabetical-listing artefact). Recommend: **move down** — #83 alone ships a mandated command that destroys in-flight work.

**Suggested fix location.** feat/setup-dev-stack-lifecycle — bring `guard_running_spawned` + `--force` down with the build-first ordering.
**Hoisted.** 2026-10-03: `44d6f214a` on `feat/setup-dev-stack-lifecycle`. The copy in the later PR becomes empty on restack.

**Verification.** Code trace; untested-needs-hardware for the live effect: start a rip (or `bash devtools/iso-smoke.sh` mid-transcode), run `bash devtools/setup-dev.sh up`, observe the ripper/transcoder container is removed and the job status.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/175

### D-054  S3  hoisted  devtools  origin #83

**Title.** `setup-dev.sh up` removes every ripper container but nothing respawns them when compose leaves the backend running.

**Where.** `devtools/setup-dev.sh:399-402` at `42cf7ea7` (introduced in `9e5828c9`); respawn is startup-only at `services/backend/arm_backend/main.py:252` (`reconcile_enrolled_rippers` is called only from `lifespan`; `grep -rn reconcile_enrolled_rippers services/backend` shows no other caller).

**What.** `up` runs `remove_spawned_containers` (docker rm -f of all `arm.drive_id` containers) and then `compose up -d --build`. The backend only reconciles enrolled drives → ripper containers in its lifespan hook. When the backend image/config is unchanged (UI-only change, or simply re-running `up`), compose does not recreate `arm-backend`, so every enrolled drive is left with no ripper until someone restarts the backend or re-enrolls. Same outcome if the build fails after the removal (removal happens before the build at head).

**Repro / evidence.**

```
bash devtools/setup-dev.sh up          # stack running, drive enrolled -> arm-ripper-<serial> exists
bash devtools/setup-dev.sh up          # no code change: "==> removing backend-spawned ripper/transcoder containers"
docker ps --filter label=arm.drive_id  # empty; `docker compose ps arm-backend` shows the SAME container, never restarted
```

**Tip check.** Fixed by #94 (`chore/ui-neu-ux-polish`) in `4f80aee3` "setup-dev up respawns rippers when the backend keeps running": records `backend_started_at` before `up`, `compose restart arm-backend` when unchanged (`respawn_rippers_if_needed`), and `34260a69` (#89) moved the removal AFTER the build. `git branch -r --contains 4f80aee3` includes `origin/chore/ui-neu-ux-polish` → not a straggler. Recommend: **move down** — #83 merged alone makes the documented "always use this" path strand enrolled drives on every no-op redeploy.

**Suggested fix location.** feat/setup-dev-stack-lifecycle — cherry-pick the `backend_started_at`/`respawn_rippers_if_needed` block and the build-before-remove ordering.
**Hoisted.** 2026-10-03: `44d6f214a` on `feat/setup-dev-stack-lifecycle`. The copy in the later PR becomes empty on restack.

**Verification.** Code trace at head (main.py:240-255 is the only reconcile call site; `compose up -d --build` does not recreate an unchanged service). untested-needs-hardware for the live run: `bash devtools/setup-dev.sh up` twice on a box with one enrolled drive, then `docker ps --filter label=arm.drive_id`.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/176

### D-055  S3  hoisted  devtools  origin #83

**Title.** `arm-data:/data` named volume is created root-owned, so the EACCES this commit claims to fix persists.

**Where.** `docker-compose.yml.example:109-113,175-176` at `42cf7ea7` (commit 42cf7ea7 "persist /data on a named volume in the template"); `services/backend/Dockerfile` at the same sha has no `/data` directory; `services/_common/docker-entrypoint.sh:299` guards only `/logs /raw /media` and never chowns.

**What.** Docker seeds a new named volume from the image's content at the mount path; when the image has no `/data`, the daemon creates the mountpoint root:root 0755 and the volume stays root-owned. The backend drops to PUID via gosu and writes `/data/cache/thediscdb` and `/data/cache/images` (`config.py:42,45`), so every refresh still fails with `[Errno 13]`; `_thediscdb_refresh_loop` swallows it (`main.py:139-140` "never kill the loop") and logs a warning each cycle. The persistence goal of the commit is achieved, the stated EACCES fix is not; nothing fails fast because `/data` is not in the entrypoint guard list.

**Repro / evidence.**

```
grep -n '/data' services/backend/Dockerfile            # (nothing) at 42cf7ea7
sed -n 299p services/_common/docker-entrypoint.sh      # for d in /logs /raw /media; do   -> /data not guarded
docker volume create t && docker run --rm -v t:/data python:3.14-slim-bookworm stat -c '%u:%g %a' /data   # 0:0 755
```

**Tip check.** Fixed by #85 (`feat/no-transcode-mode`, which carries the infra commits) in `b399d010` "bake /data ownership so fresh arm-data volumes are writable" (tip `services/backend/Dockerfile:53-55` `mkdir -p /data/cache/images /data/cache/thediscdb /data/themes && chown -R 1000:1000 /data && chmod -R 2775 /data`), `baa87ca9` (entrypoint guard now `for d in /logs /raw /media /data`, tip `docker-entrypoint.sh:299`), and `ff4578d5`/`60975f5d` (one-shot `arm-data-init` service re-owns the volume to PUID:PGID for non-1000 ids). `lowest_pr.sh b399d010` -> #85 (not #89 as first reported). Recommend: **move down** — at minimum `b399d010` belongs with the volume it makes usable; #83 alone adds a volume the backend cannot write.

**Suggested fix location.** feat/setup-dev-stack-lifecycle — Dockerfile `/data` seeding + entrypoint `/data` guard; `arm-data-init` can stay in #89.
**Hoisted.** 2026-10-03: `ff3f0db17` on `feat/setup-dev-stack-lifecycle` plus `16a8eafef` (entrypoint /data guard). The copy in the later PR becomes empty on restack.

**Verification.** Code inspection of Dockerfile/entrypoint at head + docker volume-seeding semantics. untested-needs-hardware for the end-to-end: `bash devtools/setup-dev.sh up && docker compose logs arm-backend | grep -i 'thediscdb.*Errno 13'`.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/177

### D-056  S4  open  docs  origin #83

**Title.** Contributor docs still tell people to use bare `docker compose up -d`, which this PR's CLAUDE.md says never to do.

**Where.** `CONTRIBUTING.md:65-66` and `arm_wiki/Contribute.md:32-33,43` at `42cf7ea7`; the rule they contradict is added at `CLAUDE.md:60-66` in `9e5828c9`.

**What.** CLAUDE.md now says "Always spin the stack up/down through `setup-dev.sh` — a bare `docker compose down` strands the backend-spawned ... containers", and the PR's `up` depends on being the entry point (it removes stale rippers before rebuild). CONTRIBUTING.md and the wiki Contribute page, the two documents a contributor actually reads, still give `bash devtools/setup-dev.sh` then `docker compose up -d` / `docker compose up -d --build --force-recreate`. The PR updated only CLAUDE.md.

**Repro / evidence.**

```
CONTRIBUTING.md:65:bash devtools/setup-dev.sh     # one-shot, idempotent dev-env setup
CONTRIBUTING.md:66:docker compose up -d           # bring up the stack
arm_wiki/Contribute.md:33:docker compose up -d --build      # build images from your working tree and start
```

**Tip check.** Still present at `71129cd9`: `CONTRIBUTING.md:65-66` (identical text) and `docs/developers/contributing/Contribute.md:32-33,43` (the wiki page moved by `a1b0c7c3`, same instructions). Not fixed by any PR or straggler.

**Suggested fix location.** feat/setup-dev-stack-lifecycle — replace both snippets with `bash devtools/setup-dev.sh up` / `down` alongside the CLAUDE.md change.

**Verification.** grep at head and at tip (above).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/178

### D-057  S3  untested-needs-hardware  backend  origin #84

**Title.** Removing the boot-time truncate makes orphaned BUSY GPU rows permanent: `cancel_running`'s docker-stop path (and deleting a spawned-but-unclaimed task) deletes the task row without releasing its GPU.

**Where.** `services/backend/arm_backend/main.py:87-105` (`_refresh_gpu_inventory`, early `return` at :105 when rows exist) and `services/backend/arm_backend/transcode_dispatcher.py:746-804` (`cancel_running`: `container.stop(timeout=5)` at :789 ... `await db.delete(row)` at :804, no `release_gpu_for_task`) at `ed087cf2`.

**What.** A GPU claim is `gpus.status=BUSY` + `claimed_by_task_id`, released only by the transcoder's `/complete` / `/fail` call or by `sweep_stale_claims` (which only looks at IN_PROGRESS tasks). When a cancel falls through to `docker stop` (the transcoder has no SIGTERM handler, so no `/fail` is sent), or an operator deletes a task that has been spawned but has not yet called `/claim` (still QUEUED), the task row is deleted; the FK `ondelete="SET NULL"` nulls `claimed_by_task_id` but `status` stays `busy`. Before this PR every backend boot truncated and re-filled `gpus` from `ARM_GPUS`, which healed this. With seed-once the row is BUSY forever: NULL-hw_preference presets queue forever ("waiting for GPU"), `any` presets silently go CPU, and `/api/transcodes/stats` shows 0/N available. The DELETE 409 guard does not catch it (claimed_by_task_id is NULL), so the only recovery is delete-row + restart, or a manual UPDATE.

**Repro / evidence.**

```
# packages/arm_common/arm_common/models/gpu.py:32  ForeignKey("transcode_tasks.id", ondelete="SET NULL")  — status untouched
# transcode_dispatcher.py cancel_running: emit task.cancel -> sleep 10 -> container.stop(timeout=5) -> db.delete(row); no release_gpu_for_task(db, task_id)
# services/transcode/arm_transcode: no add_signal_handler / SIGTERM handling -> docker stop never produces a /fail call
```
Drill (needs a GPU host): start a GPU transcode, `docker pause` the transcoder so it ignores `task.cancel`, DELETE the task via the UI; after the 10 s grace, `SELECT status, claimed_by_task_id FROM gpus` shows `busy | NULL`; restart the backend — it stays `busy` (pre-PR it reset to `available`).

**Tip check.** Still present at `71129cd9`: `transcode_dispatcher.py` cancel_running (`container.stop(timeout=5)` at ~1256, `await db.delete(row)` at ~1271, no release in between; `git log -S'release_gpu_for_task' origin/feat/gpu-inventory-alignment..origin/integration/all-prs-3 -- transcode_dispatcher.py` is empty); `main.py:111-114` still returns early when rows exist, and no boot-time "BUSY with NULL claim" reconcile exists anywhere on the tip (`grep claimed_by_task_id` across arm_backend at tip: only release/claim sites).

**Suggested fix location.** feat/gpu-inventory-alignment — the PR that removed the truncate should add `await release_gpu_for_task(db, task_id)` before `db.delete(row)` in `cancel_running` and in the synchronous delete path of `routers/transcodes.py:delete_transcode`, plus a boot-time reconcile in `_refresh_gpu_inventory` (`status=BUSY AND claimed_by_task_id IS NULL` -> AVAILABLE, and BUSY rows whose task is terminal/missing).

**Verification.** Code trace (FK + both delete paths + absence of signal handling in arm_transcode); untested-needs-hardware for the end-to-end drill above.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/179

### D-058  S3  open  ui-neu  origin #84

**Title.** Transcoder page per-device GPU rows are fetched once on mount and never refreshed, so their busy/available state contradicts the polled summary count.

**Where.** `services/ui-neu/frontend/src/routes/transcoder/+page.svelte:125-139` (`gpuRows` state at :125, `loadGpus()` called only from `onMount` at :139) at `ed087cf2`.

**What.** `stats`/`workers` stores poll, so "GPUs: 0/1 available" updates when the dispatcher claims a GPU, but `gpuRows` keeps the snapshot from page load and still renders a green dot + "available" (or keeps "busy" after the task finishes). The PR body sells these as "live status per GPU"; they are static until navigation.

**Repro / evidence.** Open /transcoder with an idle GPU, start a GPU transcode; the summary flips to 0/1 while the row below stays `available`. (No poll or `wsClient.subscribe('transcode.events', ...)` in the page; the Settings GpusCard on the tip did get a WS-driven reload, the transcoder page did not.)

**Tip check.** Still present at `71129cd9`: `routes/transcoder/+page.svelte:132-148` (`loadGpus()` only inside `onMount`; `grep -n "subscribe\|loadGpus"` shows no other caller).

**Suggested fix location.** feat/gpu-inventory-alignment — reload `gpuRows` on the same cadence as `stats` (or on `transcode.events`), as the tip's GpusCard does.

**Verification.** Code read of head and tip; vitest test only asserts the mounted snapshot.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/180

### D-059  S3  open  ui-neu  origin #84

**Title.** GpusCard never shows the "in use by a running transcode" message on a 409: it string-matches `'409'` in a message the API client has already replaced with the server `detail`.

**Where.** `services/ui-neu/frontend/src/lib/components/settings/GpusCard.svelte:66-70` (`msg.includes('409')` at :68) at `ed087cf2`; client behaviour at `services/ui-neu/frontend/src/lib/api/client.ts:63-73` (`message = detail` at :68, `throw new ApiError(res.status, message, body)` at :73).

**What.** `handle()` throws `ApiError(res.status, message, body)` where `message = detail` whenever `detail` is a string; the backend's 409 detail is `"gpu is in use by a running transcode"`, so `e.message.includes('409')` is false and the operator sees the generic "Deleting the GPU failed." The test `a 409 delete shows the in-use message` passes only because it rejects with `new Error('HTTP 409')` — a shape the real client never produces (a test asserting on its own mock).

**Repro / evidence.**

```
// GpusCard.svelte
error = msg.includes('409') ? 'That GPU is in use by a running transcode. ...' : 'Deleting the GPU failed.';
// client.ts handle(): if (typeof detail === 'string') message = detail;  throw new ApiError(res.status, message, body);
// GpusCard.test.ts: mockDeleteGpu.mockRejectedValue(new Error('HTTP 409'));
```

**Tip check.** Still present at `71129cd9`: `GpusCard.svelte:142` (`error = msg.includes('409')`), `client.ts:80/92` unchanged (`message = detail; throw new ApiError(res.status, message, body)`).

**Suggested fix location.** feat/gpu-inventory-alignment — `e instanceof ApiError && e.status === 409`, and make the test reject with an `ApiError(409, 'gpu is in use by a running transcode', ...)`.

**Verification.** Code read of client + card + test at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/181

### D-060  S3  open  backend  origin #84

**Title.** Fresh install: the config seeder creates the singleton and returns before the `max_parallel_transcodes` backfill, so the column stays NULL until the second boot; meanwhile `/api/config` reports `1` while the dispatcher uses the env value.

**Where.** `services/backend/arm_backend/seeders.py:110-123` (`if existing is None: session.add(Config(...)); await session.flush(); return`) and `:135-140` (backfill only on the `existing` branch); view fallback at `services/backend/arm_backend/routers/config.py:73` (`... else 1`) at `ed087cf2`.

**What.** `Config(...)` is constructed without `max_parallel_transcodes`, so a first boot leaves it NULL. `max_parallel_transcodes(db, default=env)` falls back to `MAX_PARALLEL_TRANSCODES` (say 3), but `_to_view` hardcodes `1` for NULL, so Settings > Transcoding shows "1" while 3 containers run — UI state that lies about backend state for the whole first boot. It self-corrects on the next restart (the `existing` branch backfills), so there is a workaround.

**Repro / evidence.** `tests/e2e` app_client boots a fresh SQLite DB: after lifespan, `SELECT max_parallel_transcodes FROM config` is NULL; `GET /api/config` -> `max_parallel_transcodes: 1` regardless of `MAX_PARALLEL_TRANSCODES`.

**Tip check.** Still present at `71129cd9`: `seeders.py:108-122` creates the row and `return`s before the backfill at `:134-137`; `routers/config.py:90` still `else 1`.

**Suggested fix location.** feat/gpu-inventory-alignment — pass `max_parallel_transcodes=settings.MAX_PARALLEL_TRANSCODES` in the `Config(...)` constructor (or move the backfill above the early return), and make `_to_view` fall back to the same env value the dispatcher uses.

**Verification.** Code trace of seeder control flow; not run against a fresh DB.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/182

### D-061  S4  open  backend  origin #84

**Title.** `/api/transcodes/stats.gpus_available` counts disabled GPUs as available.

**Where.** `services/backend/arm_backend/routers/transcodes.py:94-95` (`gpus_available = len([g for g in gpus if g.status == GpuStatus.AVAILABLE])`) at `ed087cf2`.

**What.** The PR adds `enabled` and makes the dispatcher skip disabled rows, but the summary the Transcoder page renders ("GPUs: 2/2 available") still counts a disabled device as available even though it will never be claimed. The per-device rows directly below say "disabled", so the page contradicts itself.

**Repro / evidence.** PATCH `/api/gpus/{id}` `{"enabled": false}` then GET `/api/transcodes/stats` -> `gpus_available` unchanged.

**Tip check.** Still present at `71129cd9`: `routers/transcodes.py:95` (`g.status == GpuStatus.AVAILABLE`, no `g.enabled`).

**Suggested fix location.** feat/gpu-inventory-alignment — `g.enabled and g.status == GpuStatus.AVAILABLE` (and decide whether `gpus_total` should exclude disabled rows).

**Verification.** Code read head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/183

### D-062  S4  open  ui-neu  origin #84

**Title.** "Manage GPUs in Settings" links to `/settings`, which opens the Metadata tab; the GPUs card lives under `#transcoding`.

**Where.** `services/ui-neu/frontend/src/routes/transcoder/+page.svelte:241` (`<a href="/settings" ...>`) at `ed087cf2`; tab routing at `routes/settings/+page.svelte:84-98` (`parseHash()` falls back to `'Metadata'`).

**What.** Settings tabs are hash-routed (`screenTabs` includes `'transcoding'`), so the link should be `/settings#transcoding`. As written the operator lands on Metadata and has to find the Transcoding tab themselves.

**Repro / evidence.** Click the link on /transcoder; URL `/settings`, active tab Metadata, no GpusCard visible.

**Tip check.** Still present at `71129cd9`: `routes/transcoder/+page.svelte:284` (`href="/settings"`).

**Suggested fix location.** feat/gpu-inventory-alignment.

**Verification.** Code read of both routes.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/184

### D-063  S4  open  ui-neu  origin #84

**Title.** GPU inventory row markup (status-dot + vendor badge + mono device path + state label) is duplicated inline in GpusCard and the Transcoder page instead of a shared component.

**Where.** `services/ui-neu/frontend/src/lib/components/settings/GpusCard.svelte:97-105` and `services/ui-neu/frontend/src/routes/transcoder/+page.svelte:224-237` at `ed087cf2`.

**What.** `feedback_standard_ui_patterns.md`: when a pattern appears in two places, extract it under `lib/components/`. The same row (dot `data-status` ternary, `badge` vendor, `title`d device path, disabled/available/busy label) and its CSS (`.gpus-card-device` / `.transcoder-page-gpu-device`) are written twice with slightly different label logic (`statusLabel()` vs an inline `{#if}` chain that can print raw `g.status`).

**Repro / evidence.** Diff hunks above; no `GpuRow`/`GpuInventoryRow` component exists.

**Tip check.** Still present at `71129cd9`: both sites still inline (`git ls-tree -r origin/integration/all-prs-3 services/ui-neu/frontend/src/lib/components | grep -i gpu` -> only GpusCard.svelte + its test; tip `transcoder/+page.svelte:262-283` is the inline row).

**Suggested fix location.** feat/gpu-inventory-alignment — extract a `GpuInventoryRow` component used by both.

**Verification.** Code read head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/185

### D-064  S4  open  devtools  origin #84

**Title.** install.sh's `.env` template and docker-compose.yml.example still tell operators to "Re-run install.sh after a GPU/driver change" — the backend now ignores `ARM_GPUS` once the table is populated.

**Where.** `install.sh:1178-1181` (".env exists; preserving secrets, re-deriving ... ARM_GPUS" at `:1082` rewrites the value; template comment "The GPU-free backend reads this to fill the gpus table ... Re-run install.sh after a GPU/driver change") and `docker-compose.yml.example:78-81` at `ed087cf2`.

**What.** With seed-once semantics a re-run installer (or a driver upgrade that now passes the `ARM_NVENC_MIN_DRIVER` gate) rewrites `ARM_GPUS` to no effect; the operator must also delete every row in Settings > GPUs and restart, which only the UI card says. The installer's "advertising NVENC" log (`install.sh:493`) is misleading on an upgraded host. The ARM_NVENC_MIN_DRIVER lockstep itself is intact (install.sh:477 and setup-dev.sh:97 both 530; Dockerfile NVCODEC_VERSION 12.1.14.0).

**Repro / evidence.** `grep -n "Re-run install.sh after a GPU" install.sh`; the PR touches neither install.sh nor setup-dev.sh nor the compose example.

**Tip check.** Still present at `71129cd9`: `install.sh:1179-1181` (same comment, `git show origin/integration/all-prs-3:install.sh | grep -n -i "re-seed\|Settings > GPUs"` finds nothing).

**Suggested fix location.** feat/gpu-inventory-alignment — update the template/compose comments and have the installer's upgrade path print the re-seed instruction when it rewrites `ARM_GPUS`.

**Verification.** grep at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/186

### D-065  S3  open  backend  origin #85

**Title.** Transcode re-enable PATCH 500s when a per-job re-drain fails: `job.id` read after `rollback()` (MissingGreenlet).

**Where.** `services/backend/arm_backend/auto_session.py:795` at `df50078e` (introduced for the re-drain reuse in `c5f687f8`; caller `services/backend/arm_backend/routers/config.py:229`).

**What.** `PATCH /api/config {"transcode_enabled": true}` commits the toggle, then `_redrain_parked_applications` calls `drain_parked_applications_after_rip(session, job, hub, trigger="transcode re-enable")` per parked job. If `fan_out_waiting_identify_applications` or its `commit()` raises, the except block does `await db.rollback()` and then logs `job.id`. A real `AsyncSession.rollback()` expires every identity-map instance (`expire_on_commit=False` does not apply to rollback), so the PK read triggers a sync lazy load inside async code and raises `sqlalchemy.exc.MissingGreenlet` out of the except block. The PATCH returns 500 even though the toggle is already committed, so the operator sees a failure for a save that succeeded; the remaining parked jobs in the loop are never re-drained. The same read-after-rollback pre-exists in `after_rip`, but this PR adds a second caller (a user-facing HTTP route) and a new `trigger` argument to that exact line.

**Repro / evidence.**

```python
# services/backend/arm_backend/auto_session.py:792-796
    except Exception:  # noqa: BLE001 - hook must never break rip-complete
        await db.rollback()
        logger.exception("%s: draining parked session_applications failed job_id=%s", trigger, job.id)
```
`services/backend/tests/test_config_transcode_enabled.py::test_reenable_redrain_failure_never_fails_the_patch` only covers the *listing* failure before the loop; the per-job failure path is covered by no test, and the FakeSession's no-op `rollback()` could not surface the expiry anyway (the PR's own `tests/e2e/test_dispatcher_real_session.py` exists precisely because of this class of bug).

**Tip check.** Still present at `71129cd9`: `services/backend/arm_backend/auto_session.py:847` (`logger.exception("%s: draining parked session_applications failed job_id=%s", trigger, job.id)` after `await db.rollback()`), caller at `routers/config.py:269`.

**Suggested fix location.** feat/no-transcode-mode — capture `job_id = job.id` before the `try`, log the local, and wrap the per-job loop in `_redrain_parked_applications` in its own try/except so one job cannot abort the rest; the PR body already proposes exactly this.

**Verification.** Code trace + SQLAlchemy semantics (rollback expires all); no automated repro because the fast suite uses FakeSession. A real-session regression test belongs next to `tests/e2e/test_dispatcher_real_session.py`.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/187

### D-066  S3  untested-needs-hardware  backend  origin #85

**Title.** Cancelling an in-process passthrough task does not stop the copy: the file still lands in `/media` and the raw source is unlinked after the user deleted the task.

**Where.** `services/backend/arm_backend/passthrough_executor.py:181` and `services/backend/arm_backend/transcode_dispatcher.py:924` at `df50078e` (introduced in `ee0d9d2d`/`b7240a1f`).

**What.** `DELETE /api/transcodes/{id}` -> `cancel_running` emits `task.cancel`, sleeps 10s, then force-stops the *container* (`self._docker.containers.list(...)`) and deletes the row. An in-process passthrough has no container and ignores the WS cancel: `asyncio.to_thread(transcode_none, ...)` keeps copying (cross-mount copies of multi-GB rips take minutes), `transcode_none` then `unlink`s the `/raw` source, and the executor merely logs "deleted mid-move; skipping terminal update". Net effect: the user cancelled, the row is gone, yet the output appears in the library at the resolved path and the raw file is consumed — the opposite of the container path, where the stop kills the copy. Memory `project_no_transcode_mode.md` lists this as follow-up 3, but the PR body's "mirrors the container lifecycle exactly" does not.

**Repro / evidence.**

```python
# passthrough_executor.py:179-186 — no cancellation check, no event to abort the thread
            final = Path(settings.MEDIA_ROOT) / task_output_path
            try:
                size = await asyncio.to_thread(transcode_none, Path(track_output_path), final)
# transcode_dispatcher.py:921-924 — only a container can be stopped
        if still_running and self._docker is not None:
            survivors = self._docker.containers.list(filters={"label": f"{_DOCKER_LABEL_KEY}={task_id}"})
```

**Tip check.** Still present at `71129cd9`: `passthrough_executor.py:181` (`await asyncio.to_thread(transcode_none, ...)`, no cancel path), `transcode_dispatcher.py:1247` (`if still_running and self._docker is not None:`); `IN_PROCESS_CLAIMANT` is never consulted by `cancel_running` on the tip.

**Suggested fix location.** feat/no-transcode-mode — either refuse DELETE for `claimed_by == IN_PROCESS_CLAIMANT` while IN_PROGRESS (409 "passthrough move in flight") or copy to `<final>.arm-inprogress` and check a per-task cancel flag before the final rename/unlink so a cancel can discard the partial.

**Verification.** Code trace; untested-needs-hardware for timing (needs a cross-mount `/raw`->`/media` copy long enough to cancel: `bash devtools/iso-smoke.sh` with a passthrough session, `DELETE /api/transcodes/{id}` during the copy, then inspect `/media` and `/raw`).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/188

### D-067  S3  open  ui-neu  origin #85

**Title.** Ripper-only (`ARM_TRANSCODE_CAPABLE=false`) hides the Transcoder page and nav while the backend silently holds previously queued encode tasks forever.

**Where.** `services/ui-neu/frontend/src/routes/transcoder/+page.svelte:142` and `:166` at `df50078e` (commit `b40b0279`/`0a1c663a`); backend hold at `services/backend/arm_backend/transcode_dispatcher.py:519` and `transcode_apply.py:transcode_enabled_now`.

**What.** A box that had encode tasks QUEUED (or a container that dies and is swept back to QUEUED) and is then redeployed with `setup-dev.sh --ripper-only` keeps those rows: `transcode_enabled_now` returns False when not capable, `spawn_pending` counts them as `held_encode` and only logs at DEBUG, and nothing fails or expires them. The UI, keyed on capability, removes `/transcoder` from the nav and renders "Transcoding is not available on this deployment (ripper-only install)" for the deep link without fetching tasks, so the held queue, its session applications (stuck RUNNING/QUEUED) and their jobs' transcode state are invisible — the page says there is nothing to transcode while the backend holds work. The capable-but-disabled case deliberately keeps the queue visible with a banner ("drain semantics need the held queue visible"); the not-capable case drops that.

**Repro / evidence.**

```svelte
<!-- +page.svelte:142 --> if (!get(transcoderEnabled)) return;   // no stats/jobs fetch
<!-- +page.svelte:166 --> {#if !$transcoderEnabled} ... Transcoding is not available on this deployment (ripper-only install).
```
```python
# transcode_dispatcher.py:516-521
                if not enabled:
                    held_encode += 1
                    continue
                if self._docker is None or not self.host_paths_set():
                    held_encode += 1
                    continue
```

**Tip check.** Still present at `71129cd9`: `routes/transcoder/+page.svelte:173` (`{#if !$transcoderEnabled}`) / `:180` ("Transcoding is not available on this deployment (ripper-only install)"); dispatcher hold at `transcode_dispatcher.py:629-632`.

**Suggested fix location.** feat/no-transcode-mode — when not capable, still fetch and render the queue (or at least a count of held encode tasks with a "re-run setup without --ripper-only to resume or delete these" hint), or have `/api/system/diagnostics` report held encode rows instead of the unconditional `ok` added in `routers/system.py:155`.

**Verification.** Code trace of both sides; the ripper-only UI branch is unit-tested only for "fetches nothing" (`transcoder-page.test.ts` "renders a full-page empty state and fetches no task data when not capable").

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/189

### D-068  S4  open  backend  origin #85

**Title.** `GET /api/config` reports `transcode_enabled: true` on a ripper-only deployment where encode is effectively disabled.

**Where.** `services/backend/arm_backend/routers/config.py:84` at `df50078e` (commit `6bdd95f5`).

**What.** `_to_view` returns the raw column (`cfg.transcode_enabled is not False`), while every enforcement point (`transcode_enabled_now`, apply gates, dispatcher) treats not-capable as disabled. So the wire contract says `{transcode_enabled: true, transcode_capable: false}` and the settings UI has to special-case it ("Always rendered off: on a ripper-only box the backend column still defaults to true" — `routes/settings/+page.svelte` ripper-only branch hard-codes `checked={false}`). Any other API consumer (scripts, the Vue UI still present at this head, future first-run setup) reading `transcode_enabled` gets a value that contradicts behaviour.

**Repro / evidence.**

```python
# routers/config.py:83-85
        # None-coerce covers rows/fixtures predating the column (NULL = enabled).
        transcode_enabled=cfg.transcode_enabled is not False,
        transcode_capable=effective_transcode_capable(settings),
```

**Tip check.** Still present at `71129cd9`: `routers/config.py:93-94` (identical two lines).

**Suggested fix location.** feat/no-transcode-mode — `transcode_enabled=capable and cfg.transcode_enabled is not False` (and drop the hard-coded `checked={false}` in the settings page), keeping the PATCH 422 as is.

**Verification.** Code read; `test_config_transcode_capable.py` asserts the view only under the default capable settings.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/190

### D-069  S3  hoisted  ui-neu  origin #87

**Title.** GpusCard subscribes to `gpu.probed` without starting the WebSocket and shows no in-progress state after Re-probe, so on a directly loaded Settings page the row stays "Never probed"/stale forever.

**Where.** `services/ui-neu/frontend/src/lib/components/settings/GpusCard.svelte:109-115` at `e5bd1493` (introduced in `0259bd56`).

**What.** `onMount` calls `load()` and `wsClient.subscribe('transcode.events', ...)` but never `wsClient.start()`. At this head the only `start()` callers are `rips.svelte.ts`, `ripperEvents.svelte.ts` and `encoders.svelte.ts#followProbes` (the latter only runs on `encodersStore.refresh()`, which GpusCard calls only after a toggle/delete). The Settings route imports none of those stores, so a user who loads `/settings` directly, clicks Re-probe (202 returned, `pending` cleared immediately) sees no "probing" indicator, the row keeps showing "Never probed" / the old chips, and the `gpu.probed` event that would refresh it is never delivered; a second click yields a 409 "gpu probe already running" alert. The card should start the socket and show a per-row in-progress state until `gpu.probed` arrives.

**Repro / evidence.**

```
grep -rn "wsClient.start()" services/ui-neu/frontend/src --include=*.svelte --include=*.ts | grep -v __tests__
# -> only stores/rips.svelte.ts, stores/ripperEvents.svelte.ts, stores/encoders.svelte.ts
grep -n "import" services/ui-neu/frontend/src/routes/settings/+page.svelte   # none of those stores
```

**Tip check.** Fixed by #102 (`feat/first-run-setup`) in `81ab0281` "feat(ui): GPU card encoder chips, probe progress, CPU empty state" (adds `wsClient.start()` in `onMount` with the comment "Start the socket ourselves: on the setup walkthrough no other store has", plus a per-row `StatusStrip` "Testing encoders..." with a 2-minute timeout keyed on `gpu.probed.payload.gpu_id`). The same patch also sits on the tip as `9ff1aa08` (patch-id identical). Recommend: move down the one-line `wsClient.start()` into #87 (without it the Re-probe button this PR adds does not visibly do anything on a fresh Settings load); leave the progress-strip part in #102 (it depends on `StatusStrip`/`Glyph` names that arrive later).

**Suggested fix location.** feat/encoder-first-presets — the Re-probe button and the subscription are both introduced here.
**Hoisted.** 2026-10-03: `d276c86b4` on `feat/encoder-first-presets`. The copy in the later PR becomes empty on restack.

**Verification.** Code-read of head and tip (`git show origin/integration/all-prs-3:...GpusCard.svelte`); vitest passes at head because tests inject events directly. Browser check: load `https://localhost:8081/settings` cold (not via the dashboard), click Re-probe, observe the row never updates.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/191

### D-070  S3  untested-needs-hardware  backend  origin #87

**Title.** An infrastructure failure during a re-probe (container could not start, docker wait error, 120 s timeout) is written as `encoder_kinds=[]`, wiping a previously verified device so queued vendor-pinned tasks terminally fail and `any_*` work silently drops to CPU.

**Where.** `services/backend/arm_backend/gpu_probe_runner.py:386,392-393` (returns `[]` for infra errors) and `:433` (`gpu.encoder_kinds = verified` unconditionally) at `e5bd1493` (introduced in `5d5b31f6`).

**What.** `_run_container` returns `([], error)` for every failure mode, including ones that say nothing about the device's encoders (a dead ssh transport to `ARM_TRANSCODE_DOCKER_HOST`, a transient daemon error, a slow host tripping `PROBE_TIMEOUT_S`). `_write` then replaces the verified list with `[]`. Unlike the spawn path, the probe runner does not use the dispatcher's transport-death rebuild (`_is_transport_death` / `_docker_factory`), so on a remote host whose connection dropped, a "Re-probe"/"Re-probe all" click or the boot pass turns every verified device into "Verified nothing". On the next tick `_claim_gpu_for_task` fails each queued `qsv_*`/`nvenc_*`/`vaapi_*` task with "no enabled device has verified ..." (retryable only by hand) and `any_*` tasks fall back to CPU. The previously verified list should be kept (write `probe_error` only) when the probe did not actually run, or the error should be classified separately from "verified nothing". The PR body discloses this as behavior change 8; recorded because the consequence (terminal task failure from a transient error) has only a manual workaround.

**Repro / evidence.**

```
# gpu_probe_runner.py:380-393 — every except branch returns [] as the verified list;
# _write (:433) stores it; _claim_gpu_for_task then takes the "fail" branch for pinned encoders.
uv run pytest -q -k "test_gpu_probe_runner and (timeout or could_not_start)"
```

**Tip check.** Still present at `71129cd9`: `services/backend/arm_backend/gpu_probe_runner.py:386,392-393,433` (file byte-identical to head: `git diff --quiet origin/feat/encoder-first-presets origin/integration/all-prs-3 -- services/backend/arm_backend/gpu_probe_runner.py`).

**Suggested fix location.** feat/encoder-first-presets — the runner is new here.

**Verification.** Code-read + existing runner tests; the end-to-end consequence is untested-needs-hardware: on a GPU host with a queued `qsv_h265` task, stop the remote docker daemon (or `docker pause` it) and click Re-probe; expect the row to flip to "Verified nothing" and the queued task to FAILED on the next tick.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/192

### D-071  S3  open  transcode  origin #87

**Title.** A `vaapi_*` (or AMD-resolved `any_*`) preset with `container=webm` passes preset validation but every task fails at run time because the ffmpeg VAAPI engine only muxes MKV/MP4.

**Where.** `services/transcode/arm_transcode/engines/ffmpeg_vaapi.py:28,41-43` (`FFMPEG_MUXER` has only MKV/MP4, `raise ValueError`) at `e5bd1493` (introduced `1e87bc6d`); `services/backend/arm_backend/routers/transcode_presets.py:20-30` `_validate_encoder` checks only encoder-vs-tool, not container; `services/ui-neu/frontend/src/lib/components/TranscodePresetForm.svelte:231` offers WebM for every encoder.

**What.** `vaapi_av1` + WebM (and `any_av1` + WebM once the claim lands on an AMD row) is accepted by POST/PATCH `/api/transcode-presets` and by the form, applies cleanly, and then `main._run_encoder` -> `build_command` raises `ValueError("ffmpeg_vaapi does not support container webm")` on each attempt, failing the task with a message the user can only fix by editing the preset. The combination should be refused at create/update (422) and greyed in the picker, or the engine should map WEBM to the `webm` muxer for AV1.

**Repro / evidence.**

```
uv run pytest -q -k test_unsupported_container_rejected   # pins the ValueError (services/transcode/tests/test_ffmpeg_vaapi.py:92)
# while POST /api/transcode-presets {"tool":"handbrake","container":"webm","encoder":"vaapi_av1",...} returns 201
```

**Tip check.** Still present at `71129cd9`: `services/transcode/arm_transcode/engines/ffmpeg_vaapi.py:28,41-43` (identical), `routers/transcode_presets.py:20` `_validate_encoder` still container-blind (identical), `TranscodePresetForm.svelte:207` still offers WebM unconditionally.

**Suggested fix location.** feat/encoder-first-presets — the engine, the validator and the picker are all introduced here.

**Verification.** Code-read + the engine unit test; the live failure path is untested-needs-hardware (AMD VAAPI device).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/193

### D-072  S3  open  devtools  origin #87

**Title.** install.sh-generated compose does not forward `ARM_TRANSCODE_IMAGE_QSV` / `_VAAPI` / `_NVENC` to the backend, so the PR's operator instruction for air-gapped/private-registry installs has no effect.

**Where.** `install.sh:1380-1391` (backend `environment:` heredoc lists `ARM_TRANSCODE_IMAGE` ... `ARM_TRANSCODE_PGID`, no `_QSV/_VAAPI/_NVENC`, no `env_file`) at `e5bd1493`; claim at `arm_wiki/Hardware-Transcoding.md:174-178` (`77c2a94c`) and PR body "Operator actions".

**What.** `Settings.ARM_TRANSCODE_IMAGE_QSV/_VAAPI/_NVENC` (config.py, `2f9747c9`) are read from the backend container's environment. The dev `docker-compose.yml.example` was updated to pass them, but install.sh's generated compose was not (PR body: "install.sh itself is unchanged"). An install.sh operator who follows the wiki and sets `ARM_TRANSCODE_IMAGE_QSV=myregistry/...` in `~/arm/.env` gets no override: the backend derives `<prefix>/arm-transcode:<tag>-intel` and tries to pull it from the public registry. Workaround: hand-edit the generated compose.

**Repro / evidence.**

```
grep -n "ARM_TRANSCODE_IMAGE_QSV" install.sh        # no output
grep -n "env_file" install.sh | grep -v 'env_file="\$PREFIX' # no compose env_file
```

**Tip check.** Still present at `71129cd9`: `install.sh:1380-1394` backend env block unchanged except an added `ARM_HOST_ISO_LIBRARY_PATH`; `docs/user/Hardware-Transcoding.md:174-178` still tells operators to set the override.

**Suggested fix location.** feat/encoder-first-presets — add the three lines to the install.sh heredoc next to `ARM_TRANSCODE_IMAGE`, or drop the install.sh instruction from the wiki/PR body.

**Verification.** Code-read of install.sh heredoc at head and tip; untested-needs-hardware for the end-to-end pull (`bash install.sh` on a QSV host with the override set, then `docker inspect armv3-backend | grep ARM_TRANSCODE_IMAGE_QSV`).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/194

### D-073  S4  open  devtools  origin #87

**Title.** install.sh still runs the now-deprecated `--probe-encoders` container at install time; its `{}` output is discarded by the backend, so the step only costs an image pull plus up to 60 s.

**Where.** `install.sh:541` (`timeout 60 docker run ... python -m arm_transcode.main --probe-encoders`) at `e5bd1493`; deprecation in `services/transcode/arm_transcode/main.py:263-271` (`5e777946`).

**What.** `main.py` now prints `{}` for `--probe-encoders` and the backend seeds every row with `encoder_kinds=[]` regardless of the hint (`main.py::_refresh_gpu_inventory`, `gpu_probe.py`). `devtools/setup-dev.sh` had its `probe_encoder_caps` removed in this PR (`d5511639`), but install.sh keeps the whole `probe_encoder_caps`/`kinds_for` machinery, including its "fall back to h264+h265" comment that is no longer true of anything downstream. Dead code with a real install-time cost; acknowledged in the memory entry as "install.sh has no variant awareness".

**Repro / evidence.** `grep -n "probe-encoders" install.sh` -> `:541`; `grep -n "probe-encoders" devtools/setup-dev.sh` -> none.

**Tip check.** Still present at `71129cd9`: `install.sh:541`.

**Suggested fix location.** feat/encoder-first-presets — same change already made to setup-dev.sh (`detect_gpus` emits `encoder_kinds:[]` without probing).

**Verification.** Code-read; `bash devtools/test-setup-dev.sh` asserts the setup-dev side only.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/195

### D-074  S4  open  docs  origin #89

**Title.** The docs sweep changed Settings `/config` -> `/settings` in one place but left the same wrong route in `docs/README-OMDBAPI.md`.

**Where.** `docs/README-OMDBAPI.md:29` at `480138c6` (the PR's "docs: describe the SvelteKit UI" commit, which edited `arm_wiki/Configuring-ARM.md:51` for exactly this).

**What.** The file tells users to "navigate to **Settings** (`/config`)" and enter the OMDb key under Metadata. ui-neu has no `/config` route (routes at head: `/`, `/login`, `/change-password`, `/files`, `/jobs/[id]`, `/logs`, `/logs/[job_id]`, `/notifications`, `/settings`, `/setup`, `/transcoder`); the page is `/settings` (Metadata tab). Same stale claim the PR fixed in the wiki.

**Repro / evidence.**

```
$ grep -rn '(`/config`)' arm_wiki docs
arm_wiki/Configuring-ARM.md:51 ... (`/settings`)      <- fixed by this PR
docs/README-OMDBAPI.md:29:Open the ARM web UI and navigate to **Settings** (`/config`). Under **Metadata / identification**,
```

**Tip check.** Still present at `71129cd9`: `docs/developers/reference/legacy/README-OMDBAPI.md:29` (file relocated by #88 feat/docs-site into a `legacy/` folder, text unchanged — `git grep -n '(\`/config\`)' origin/integration/all-prs-3 -- docs arm_wiki`).

**Suggested fix location.** chore/remove-vue-ui — one-word change in the commit that already does this sweep.

**Verification.** verified by grep + ui-neu route listing at head.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/196

### D-075  S4  open  ci  origin #89

**Title.** The published `arm-ui` image no longer ships `/LICENSE`: ui-neu's Dockerfile lacks the `COPY LICENSE /LICENSE` every other image (and the removed Vue arm-ui image) has.

**Where.** `services/ui-neu/Dockerfile:12-20` (nginx stage, no LICENSE copy) as wired into the `arm-ui` legs of `.github/workflows/release.yml:111`, `publish-main.yml:103`, `weekly-rebuild.yml:181` at `d2a9489e`; the deleted `services/ui/Dockerfile:25` (`COPY LICENSE /LICENSE`) at `daddb6a4`.

**What.** Before this PR the `arm-ui` image was built from `services/ui/Dockerfile`, which bundled the project license like `services/backend/Dockerfile:62`, `services/ripper/Dockerfile:166`, `services/transcode/Dockerfile:146`. Switching the `arm-ui` leg to `services/ui-neu/Dockerfile` silently drops it from the published image, although the root `.dockerignore` explicitly keeps `LICENSE` in the context "so a `COPY LICENSE` can bundle it into each image". Cosmetic/compliance regression in the shipped artifact.

**Repro / evidence.**

```
$ grep -n LICENSE services/*/Dockerfile
services/backend/Dockerfile:62:COPY LICENSE /LICENSE
services/ripper/Dockerfile:166:COPY LICENSE /LICENSE
services/transcode/Dockerfile:146:COPY LICENSE /LICENSE
$ git show origin/feat/encoder-first-presets:services/ui/Dockerfile | grep -n LICENSE
25:COPY LICENSE /LICENSE
```

**Tip check.** Still present at `71129cd9`: `git show origin/integration/all-prs-3:services/ui-neu/Dockerfile | grep LICENSE` matches only a comment (line 4); no `COPY LICENSE`.

**Suggested fix location.** chore/remove-vue-ui — the commit that makes ui-neu the arm-ui image (`d2a9489e`) is where the image contract changes.

**Verification.** verified by reading both Dockerfiles; image not built locally (CI `build-images` job builds `services/ui-neu/Dockerfile` already at base, so the build itself is known-good).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/197

### D-076  S4  open  ci  origin #88

**Title.** New `site/` npm lockfile has no Dependabot coverage, unlike every other dependency manifest in the repo.

**Where.** `.github/dependabot.yml:26-34` (npm ecosystem lists only `/services/ui-neu/frontend`) vs `site/package.json` / `site/package-lock.json` added in `a8b43886` (head `84f9a2f5`).

**What.** The PR adds a third npm manifest (`markdown-it`, `shiki`, `minisearch`, `tailwindcss`, `@tailwindcss/cli`) that is built in CI (`test-site`), in the Pages deploy, and inside the ui-neu image (`services/ui-neu/Dockerfile:7-11`), but `dependabot.yml` was not extended with a `/site` npm entry. The repo's convention (memory `feedback_pin_actions_to_sha.md`, `dependabot.yml` comments) is that Dependabot keeps actions, uv, the ui-neu npm tree and every Dockerfile dir bumped; `site/` is the only manifest left outside that.

**Repro / evidence.**

```
grep -n "directory" .github/dependabot.yml   # "/", "/", "/services/ui-neu/frontend", 4 docker dirs — no "/site"
ls site/package-lock.json                     # exists, 41 KB
```

**Tip check.** Still present at `71129cd9`: `git show origin/integration/all-prs-3:.github/dependabot.yml | grep directory` -> same seven entries, no `/site`.

**Suggested fix location.** feat/docs-site — add `- package-ecosystem: "npm"  directory: "/site"` (weekly, `dependencies` label, grouped) next to the ui-neu entry.

**Verification.** Verified by reading the file at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/198

### D-077  S4  open  docs  origin #88

**Title.** `project_docs_site.md` memory (and the PR body) record the wrong stacking base: "on `feat/encoder-first-presets` (#87)" with a stack list that omits #89/#90.

**Where.** `.claude/memory/project_docs_site.md:31-34` at `84f9a2f5` (text introduced in `b6e98108`, touched again in `f87cf33f`).

**What.** The entry says the branch "sits at the end of the wolfy PR stack, on `feat/encoder-first-presets` (#87; the stack runs #61..#66, #75, #76, #73, #74, #81, #83, #84, #85, #87)". The PR's base is `chore/ui-neu-eslint-prettier` (#90) and the head already contains #89 (Vue removal) and #90 (eslint/prettier): `git merge-base --is-ancestor origin/chore/ui-neu-eslint-prettier origin/feat/docs-site` is true. CLAUDE.md makes this memory authoritative for every session, so the stale rebase/merge-order note misleads the next person who follows "Rebase/merge order matters."

**Repro / evidence.**

```
git merge-base --is-ancestor origin/chore/ui-neu-eslint-prettier origin/feat/docs-site && echo contains-90
sed -n 31,34p .claude/memory/project_docs_site.md
```

**Tip check.** Still present at `71129cd9`: `diff <(git show origin/integration/all-prs-3:.claude/memory/project_docs_site.md) .claude/memory/project_docs_site.md` is empty; lines 31-34 unchanged.

**Suggested fix location.** feat/docs-site — the memory entry is this PR's own artifact; update the base/stack line (or drop the volatile stack list and keep only "base = the branch below it in the stack").

**Verification.** Verified via git ancestry and file contents at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/199

### D-078  S4  open  docs  origin #88

**Title.** Former `docs/ops/` pages now published to the GitHub wiki carry relative `../../services/...` repo links that cannot resolve on the wiki.

**Where.** `docs/user/MakeMKV-Ripper.md:25`, `:51`, `:52` at `84f9a2f5` (page moved into the wiki source dir by `a1b0c7c3`; links are `../../services/ripper/arm_ripper/makemkv_key.py`, `../../services/ripper/install/install_makemkv.sh`, `../../services/ripper/install/update_key.sh`).

**What.** `publish-wiki.yml` now syncs `docs/user/` verbatim to the wiki (`source: docs/user`, `publish-wiki.yml:31`), and the PR deliberately "joined" the user-facing ops notes to the wiki source. On the wiki, a relative `../../services/...` href resolves against `https://github.com/<org>/<repo>/wiki/` and 404s; the wiki has no `services/` tree. The site/app are unaffected (the resolver rewrites these to `blob/main` URLs, `links.mjs:106-107`), so only the wiki rendering is wrong. The PR's own contributor rule says the opposite: "link into the repo with full GitHub URLs" (`docs/developers/contributing/Contribute-Wiki.md:46-47`). (`docs/user/Notification-Scripts.md:128,130` link `examples/*.sh`, which the PR intends to work via the synced `docs/user/examples/`; not counted.)

**Repro / evidence.**

```
grep -n "](\.\./" docs/user/*.md
# docs/user/MakeMKV-Ripper.md:25 ... (../../services/ripper/arm_ripper/makemkv_key.py)
# docs/user/MakeMKV-Ripper.md:51 ... (../../services/ripper/install/install_makemkv.sh)
# docs/user/MakeMKV-Ripper.md:52 ... (../../services/ripper/install/update_key.sh)
```

**Tip check.** Still present at `71129cd9`: `git grep -n "](\.\./" origin/integration/all-prs-3 -- docs/user` -> `docs/user/MakeMKV-Ripper.md:25`, `:52`, `:53` (one line shifted by a later edit; same three links).

**Suggested fix location.** feat/docs-site — rewrite the three hrefs as full `https://github.com/<repo>/blob/main/...` URLs (the site resolver maps those back to `repo` links, `links.mjs:58-64`, so site/app output is unchanged).

**Verification.** Verified link text at head and tip and the wiki-sync source dir; the wiki rendering itself is untested (no GitHub access) — a human can open the wiki page "MakeMKV-Ripper" after the next `publish-wiki.yml` run and click the three links.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/200

### D-079  S4  open  ui-neu  origin #94

**Title.** `dismissAllNotifications` doc comment states the opposite of the backend behaviour this same PR introduced.

**Where.** `services/ui-neu/frontend/src/lib/api/notifications.ts:34` at `4f80aee3` (comment added in `ff5a4751`, contradicted by `e8d40f23`).

**What.** Commit `e8d40f23` changes `POST /inbox/dismiss-all` to mark every not-yet-cleared row seen *and* cleared (purgeable), and the page relies on that (`+page.svelte:66-68` "Like a per-row dismiss ... seen and cleared"). The API client's comment still reads "Marks every unseen row seen. It does NOT clear them, so they are not purgeable." A future caller reading the client will build on the wrong contract.

**Repro / evidence.**

```
$ sed -n 34,36p services/ui-neu/frontend/src/lib/api/notifications.ts
// Marks every unseen row seen. It does NOT clear them, so they are not purgeable.
export function dismissAllNotifications(): Promise<NotificationDismissAllResult> {
	return post<NotificationDismissAllResult>('/api/notifications/inbox/dismiss-all');
$ sed -n 647,660p services/backend/arm_backend/routers/notifications.py   # same PR: sets r.cleared = True for every non-cleared row
```

**Tip check.** Still present at `71129cd9`: `services/ui-neu/frontend/src/lib/api/notifications.ts:34` (identical line, `git show origin/integration/all-prs-3:...`).

**Suggested fix location.** chore/ui-neu-ux-polish — the contradicting backend change is in this PR; one-line comment fix ("Marks every not-yet-cleared row seen and cleared, same as a per-row dismiss").

**Verification.** Read at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/201

### D-080  S4  open  docs  origin #94

**Title.** Status-Roadmap describes maintenance "buttons" for orphaned log files and clearing the raw rip area that do not exist in the UI; this PR deleted their last stubs.

**Where.** `docs/user/Status-Roadmap.md:44-46` at `4f80aee3` (added in `7021daa5`; stubs removed in `16b84d1e`).

**What.** The new roadmap bullet says maintenance tools "find and remove orphaned media folders **and log files**, clean up finished transcode jobs, **and clear the raw rip area** from the UI. The buttons are hidden until these endpoints exist in v3." The UI at head has only the Orphan-folders and Clean-up-transcoder buttons (`routes/files/+page.svelte:570-`); there is no orphan-logs or clear-raw UI, and this PR removes `fetchOrphanLogs/deleteLog/bulkDeleteLogs/clearRaw` from `lib/api/maintenance.ts` as "stubs with no callers". The doc promises hidden features that are not built.

**Repro / evidence.**

```
$ grep -rniE "orphan.?log|clear.?raw|raw rip|raw area" services/ui-neu/frontend/src | grep -v test   # -> no matches
$ git diff origin/feat/docs-site...4f80aee3 -- services/ui-neu/frontend/src/lib/api/maintenance.ts | grep -E "^-export async function (fetchOrphanLogs|deleteLog|bulkDeleteLogs|clearRaw)"
```

**Tip check.** Still present at `71129cd9`: `docs/user/Status-Roadmap.md:43-45` ("find and remove orphaned media folders and log files, clean up finished transcode jobs, and clear the raw rip area from the UI. The buttons are hidden..."); still no orphan-log/clear-raw UI on the tip.

**Suggested fix location.** chore/ui-neu-ux-polish — same commit series introduced the text; reword to the two tools that exist (orphan folders, transcoder job cleanup).

**Verification.** grep at head and tip; docs-only.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/202

### D-081  S3  open  backend  origin #95

**Title.** A parked application that stays parked after rip-complete makes a `ripped` job read "Transcoding 0/0" forever (and stay live/polling).

**Where.** `services/backend/arm_backend/auto_session.py:477` (park on `job.status not in POST_RIP_JOB_STATUSES`, commit 53555eb5) with `services/backend/arm_backend/routers/jobs.py:143-146` (`_session_app_is_terminal` treats WAITING_IDENTIFY with 0 tasks as non-terminal; pre-existing) and `services/ui-neu/frontend/src/lib/utils/job-status.ts:19-20` (`effectiveJobStatus` -> 'transcoding').

**What.** PR #95 deliberately defers output-path resolution for every pre-rip apply to drain time ("A required token that is still empty at drain time stays parked with a template reason"). When the drain fails (e.g. a `{year}` clone template and a job with no year, or `no_outputs`), the row stays WAITING_IDENTIFY on a RIPPED job. `_summarize_transcode_progress` then yields `state='transcoding', tasks_total=0, percent=100.0`; the UI folds that into effective status `transcoding` (badge, lifecycle stepper on the Transcoding stage, "Transcoding 0/0" in the table, `isLive()` true so the detail page polls every 5s and the log panel streams indefinitely), while the new `parked_session_ids` line on the same page says "<session>, waiting". Nothing is transcoding and nothing will. The root (`_session_app_is_terminal`) predates this PR, but this PR widens the entry (Apply is now offered on `awaiting_review` and parks instead of 409ing, and the resolve-fanout/redrain paths park too) and documents the silent park as intended, without making the read layer distinguish "parked with a terminal reason" from "in flight".

**Repro / evidence.**

```
DATABASE_URL=postgresql+asyncpg://u:p@localhost/x ARM_SERVICE_TOKEN=tok-service uv run python -c "
from arm_backend.routers.jobs import _summarize_transcode_progress
from arm_common import SessionApplication, SessionApplicationStatus
sa = SessionApplication(session_id='ses_x', job_id='job_x', status=SessionApplicationStatus.WAITING_IDENTIFY, overwrite=False)
print(_summarize_transcode_progress([sa], []))"
# -> state='transcoding' tasks_total=0 tasks_done=0 tasks_failed=0 percent=100.0
```
Flow: hold_for_review on, apply a user-cloned session with `{year}` to a held disc with no year -> 200 + `waiting_identify` (test_held_disc_apply_flow.py proves the park) -> rip completes -> `drain_parked_applications_after_rip` logs WARN `reason=template` and the row stays parked -> `GET /api/jobs/{id}` has `transcode_progress.state == "transcoding"`.

**Tip check.** Still present at `71129cd9`: `services/backend/arm_backend/routers/jobs.py:180-183` (`return task_count == 0 and sa != SessionApplicationStatus.WAITING_IDENTIFY`), `auto_session.py:478`, `job-status.ts:5` (`POST_RIP = new Set(['ripped','ripped_partial'])`). #96 reduces the frequency (built-ins use `{year?}`) but user clones with `{year}` and the `no_outputs` park still hit it.

**Suggested fix location.** fix/job-status-actions — either persist the drain skip reason on the application (so `_summarize_transcode_progress` can treat a terminally-parked app as terminal and the UI can show "parked: <reason>"), or make `_session_app_is_terminal` ignore WAITING_IDENTIFY rows on POST_RIP jobs when computing `all_terminal`.

**Verification.** Verified the summary function with the real code (above) and traced the UI fold in job-status.ts / job-status-groups.ts; end-to-end drill: `devtools/iso-smoke.sh` with hold_for_review on, apply a clone session whose template uses `{year}` to a job with no year, then inspect the job page after rip-complete (untested-needs-hardware for the live stack).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/203

### D-082  S3  open  ui-neu  origin #95

**Title.** Parked-session line promises "applies when the rip finishes" on failed and abandoned jobs; nothing ever cancels a parked application when the rip fails or the job is abandoned.

**Where.** `services/ui-neu/frontend/src/lib/utils/job-fields.ts:124` at afa8b309 (`isPostRipStatus(job.status) ? 'waiting' : 'applies when the rip finishes'`); `services/backend/arm_backend/routers/ripper.py:1082` (rip-complete FAILED branch) and `services/backend/arm_backend/routers/jobs.py:399` (abandon) touch no SessionApplication rows.

**What.** `isPostRipStatus` is false for `failed` and `abandoned`, so a job whose rip failed (or was abandoned) with a parked session shows `Session: <name>, applies when the rip finishes` in the detail metadata (and the same text via `parkedSessionLine` on the review card). No rip will finish; the WAITING_IDENTIFY row is never cancelled (`after_rip` is only called for RIPPED/RIPPED_PARTIAL), so the promise is false and permanent. The row also keeps `transcode_progress.state='transcoding'` on a failed job (see C1 mechanics), though `isLive` stops at FINAL statuses so at least polling stops.

**Repro / evidence.** `job-fields.ts:116-125`: only two branches, keyed on `POST_RIP` membership. `JobStatus.FAILED`/`ABANDONED` fall into the "applies when the rip finishes" branch. Backend: `grep -n "SessionApplication\|WAITING_IDENTIFY" services/backend/arm_backend/routers/ripper.py` finds no cleanup in `rip_complete`; `abandon_job` (jobs.py:368-433) only flips the job and emits WS events.

**Tip check.** Still present at `71129cd9`: `services/ui-neu/frontend/src/lib/utils/job-fields.ts:124` (identical line); tip `routers/ripper.py` and `routers/jobs.py` abandon still touch no `SessionApplication` rows.

**Suggested fix location.** fix/job-status-actions — this PR introduced `parked_session_ids`/`parkedSessionLine`; add a third branch for FINAL statuses ("not applied: rip failed/abandoned") and, ideally, cancel WAITING_IDENTIFY rows in rip-complete's FAILED branch and in abandon.

**Verification.** Code trace at head and tip; unit-level repro: call `parkedSessionLine({parked_session_ids:['ses_x'], status:'failed'}, new Map())` -> `"ses_x, applies when the rip finishes"`.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/204

### D-083  S4  open  common  origin #95

**Title.** `REDRAIN_JOB_STATUSES` includes pre-rip statuses whose parked applications the redrain can never promote; every transcode re-enable logs a WARN per such row.

**Where.** `packages/arm_common/arm_common/enums.py:144-146` at 53555eb5 (`REDRAIN_JOB_STATUSES = {RIPPED, RIPPED_PARTIAL, IDENTIFIED, AWAITING_REVIEW}`), used at `services/backend/arm_backend/routers/config.py:215`.

**What.** The comment above the set says "the rip is done and identity is known, so the only thing that held an encode application parked was the toggle", but IDENTIFIED and AWAITING_REVIEW are pre-rip. For them `drain_parked_applications_after_rip` -> `_fan_out_tasks_for_application` hits the new `job.status not in POST_RIP_JOB_STATUSES` park and returns `no_tracks`, so the redrain does nothing except log `WARNING transcode re-enable: parked session_application=... stays parked reason=no_tracks` for each pre-rip parked row on every toggle. The PR even adds a test (`test_reenable_leaves_pre_rip_application_parked_even_with_review_tracks`) asserting the no-op. Base had IDENTIFIED in the local tuple; this PR added AWAITING_REVIEW and moved the set to arm_common with a contradicting comment.

**Repro / evidence.** `uv run pytest -q -k test_reenable_leaves_pre_rip_application_parked_even_with_review_tracks` passes and the captured log shows the WARN line; `enums.py:140-146` comment vs members.

**Tip check.** Still present at `71129cd9`: `packages/arm_common/arm_common/enums.py:171-173` (same four members).

**Suggested fix location.** fix/job-status-actions — restrict the set to `POST_RIP_JOB_STATUSES - {RIPPED_AWAITING_IDENTIFY}` (or just RIPPED/RIPPED_PARTIAL) and fix the comment; pre-rip rows drain at rip-complete anyway.

**Verification.** Code trace; test run at head.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/205

### D-084  S4  open  ui-neu  origin #95

**Title.** Detail-page metadata says `State: In progress` for an idle `ripped` job with no session applied.

**Where.** `services/ui-neu/frontend/src/lib/utils/job-fields.ts:132,153` at ce5ef0ab (`const active = isLive(job)` -> `'In progress'`).

**What.** `buildMetadataFields` switched from `isJobActive(status)` (false for `ripped` at base, so the field read "Finished") to `isLive(job)`, which is true for `ripped`/`ripped_partial`/`ripped_awaiting_identify` with no transcode. A disc that finished ripping and is waiting for the operator to pick a session now reads "In progress" although nothing is running; the same `isLive` also opens the log panel by default and keeps it streaming for such jobs (acknowledged in the PR body), but the State label is a plain mis-statement.

**Repro / evidence.** `job-fields.ts:132-156`; base `job-type.ts:119-156` `ACTIVE_STATUSES` did not contain `ripped`.

**Tip check.** Still present at `71129cd9`: `services/ui-neu/frontend/src/lib/utils/job-fields.ts:132,153`.

**Suggested fix location.** fix/job-status-actions — use `isInProgress(job)` for the State field (that helper exists in the same PR precisely to exclude idle post-rip statuses) or add a third label ("Waiting for session").

**Verification.** Code trace at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/206

### D-085  S4  open  ui-neu  origin #95

**Title.** `JobStatsPanel.svelte` and `JobStatsPanel.test.ts` left behind after their last consumer was removed.

**Where.** `services/ui-neu/frontend/src/lib/components/BulkActionsMenu.svelte:1-14` at ce5ef0ab (removed `import type { JobStats } from './JobStatsPanel.svelte'` and the `jobsStats` prop); `services/ui-neu/frontend/src/lib/components/JobStatsPanel.svelte` still present.

**What.** The PR removes the only import of `JobStatsPanel` and acknowledges the files are now unreferenced, but leaves them (and their vitest file) in the tree. Dead component + a test that exercises nothing shipped.

**Repro / evidence.** `grep -rn JobStatsPanel services/ui-neu/frontend/src --include=*.svelte --include=*.ts | grep -v JobStatsPanel\.` returns nothing at afa8b309.

**Tip check.** Still present at `71129cd9`: `git ls-tree origin/integration/all-prs-3 services/ui-neu/frontend/src/lib/components/` lists `JobStatsPanel.svelte` and `JobStatsPanel.test.ts`; no straggler removed them.

**Suggested fix location.** fix/job-status-actions — delete both files in the commit that drops the import.

**Verification.** grep at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/207

### D-086  S4  open  backend  origin #96

**Title.** New `except TemplateValidationError: raise` makes the `malformed template` re-wrap branch uncovered; backend 100%-statement policy regresses.

**Where.** `services/backend/arm_backend/path_template.py:122-125` at f764be4c (`feat(backend): optional output path tokens with {token?}`).

**What.** Before this PR an unknown token raised `TemplateValidationError` inside `format_map`; since it subclasses `ValueError`, it was caught by `except (IndexError, ValueError)` and re-wrapped, so that clause executed in every unknown-token test. The PR adds `except TemplateValidationError: raise` ahead of it to keep the "unknown token" message intact (correct), but no test now exercises a genuinely malformed template (e.g. `"{title"` -> `malformed template: expected '}' before end of string`), so lines 124-125 are uncovered. There is no pragma and no justification.

**Repro / evidence.**

```
uv run coverage run -m pytest -q -k "path_template or naming or sessions_router or transcode_apply" && uv run coverage report | grep path_template
# at afa8b309 (#95 head): no line for path_template.py (100%)
# at 2dcd294f (#96 head): services/backend/arm_backend/path_template.py  73  2  18  0  98%  124-125
```
Full-suite run at 2dcd294f confirms the same two lines missing.

**Tip check.** Still present at `71129cd9`: `services/backend/arm_backend/path_template.py:121-125` has the same clause order and `git grep -n malformed origin/integration/all-prs-3 -- services/backend/tests` finds no path-template test (only drive_scanner/episode tests). No straggler adds one.

**Suggested fix location.** fix/optional-template-tokens — add one test in `services/backend/tests/test_path_template.py` asserting `expand_template("{title", ctx)` raises `TemplateValidationError` matching `malformed template`.

**Verification.** Coverage runs at both heads (above).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/208

### D-087  S4  open  docs  origin #96

**Title.** Architecture docs that `path_template.py` says it mirrors were not updated for the `{token?}` syntax or the new built-in defaults.

**Where.** `docs/developers/architecture/02-job-lifecycle.md:310` (token table, `{year}` row; no mention of optional syntax) and `docs/developers/architecture/04-data-model.md:140` (built-in example still `{title} ({year})/{title} ({year}) - {transcode_slug}.{ext}`) at df22f259 (`docs: optional output path tokens`), which added only `docs/user/Web-UI.md`.

**What.** `path_template.py:6` states "The token whitelist per MediaType mirrors arch §02". The PR introduces new template grammar (`{token?}`, NEVER_OPTIONAL, empty-after-drop rejection) and changes all seven shipped defaults to `{year?}`, but the developer architecture docs still describe the old grammar and show the old default. Docs out of date against the code in the same PR.

**Repro / evidence.** `git grep -n 'year?' origin/fix/optional-template-tokens -- docs` matches only `docs/user/Web-UI.md`; `docs/developers/architecture/04-data-model.md:140` still shows `({year})`.

**Tip check.** Still present at `71129cd9`: `git grep -n 'year?' origin/integration/all-prs-3 -- docs` matches only `docs/user/Web-UI.md:74-85`.

**Suggested fix location.** fix/optional-template-tokens — add the `?` rule to the token table in 02-job-lifecycle.md §"Output paths and naming" and update the 04-data-model.md example.

**Verification.** grep at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/209

### D-088  S3  open  backend  origin #97

**Title.** `test_identify_repost_on_held_disc_keeps_operator_exclusion` passes without ever reaching the resolver it claims to test.

**Where.** `services/backend/tests/test_ripper_router.py:620-672` at `cf4e6d73` (refactor(backend): identify and rip-start go through the identity resolver).

**What.** The test seeds `identity_claims` with a `preset` claim (`selected: False` for track 2) and a `manual` claim (`selected: True`), a track with `identity_provenance={"excluded": "manual"}`, and documents "The preset claim must not flip it back". But a re-POST for a disc whose job is reused takes the `already_identified = True` Guard-1 path in `identify` (`routers/ripper.py:481-487`), which skips the `hold_for_review` branch entirely — `_persist_review_tracks`, `record_preset` and `resolve_job` are never called. The assertion `reenabled.excluded is False` therefore holds because nothing touches the row, not because manual outranks preset. The claims fixture and the stated precedence guarantee are untested (the precedence itself IS covered elsewhere, e.g. `test_identity_resolver.py::test_manual_selected_false_beats_thediscdb_selected_on_unguarded_field` and `test_jobs_router.py::test_patch_sibling_edit_keeps_migrated_legacy_exclusion`, so this is a wrong-reason test, not a missing-coverage defect).

**Repro / evidence.** With an autouse plugin that monkeypatches `arm_backend.routers.ripper.resolve_job` and `record_preset` to raise `AssertionError`, the test still passes:
```
$ PYTHONPATH=$SCRATCH uv run pytest -q -p probe_plugin -k test_identify_repost_on_held_disc_keeps_operator_exclusion
1 passed, 2703 deselected in 2.83s
```

**Tip check.** Still present at `71129cd9`: `services/backend/tests/test_ripper_router.py:692` — same fixture (`"preset": {... "2": {"selected": False}}`, `"manual": ...`) and same two assertions (`len(db.rows["tracks"]) == 2`, `reenabled.excluded is False`); the Guard-1 early path in `identify` is unchanged on the tip.

**Suggested fix location.** feat/identity-core — either retitle/trim it to what it checks (reuse path is a no-op for tracks and claims) or make it exercise the real precedence path (e.g. a held job with existing review tracks + PATCH toggling `excluded`, then assert the stored manual claim and `excluded` after `resolve_job`; or drive `_persist_review_tracks` + `resolve_job` directly with the fixture).

**Verification.** Monkeypatch probe above; code read of `routers/ripper.py:478-487, 547-552`.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/210

### D-089  S4  open  docs  origin #97

**Title.** `04-data-model.md` tracks section still documents `role_source` and free-text `role`; new columns undocumented.

**Where.** `docs/developers/architecture/04-data-model.md:84-85` at `12bd0a66` (the migration commit that drops `role_source`/`video_type` and adds `episode_number_end`/`identity_provenance`).

**What.** The PR removes `tracks.role_source` and `tracks.video_type`, turns `role` into the `TrackRole` enum (`main|episode|extra|trailer|other`, validated app-side) and adds `tracks.episode_number_end`, `tracks.identity_provenance` and `jobs.identity_provenance`. The data-model doc in the same PR still lists `role_source` ("community | user | heuristic") and describes `role` as free text with values `feature, alternate_cut, …`, and lists none of the new columns. Docs out of date against code in the same PR.

**Repro / evidence.**

```
$ git grep -n "role_source" origin/feat/identity-core -- docs/developers/architecture/04-data-model.md
84:- `role` (text, nullable — semantic role within the disc: `feature`, `alternate_cut`, ... Free-text, not enum ...)
85:- `role_source` (text, nullable — `community` | `user` | `heuristic`. ...)
$ git grep -n "identity_provenance\|episode_number_end" origin/feat/identity-core -- docs/developers/architecture/04-data-model.md   # (no output)
```

**Tip check.** Still present at `71129cd9`: `docs/developers/architecture/04-data-model.md:85` (`role_source` line unchanged; no `identity_provenance`/`episode_number_end` anywhere in the file on the tip).

**Suggested fix location.** feat/identity-core — the PR that changed the schema should update the data-model doc (tracks + jobs sections).

**Verification.** git grep at head and tip, as above.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/211

### D-090  S4  fixed-later  backend  origin #97

**Title.** PR body promises `put_source` keeps last-good claims on a same-inputs error; the code is a plain overwrite.

**Where.** `services/backend/arm_backend/identity/proposals.py:52-55` at `5fb706b0` (feat(backend): identity claim storage and manual/preset recorders).

**What.** `put_source(job, source_id, source_claims)` replaces the source entry unconditionally; there is no `status == "error"` / `inputs` comparison, so a later source run that errors would wipe the previous good proposals. In #97 itself nothing records an error status (TheDiscDB lookup failures are only logged), so there is no runtime impact at this PR; it is a claim in the PR body the diff does not deliver.

**Repro / evidence.**

```python
# proposals.py @5fb706b0
def put_source(job: Job, source_id: str, source_claims: SourceClaims) -> None:
    claims = claims_of(job)
    claims.sources = {**claims.sources, source_id: source_claims}
    _store(job, claims)
```

**Tip check.** Fixed by #99 (feat/identity-episode-matcher) in `daf5b2b4` ("resolver keeps last good on error, leaves unknown owners, reports changed tracks": adds the `status=="error" and existing.status=="ok" and inputs unchanged -> keep existing, stash last_error in extra` branch). The same patch is also on the tip as `2348fe16`, which `lowest_pr.sh` reports TIP-ONLY by sha, but the code is present on `origin/feat/identity-episode-matcher` and above (git grep), absent on `origin/feat/identity-disc-hints`. Recommend: **leave** — the fix is only meaningful once sources that report `status="error"` with `inputs` exist (#98/#99); #97 merged alone is not broken by its absence. Alternatively, drop the sentence from the #97 PR body.

**Suggested fix location.** feat/identity-episode-matcher already has it; edit the #97 PR description.

**Verification.** Code read at head; `git grep -c 'source_claims.status == "error"' origin/<branch> -- services/backend/arm_backend/identity/proposals.py` across the stack.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/212

### D-091  S3  untested-needs-hardware  ripper  origin #98

**Title.** BDMT disc-title probe silently yields nothing for UDF-only Blu-ray sources (no ISO 9660 PVD) — pycdlib refuses to open them and the probe soft-fails to None.

**Where.** `services/ripper/arm_ripper/scan/bd_meta.py:66` (`iso.open(source_path)`) and `:84-94` (`probe_bd_meta` catches the exception and returns None) at `bcf72f90` (feat(ripper): read the Blu-ray BDMT disc title), unchanged through head `d826dc55`.

**What.** `_read_bdmt` is the only read path; `PyCdlib.open()` raises `PyCdlibInvalidISO('Valid ISO9660 filesystems must have at least one PVD')` (`pycdlib/pycdlib.py:685` in the pinned 1.14.0) for a pure-UDF 2.50 image, which is exactly what DVDFab-style Blu-ray backups (and plausibly pressed BD-ROMs, which are UDF 2.50 by spec) look like. For those the feature the PR adds never fires: `bd_meta` stays None, `bd_title` records `skipped: "no BDMT disc title"`, and identify falls back to the raw volume label / file name. The volume-label hint still works, so there is a workaround (S3, not S2). The ISO-9660+UDF bridge case does work — verified end-to-end against a pycdlib-authored UDF 2.60 image (`probe_bd_meta` returned `name='Test Show: Season 2' set_number=3 num_sets=4 language='eng'`, English preferred over `bdmt_jpn.xml`).

**Repro / evidence.**

```
# pinned pycdlib refuses any image lacking an ISO 9660 PVD:
grep -n "must have at least one PVD" .venv/lib/python3.14/site-packages/pycdlib/pycdlib.py   # -> :685
# tip straggler commit message confirms the real-world case:
git show --no-patch 89a5cf53   # "PyCdlib refuses an image without an ISO 9660 primary volume descriptor,
                               #  which is what DVDFab's UDF 2.50 Blu-ray backups are, so for them the disc
                               #  title from BDMV/META ... were both unavailable"
```

**Tip check.** GONE on the tip, but fixed only on the integration tip by `89a5cf53` ("feat(ripper): read UDF-only images through 7-Zip for the BD title and matrix256" — adds `scan/udf_image.py` (`7z l -slt -ba -- <img>` / `7z e -so -- <img> <path>`, `--` guard, 180s/60s timeouts, None when the binary is missing), installs `7zip` in the ripper Dockerfile, and `bd_meta.py:108` falls back to `_read_bdmt_udf` when pycdlib raises) plus `2837d671` ("the UDF image reader runs 7zz when 7z is not installed" — Debian 12's `7zip` package ships only `7zz`, so the first fix never activated in the image). `lowest_pr.sh` → `TIP-ONLY` for both; they are in no open PR, so the stack can merge without them → **OPEN**. The 7z path keeps the ripper unprivileged (no mount, no caps — consistent with feedback_ripper_unprivileged_no_mount).

**Suggested fix location.** feat/identity-disc-hints — this PR introduces the BDMT read and the body claims it works for Blu-rays; cherry-pick `89a5cf53` + `2837d671` (udf_image.py, bd_meta fallback, Dockerfile `7zip`, the two test files) down into it, dropping the matrix256_fp.py hunk which belongs to off-stack #82.

**Verification.** untested-needs-hardware — needs a UDF-only BD image or a pressed Blu-ray. Human: `ARM_SOURCE_PATH=/path/to/udf-only.iso bash devtools/iso-smoke.sh` (or insert a retail BD) and check the ripper log for `bdmt device=... name=...` and `identity_claims.sources.bd_title.status == "ok"` on the job; at #98 head expect `skipped`.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/213

### D-092  S4  open  backend  origin #98

**Title.** `parse_label` leaves a year token inside the "cleaned" hint title (e.g. `THE_OFFICE_2005_S1_D2` → `"the office 2005"`), so the first-searched candidate carries the year as query text and the TV search has no year filter to compensate.

**Where.** `services/backend/arm_backend/identity/sources/label_hints.py:113` (title construction) and `:150` (title emitted whenever a season/disc marker was stripped) at `7d62a807`; consumed at `services/backend/arm_backend/metadata/dispatcher.py:147` (hint candidate searched before the label candidate) at `5a46df1a`.

**What.** The module docstring promises "a cleaned search title", and the dispatcher's own `_normalize_volume_label` strips a trailing year (`_YEAR_SUFFIX_RE`) and passes it as the `year` filter; `parse_label` only strips trailing S/D/DISC markers, so a year that sits before the marker survives into the hint. Because `hint_is_tv` is True for these labels, `_search_title(..., tv_first=True)` calls `tmdb.search_tv("the office 2005")` — `search_tv` takes no year, so the year is pure query noise; the movie fallback gets `year=label_year` only via the dispatcher's label pass. A miss falls through to the label candidate (`"THE OFFICE 2005 S1 D2"`), which is worse still. Rare label shape (year + season/disc marker), cosmetic/quality impact, hence S4.

**Repro / evidence.**

```
uv run python -c 'import os;os.environ.setdefault("DATABASE_URL","postgresql://x:x@localhost/x");os.environ.setdefault("ARM_SERVICE_TOKEN","t")
from arm_backend.identity.sources.label_hints import parse_label
print(parse_label("THE_OFFICE_2005_S1_D2")); print(parse_label("BAND_OF_BROTHERS_2001_D1"))'
# LabelHints(title='the office 2005', season=1, disc_number=2, ...)   LabelHints(title='band of brothers 2001', disc_number=1, ...)
```

**Tip check.** Still present at `71129cd9`: `services/backend/arm_backend/identity/sources/label_hints.py:113` (tip's label_hints.py differs from head only by the added `inputs()` method; `dispatcher.py:152` still appends the hint candidate first).

**Suggested fix location.** feat/identity-disc-hints — strip a trailing `(19|20)\d{2}` from `s` after the marker pass (or reuse `_YEAR_SUFFIX_RE`) and let the dispatcher keep supplying `label_year`.

**Verification.** Reproduced with the command above at head `d826dc55`.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/214

### D-093  S3  open  backend  origin #99

**Title.** `/identity/match apply=true` → `invalidate()` → the rerun-once starts while the router is still computing and later overwrites the operator's stored match with a default-input recompute.

**Where.** `services/backend/arm_backend/identity/stage_runner.py:229-231` (`_done` reschedules the moment the invalidated run finishes), `:358` (phase 2 only skips when `job_id in self._rerun`), and `services/backend/arm_backend/routers/identity.py:192` (`stage_runner.invalidate(job_id)` is called BEFORE the router's own network round-trip and commit) at `78a78826` (introduced in `b2fb0fbf`/`eac6df2a`).

**What.** When a background run for the job is pending or in flight (right after identify / rip-start, during the startup-sweep backlog behind `MAX_CONCURRENT_RUNS=2`, or while a provider is slow/backing off), the router marks it for rerun and then spends seconds on providers. The invalidated run reaches phase 2, returns without writing, and `_done` immediately `schedule()`s the rerun, whose phase-1 snapshot is taken before the router commits: it sees no pin, the old `job.season`, and the default tolerance. Its phase 2 blocks on `FOR UPDATE` until the router commits, then `put_source` replaces the router's freshly stored `episodes_*` entry (operator tolerance / `/match` season gone; a different season may have been scanned) while the pin the router set remains, so the resolver now applies the rerun's claims instead of what the operator previewed and applied. The rerun should not start until the caller's write has landed (e.g. `invalidate()` hands back a deferral the router releases after commit, or the router calls `schedule()` itself after commit and `_done` does not auto-reschedule an invalidated run).

**Repro / evidence.** Script using the PR's own test doubles (`_GatedSeasonProvider`, `FakeSession`), run with `uv run python` from the worktree root:
```
rerun started while router still computing: True | pin seen by rerun: {}
router stored inputs: {'show_id': '100', 'season': 1, 'disc_number': None, 'tolerance': 123, 'nominal_runtimes': False}
after rerun   inputs: {'show_id': '100', 'season': 1, 'disc_number': None, 'tolerance': 300, 'nominal_runtimes': False}
pin still: {'episode': 'episodes_tmdb'} | provider.season calls: [('season', 1), ('season', 1)]
```
(`/tmp/claude-0/-home-user/e06fb963-3780-5816-b936-b6d6249b1440/scratchpad/pr99/race_repro.py`: schedule → block in `season()` → `invalidate()` → release → rerun's `season()` reached → emulate the router's commit (`put_source` with tolerance 123 + `set_pin`) → release rerun → stored inputs are back to tolerance 300.) The existing `test_invalidate_marks_rerun_when_run_has_started` never models the caller's write, so it passes without exercising this ordering.

**Tip check.** Still present at `71129cd9`: `identity/stage_runner.py:229-231` (`if job_id in self._rerun and not self._shutdown: ... self.schedule(job_id)`), `:358` (`if fresh_job is None or job_id in self._rerun:`), `routers/identity.py:192` (`stage_runner.invalidate(job_id)`). The only tip change to `stage_runner.py` is the `ids_before.get(field) != value` line (338); no later commit touches the rerun scheduling.

**Suggested fix location.** feat/identity-episode-matcher — the runner and the `/match` route are both introduced here; the fix is self-contained (defer the rerun until the caller commits).

**Verification.** Reproduced with the script above against the PR head; no hardware needed.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/215

### D-094  S4  open  backend  origin #99

**Title.** Operator-supplied external ids are interpolated unescaped into provider URL paths.

**Where.** `services/backend/arm_backend/identity/episodes/providers/tmdb.py:122` (`f"{settings.ARM_TMDB_BASE_URL}/find/{external_id}"`) and `services/backend/arm_backend/identity/episodes/providers/tvdb.py:94` (`f".../search/remoteid/{ids.imdb}"`) at `78a78826` (introduced in `f598a247` / `8dfa7a87`).

**What.** `ExternalIds` (`packages/arm_common/arm_common/schemas/job_metadata.py:35-43`) has no pattern, and `ResolveRequest.external_ids` accepts any string, so an operator pasting an IMDb URL, an id with trailing whitespace, or anything containing `/`, `?` or `#` produces a malformed provider path (a `?` even injects query params ahead of `external_source`). TMDb/TVDB answer 404 → `SourceMiss` → the stage records `status="miss", detail="show not found"` with no hint that the id was malformed. `urllib.parse.quote(value, safe="")` at the two call sites (or an `^tt\d+$` / digits validator on the id fields) would make the failure explicit. TVmaze is unaffected (ids go in `params`).

**Repro / evidence.** `POST /api/jobs/{id}/resolve {"title":"X","external_ids":{"imdb":"https://www.imdb.com/title/tt0903747/"}}` then `GET /api/jobs/{id}/identity/episodes?source=tmdb&season=1` → `GET /3/find/https://www.imdb.com/title/tt0903747/?external_source=imdb_id` → 404 → "no tmdb show id known for job". No `quote` usage anywhere under `identity/` (`grep -rn quote services/backend/arm_backend/identity/` is empty).

**Tip check.** Still present at `71129cd9`: `providers/tmdb.py:52` (`f"{settings.ARM_TMDB_BASE_URL}/find/{external_id}"`), `providers/tvdb.py:94` (`.../search/remoteid/{ids.imdb}`). The providers directory has no commits above this PR on the tip.

**Suggested fix location.** feat/identity-episode-matcher — the two provider call sites are new here.

**Verification.** Code read + grep; the HTTP path shape follows from httpx's URL handling (not executed against the live providers — no key).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/216

### D-095  S4  open  docs  origin #99

**Title.** `02-job-lifecycle.md` still says Play-All titles are "not auto-detected" while this PR's matcher detects them (sum-of-episodes and sum-of-other-titles) and roles them `extra`.

**Where.** `docs/developers/architecture/02-job-lifecycle.md:287` at `78a78826` (the PR edits lines 285 and adds the "Episode matching" section at 295-298 but leaves 287 as-is).

**What.** Line 287: `"Play All" tracks ... are *not* auto-detected and filtered — "duration ≈ sum of other tracks" doesn't work because special features on the same disc confound the heuristic.` The same PR adds `matcher._is_play_all` (3+ consecutive episode sum, sum of ≥3 other titles, or exactly-two-others within 10 s) and `episode_stage._ok_claims` stores every `play_all` ref as `TrackClaim(role=EXTRA)` (`episode_stage.py:311-312`). The sentence contradicts the new section two paragraphs below; it should say the naming layer does not filter them but the episode stage marks them `extra`.

**Repro / evidence.** `grep -n 'not\* auto-detected' docs/developers/architecture/02-job-lifecycle.md` → line 287; `grep -n play_all services/backend/arm_backend/identity/episode_stage.py` → 311, 328.

**Tip check.** Still present at `71129cd9`: `docs/developers/architecture/02-job-lifecycle.md:287` (identical sentence).

**Suggested fix location.** feat/identity-episode-matcher — the contradicting section is added by this PR.

**Verification.** Code/doc read.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/217

### D-096  S3  open  ui-neu  origin #100

**Title.** Emptying an int setting now sends `null`; for `thediscdb_refresh_days` and `manual_wait_seconds` the backend has no None check, so Save ends in an unhandled NOT NULL IntegrityError (HTTP 500).

**Where.** `services/ui-neu/frontend/src/lib/components/settings/ConfigSchemaField.svelte:86` at `037ef7f2` (`value = raw === '' ? null : Number(raw);`); backend side `services/backend/arm_backend/routers/config.py:160-162` (None/positive check covers only `drive_scan_interval_seconds`, `drive_detected_prune_days`, `max_parallel_transcodes`) and `:208` (`setattr` loop) at head `0afe5abe`.

**What.** Before this PR an int field was a text input: clearing it sent `""`, which Pydantic rejected with a 422 the form displayed. The new `type="number"` input converts an empty box to `null`, which `ConfigUpdateRequest.thediscdb_refresh_days: int | None` accepts; `update_config` writes `None` into a `nullable=False` column and `session.commit()` raises `IntegrityError` -> 500, shown as "Couldn't save settings. API 500: Internal Server Error". `thediscdb_refresh_days` sits in Settings > Metadata > Lookup, `manual_wait_seconds` in Ripping. Workaround: type a number. Either the input must not emit `null` for a NOT NULL int, or the router must 400 like it does for the other three ints (the PR itself added exactly that style of check for `episode_match_tolerance_seconds`).

**Repro / evidence.** Temporary e2e test (real SQLite harness, `tests/e2e/conftest.py` `app_client` + `admin_token`), run with `uv run pytest -q -k test_pr100_repro_null_int_fields`:
```
PATCH /api/config {"thediscdb_refresh_days": null}  -> IntegrityError: NOT NULL constraint failed: config.thediscdb_refresh_days
PATCH /api/config {"manual_wait_seconds": null}     -> IntegrityError: NOT NULL constraint failed: config.manual_wait_seconds
PATCH /api/config {"drive_scan_interval_seconds": null} -> 400 "must be a positive integer"   (the validated one, for contrast)
```
The UI path: `SchemaConfigForm.buildPayload()` sends the field because `unchanged(null, 7)` is false.

**Tip check.** Still present at `71129cd9`: `ConfigSchemaField.svelte:106-113` (`type="number"` ... `raw === '' ? null : Number(raw)`), `routers/config.py:158` (same three-key list; the tip only adds a `max_parallel_iso_rips` 1..8 check from #101), `routers/config.py:210` setattr loop. The straggler `67f81e06` on the tip is a byte-identical re-commit of `037ef7f2` (interdiff empty), not a fix.

**Suggested fix location.** feat/identity-settings — the PR introduced the `null` emitter; add `thediscdb_refresh_days`/`manual_wait_seconds` to the positive-int 400 list in `routers/config.py` (backend defence) and/or keep the number input from emitting `null` for a non-nullable int.

**Verification.** Executed the repro above against the real-DB e2e harness at the PR head (file removed afterwards); UI side traced through `ConfigSchemaField` -> `SchemaConfigForm.buildPayload` -> `saveArmConfig`.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/218

### D-097  S3  open  backend  origin #100

**Title.** Changing `episode_sources` / `disc_hint_sources` does not re-resolve existing jobs, so a disabled source's already-applied fields stay on the job until an unrelated trigger runs the resolver.

**Where.** `services/backend/arm_backend/routers/config.py:208-220` at `23c0b15a` (fields are `setattr`'d and committed; nothing re-resolves jobs); `services/backend/arm_backend/identity/pipeline.py:35-38` at `29640970` (the only place `disabled_source_ids(cfg)` is consulted is inside `resolve_job`); docs claim `docs/developers/architecture/02-job-lifecycle.md:297` at `39c8278a` ("unchecking one stops it running and resets the fields it owned").

**What.** Operator sees a wrong season/disc number from the `label` hint (or a wrong episode placement from `episodes_tmdb`) on an `awaiting_review`/`identified` job, unchecks that source in Settings > Metadata > TV episodes and saves. The job page keeps showing the old values and the rip/transcode will use them: the resolver logic is right (test `test_resolve_job_resets_when_config_disables_the_winning_source` shows the reset) but `resolve_job` is only run by the episode stage, `PATCH /api/jobs/{id}`, `/resolve`, `/identity/match` and `/identity/pin`. Nothing runs it after a config change. Workaround: `POST /api/jobs/{id}/identity/match` or `PATCH` any identity field on each affected job. Either re-run `resolve_job` (and the episode stage, since a newly enabled source has no stored claims yet) for live jobs when these keys change, or change the doc/PR-body wording to "takes effect the next time the job is resolved".

**Repro / evidence.** `test_resolve_job_resets_when_config_disables_the_winning_source` (`services/backend/tests/test_identity_pipeline.py`) needs a second explicit `await resolve_job(db, job)` after swapping the config row; grep shows no `resolve_job`/`EpisodeStageRunner` reference in `routers/config.py` at head or tip.

**Tip check.** Still present at `71129cd9`: `routers/config.py:210` (setattr loop, no identity follow-up; tip adds only the transcode re-drain and ISO cap), `identity/pipeline.py:38`, doc sentence at `02-job-lifecycle.md:297`.

**Suggested fix location.** feat/identity-settings — the PR introduces both the setting and the doc claim; a follow-up in #101/#102 would still leave the claim false for this PR merged alone.

**Verification.** Traced statically; backend tests at head exercise `resolve_job` only when called explicitly. No hardware needed to confirm (a PATCH to `/api/config` followed by `GET /api/jobs/{id}/identity` on a dev stack shows the unchanged fields).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/219

### D-098  S4  open  ui-neu  origin #100

**Title.** `RankedListField`'s "Needs <source> key" chip hardcodes the `Metadata` tab in its deep link instead of deriving it from the required key's field metadata.

**Where.** `services/ui-neu/frontend/src/lib/components/settings/RankedListField.svelte:91` at `dc362123` (`href="#Metadata/{missing}"`).

**What.** `ranked` is a generic field type and `enum_requires` maps a value to an arbitrary secret key; the component is reused by first-run setup per `feedback_setup_reuses_settings_components.md`. The settings deep link is `#<tab>/<field key>` (`routes/settings/+page.svelte:120-135`), so a ranked field whose required key lives in another group would open the wrong tab. Today both keys happen to be in Metadata, so it works by coincidence. Should look the key up in the group list / `CONFIG_FIELD_META` (the form already has `group.fields`) or receive the tab from the parent.

**Repro / evidence.** `RankedListField.test.ts` asserts the literal `'#Metadata/tvdb_api_key'`; no group lookup exists in the component.

**Tip check.** Still present at `71129cd9`: `RankedListField.svelte:91` `href="#Metadata/{missing}"`.

**Suggested fix location.** feat/identity-settings — the component is introduced here.

**Verification.** Static read of head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/220

### D-099  S4  open  ui-neu  origin #100

**Title.** Two recurring visual patterns are re-implemented inline instead of shared: the TV-episodes summary strip copies SessionCard's recipe strip, and the "Advanced" label copies `.session-card-recipe-label` (`feedback_standard_ui_patterns.md`: a pattern in two places is extracted).

**Where.** `services/ui-neu/frontend/src/lib/components/settings/TvEpisodesSummary.svelte:61-62, 92-125` at `639f68db` ("Recipe strip metrics copied from SessionCard.svelte's .session-card-recipe"); `services/ui-neu/frontend/src/lib/components/settings/SchemaConfigForm.svelte:323-335` at `037ef7f2` ("the session-card-recipe-label look (SessionCard.svelte), restated here since this is its only other consumer - not yet a shared block").

**What.** Both comments acknowledge the duplication. The memory rule is explicit that the second site is the moment to extract. On the tip a shared `sessions/RecipeStrip.svelte` (cells + chevron arrows, mobile stacking) now exists and is used by SessionCard and the setup disc table, but `TvEpisodesSummary` still carries its own copy of the strip markup and CSS, so Settings > Metadata and Settings > Sessions will drift as RecipeStrip evolves (it already differs: tint token, separator breakpoint 40rem vs the shared one's).

**Repro / evidence.** `git show 71129cd9:services/ui-neu/frontend/src/lib/components/settings/TvEpisodesSummary.svelte | grep -n import` -> only `Glyph` and the type import; `RecipeStrip.svelte` added by `e7945cd4` "refactor(ui): shared RecipeStrip (sessions + setup disc table)".

**Tip check.** Still present at `71129cd9`: `TvEpisodesSummary.svelte:61` (copy comment) and `:92` (`.tv-episodes-summary-strip`), `SchemaConfigForm.svelte:383-384` (advanced label copy). The extraction commit `e7945cd4` is TIP-ONLY (in no open PR) and did not migrate TvEpisodesSummary anyway.

**Suggested fix location.** feat/identity-settings for the advanced label (introduced here, trivially a shared `.section-label` utility); the strip should adopt `RecipeStrip` once that straggler lands in a PR (or extract it here and let `e7945cd4` rebase onto it).

**Verification.** Static read of head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/221

### D-100  S2  open  ripper  origin #101

**Title.** The extract fallback (`iso_extract`) needs 7-Zip, but this PR's ripper image never installs it; every image MakeMKV cannot open fails as "no titles".

**Where.** `services/ripper/arm_ripper/iso_extract.py:92-95` (`shutil.which("7z") or shutil.which("7zz")` -> `logger.error("7-Zip (7z / 7zz) is not installed")`, return False) and `services/ripper/Dockerfile` runtime apt list (no `7zip`/`p7zip`) at `d2de3dde` (introduced by b84c4470 "unpack an image MakeMKV cannot open", 7038537f "runs 7zz when 7z is not installed").

**What.** The PR advertises (memory `project_iso_source_ripping.md`, doc 10 section "Extract fallback", commits b84c4470/7038537f) that a DVDFab UDF 2.50 ISO MakeMKV crashes on is unpacked with `7z x -tudf` and ripped as a folder. The PR touches no Dockerfile and the ripper image's apt lists contain no 7-Zip package, so `_run_7z` always returns False, `extract()` returns None, `_scan_extracted` returns None, and rip-start fails the job with `ISO_NO_TITLES` ("even after unpacking it" — misleading, nothing was unpacked). The ripper tests only pass because they monkeypatch `shutil.which` (`tests/test_iso_extract.py:226,242`) or skip (`needs_7z`).

**Repro / evidence.**

```
grep -n "7zip\|7zz\|p7zip" services/ripper/Dockerfile        # head: no output
git show origin/integration/all-prs-3:services/ripper/Dockerfile | grep -n 7zip   # tip: line 93 "7zip \"
git log -S'7zip' origin/feat/identity-settings..origin/integration/all-prs-3 -- services/ripper/Dockerfile
# -> 89a5cf53 feat(ripper): read UDF-only images through 7-Zip for the BD title and matrix256   (lowest_pr.sh: TIP-ONLY)
```

**Tip check.** Fixed only on the integration tip by `89a5cf53` (`feat(ripper): read UDF-only images through 7-Zip for the BD title and matrix256`, adds `7zip` to the ripper runtime apt list at Dockerfile:93), which is in no open PR -> OPEN.

**Suggested fix location.** feat/iso-source-rip — add `7zip` to the runtime stage's `apt-get install` list in `services/ripper/Dockerfile` (the code already prefers `7zz`, which is the binary Debian's `7zip` package ships), or move 89a5cf53 down into this PR.

**Verification.** Static (grep of the Dockerfile at head vs tip). Runtime: untested-needs-hardware — build the ripper image from this branch and run `bash devtools/iso-smoke.sh` against an ISO that `makemkvcon info iso:` lists no titles for; expect the job to fail with "MakeMKV found no titles in this ISO, even after unpacking it" and the ripper log line "iso extract: 7-Zip (7z / 7zz) is not installed".

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/222

### D-101  S3  open  backend  origin #101

**Title.** An ISO (or disc folder) whose name contains `:` cannot be ripped: the bind spec docker-py builds is `host:container:mode`, so the extra colon makes the spawn fail with 500 and the drive is retired.

**Where.** `services/backend/arm_backend/ripper_manager.py:175` (`volumes[iso_host_path(drive.source_path, library_host=library_host)] = {"bind": source, "mode": "ro"}`) with `source = drive.device_path = f"/source/{target.name}"` set in `services/backend/arm_backend/iso_rips.py:353`, at `d2de3dde` (introduced by ff9890cf).

**What.** The physical-drive spec only ever binds operator-configured directories; the virtual spec binds a user-named file, on both sides of the colon. docker-py's `convert_volume_binds` renders a dict volume as `f'{k}:{bind}:{mode}'` (`.venv/.../docker/utils/utils.py:168-170`) and the daemon's Linux bind parser rejects a spec with more than three colon-separated fields ("invalid volume specification"). Names like `Star Wars: Episode IV.iso` are ordinary on Linux file systems. `ensure_running` raises `RipperManagerError`, `create_iso_rip` retires the just-created drive and answers 500 "could not start the ISO ripper: ...". Workaround: rename the file.

**Repro / evidence.** `touch "$ARM_HOST_ISO_LIBRARY_PATH/A: B.iso"`, then `POST /api/iso/rips {"path": "A: B.iso"}` -> 500 (truncation check passes since the file is empty/unknown layout). Or, zero-infra: `RipperManager(settings, FakeDocker).container_spec(drive)` yields `volumes={"/lib/A: B.iso": {"bind": "/source/A: B.iso", "mode": "ro"}}` which docker-py serialises as `/lib/A: B.iso:/source/A: B.iso:ro`.

**Tip check.** Still present at `71129cd9`: `services/backend/arm_backend/ripper_manager.py:175` (identical line; no tip commit touches the bind construction).

**Suggested fix location.** feat/iso-source-rip — bind at a fixed, name-free container path (e.g. `/source/image.iso` / `/source/disc`) and pass the display name separately, or switch the virtual spec to `mounts=[docker.types.Mount(target, source, type="bind", read_only=True)]`, which carries source/target as separate fields and accepts colons.

**Verification.** untested-needs-hardware (needs a docker daemon): run the `touch`+POST above against a dev stack; expect HTTP 500 and the backend log `could not start the ISO ripper: APIError: ... invalid volume specification`. Static reasoning from docker-py's bind formatter is quoted above.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/223

### D-102  S4  open  backend  origin #101

**Title.** New uncovered backend statement: `_virtual_source_drive`'s `drive_id is None` guard is unreachable from `rip_start` and has no test or pragma.

**Where.** `services/backend/arm_backend/routers/ripper.py:107-108` at `d2de3dde` (introduced by 00790a2f "Rip from folder").

**What.** `rip_start` reaches `_virtual_source_drive` only after `require_drive_owner_by_job`, which already 403s a job with `drive_id=None` ("job has no owning drive"), so `return None` on line 108 can never execute and the Backend's 100%-statement policy is broken for a file the PR touched (coverage report: `routers/ripper.py ... 99%  108, 548, ...`; 548/1008 pre-exist at BASE).

**Repro / evidence.**

```
uv run coverage run -m pytest -q && uv run coverage report --include='services/backend/arm_backend/*' -m
# services/backend/arm_backend/routers/ripper.py   520   3  ...  99%   108, 548, ...
```

**Tip check.** Still present at `71129cd9`: `routers/ripper.py:109-110` (same guard). The only tip test with `drive_id=None` (`services/backend/tests/test_ripper_router.py:2634`, `test_owner_check_rejects_job_whose_drive_was_deleted`) asserts the 403 from the owner check, so the branch stays unreached there too; ccd66608's coverage top-up covers the dump-fallback branches, not this one.

**Suggested fix location.** feat/iso-source-rip — drop the guard (make `drive_id: str` the precondition, as the owner dependency guarantees) or add a direct unit test of `_virtual_source_drive` with a drive-less job.

**Verification.** coverage run above at head.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/224

### D-103  S4  open  ripper  origin #101

**Title.** `ARM_SOURCE_KIND` is set by the backend, declared by the ripper and documented as "selects the MakeMKV source scheme", but nothing in the ripper reads it.

**Where.** `services/ripper/arm_ripper/config.py:47-51` (comment + `ARM_SOURCE_KIND: str = "iso"`), `services/backend/arm_backend/ripper_manager.py:167` (`env["ARM_SOURCE_KIND"] = ...`), `docs/developers/architecture/10-iso-source-ripping.md:143-144`, at `d2de3dde` (introduced by 9248d772 / ff9890cf).

**What.** `rg ARM_SOURCE_KIND services/ripper/arm_ripper` matches only the Settings declaration. The MakeMKV scheme (`iso:`/`file:`/`dev:`) is chosen by inspecting the path (`source.py:makemkv_source_url`, `is_folder_source`), so the env var is dead configuration and the config comment/architecture doc describe a mechanism that does not exist. Also the comment still says "`folder` is a later addition" although the same PR ships it.

**Repro / evidence.** `grep -rn ARM_SOURCE_KIND services/ripper/arm_ripper/` -> only `config.py:51`.

**Tip check.** Still present at `71129cd9`: `services/ripper/arm_ripper/config.py:51` (declared, never read), `ripper_manager.py:168` (still set).

**Suggested fix location.** feat/iso-source-rip — either read it (`source.py` could trust the kind instead of re-sniffing) or remove the env var from both sides and fix the comment/doc.

**Verification.** grep above at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/225

### D-104  S4  open  docs  origin #101

**Title.** Status-Roadmap lists "Extracted disc folders as a rip source" as "Next up" while this PR ships Rip from folder.

**Where.** `docs/user/Status-Roadmap.md:50-52` at `d2de3dde` (text from 56b69631; feature added by 00790a2f in the same PR).

**What.** The roadmap says a `BDMV`/`VIDEO_TS` folder source is not built yet, but `GET /api/iso/folders`, `DriveSourceKind.FOLDER`, `disc_folders.py` and the gear menu's "Rip from folder" are all in this diff. Docs out of date against code in the same PR.

**Repro / evidence.** `grep -n "Extracted disc folders" docs/user/Status-Roadmap.md` vs `grep -n '"/folders"' services/backend/arm_backend/routers/iso.py` (line 124).

**Tip check.** Still present at `71129cd9`: `docs/user/Status-Roadmap.md:49-51` (same paragraph).

**Suggested fix location.** feat/iso-source-rip — move the bullet into the "in place" list next to the ISO bullet.

**Verification.** grep.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/226

### D-105  S4  open  docs  origin #101

**Title.** Configuring-ARM recommends a relative `ARM_HOST_ISO_LIBRARY_PATH` ("e.g. `./iso-library`") that the backend deliberately treats as "not configured".

**Where.** `docs/user/Configuring-ARM.md:37` vs `services/backend/arm_backend/iso_library.py:200-205` (`library_configured()` requires `Path(host).is_absolute()`), at `d2de3dde` (both from 56b69631 / b3940e54).

**What.** An operator who follows the doc and sets `ARM_HOST_ISO_LIBRARY_PATH=./iso-library` gets the compose mount (it is interpolated into the `volumes:` entry) but `GET /api/iso/library` answers 503 "the ISO library is not configured" and the picker shows the setup card. The code's reason (a relative bind source would be read by docker as a named volume for the spawned ripper) is correct; the doc is wrong.

**Repro / evidence.** `.env`: `ARM_HOST_ISO_LIBRARY_PATH=./iso-library` -> `library_configured()` False -> 503.

**Tip check.** Still present at `71129cd9`: `docs/user/Configuring-ARM.md:37` (same cell) and `iso_library.py:15-18` (same rule).

**Suggested fix location.** feat/iso-source-rip — say "an absolute host path, e.g. `/srv/arm/iso-library` or a NAS mount; relative values are ignored".

**Verification.** read of both files at head and tip.

**Installer gap (2026-10-11, same defect).** A fresh `armctl install` (#119) creates `<arm>/iso-library` but never writes `ARM_HOST_ISO_LIBRARY_PATH`, so the key stays at the commented template default and the backend reports the same 503 on every install. Filed as #134, closed as a duplicate of this row. Fix branch `fix/installer-iso-library-path`: `write_env` sets the key to `<arm>/iso-library` (absolute) when unset, keeps a user-set value, and the doc cell now asks for a full path; verified 200 on a fresh install from the published images.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/227

### D-106  S4  open  ui-neu  origin #101

**Title.** IsoPicker re-implements byte formatting inline instead of using the shared `formatBytes` helper.

**Where.** `services/ui-neu/frontend/src/lib/components/IsoPicker.svelte:97-103` (`function formatSize`) vs `services/ui-neu/frontend/src/lib/utils/format.ts:16` (`export function formatBytes`), at `d2de3dde` (introduced by e429377c).

**What.** `feedback_standard_ui_patterns.md`: recurring UI logic is a shared helper, never a one-off. `formatSize` duplicates `formatBytes` with slightly different output (`'--'` for null, `1` decimal above bytes), so ISO sizes in the picker format differently from sizes elsewhere in the UI.

**Repro / evidence.** `grep -rn "function formatSize\|export function formatBytes" services/ui-neu/frontend/src/lib`.

**Tip check.** Still present at `71129cd9`: `IsoPicker.svelte:97` (`function formatSize`).

**Suggested fix location.** feat/iso-source-rip — `import { formatBytes } from '$lib/utils/format'` and keep only the null fallback.

**Verification.** grep at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/228

### D-107  S4  open  ui-neu  origin #101

**Title.** The picker's "not configured" card tells every operator to redeploy with `bash devtools/setup-dev.sh up`, a dev-only script.

**Where.** `services/ui-neu/frontend/src/lib/components/IsoPicker.svelte:346` at `d2de3dde` (introduced by e429377c).

**What.** `feedback_ui_port_8081.md`: the installer is canonical for deployment values. Production installs (install.sh-generated compose) have no `devtools/` directory; the instruction is wrong for them (they need `docker compose up -d` after editing `.env`). The same card is the only in-product guidance for enabling the feature.

**Repro / evidence.** `grep -n "setup-dev.sh up" services/ui-neu/frontend/src/lib/components/IsoPicker.svelte`.

**Tip check.** Still present at `71129cd9`: `IsoPicker.svelte:346` (same line).

**Suggested fix location.** feat/iso-source-rip — "restart the stack (`docker compose up -d`)", or link to Configuring-ARM.

**Verification.** grep at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/229

### D-108  S4  open  ripper  origin #101

**Title.** `_scan_extracted` removes a multi-GB extraction with a synchronous `shutil.rmtree` on the event loop.

**Where.** `services/ripper/arm_ripper/scan/dispatcher.py:31` (`iso_extract.discard_all()` inside `async def _scan_extracted`) at `d2de3dde` (introduced by b84c4470).

**What.** `discard_all` is plain `shutil.rmtree`. When the unpacked folder (up to a full Blu-ray, under `/raw/.iso-extract/<drive_id>/`) yields no titles, the deletion runs inline in the scan coroutine and blocks the ripper's heartbeat loop, WS client and the `prepare` keepalive for the duration of the rmtree. `main.run_source_mode` does the same cleanup correctly via `asyncio.to_thread(iso_extract.discard_all)`, and `iso_extract.extract` offloads its own rmtree calls; this call site is the odd one out.

**Repro / evidence.** diff hunk: `logger.warning("extracted image %s has no titles either; dropping the extraction", device_path)` followed by bare `iso_extract.discard_all()`.

**Tip check.** Still present at `71129cd9`: `services/ripper/arm_ripper/scan/dispatcher.py:31` (same call).

**Suggested fix location.** feat/iso-source-rip — `await asyncio.to_thread(iso_extract.discard_all)`.

**Verification.** code read; blocking duration depends on extraction size (untested-needs-hardware for timing).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/230

### D-109  S3  open  ui-neu  origin #102

**Title.** MakeMKV step records done/attention from a config snapshot taken before the key was entered or verified.

**Where.** `services/ui-neu/frontend/src/lib/components/setup/steps/MakemkvStep.svelte:14` and `services/ui-neu/frontend/src/lib/components/setup/SetupConfigFields.svelte:19-28,36-38` at `a725180d` (introduced in 9056efd7).

**What.** `MakemkvStep.commit()` saves the form, then decides the recorded state with `fields.current()?.makemkv_key_valid === false ? 'attention' : 'done'`. `SetupConfigFields.current()` returns the `ConfigView` fetched once in `onMount` (`config = s.config`); neither `save()` nor the `MakemkvKeyField` 5s poll (which keeps its own `cfg`) refreshes it. On a fresh install `makemkv_key_valid` is `null` at mount, so a purchased key the ripper has since rejected (the widget's own status strip says "Key not accepted") is recorded `done`; conversely an install whose earlier key was invalid at mount but was replaced with a working one (or switched to the beta key) is recorded `attention`. The stepper, Finish summary and dashboard checklist then show a state that contradicts the live status on the same page.

**Repro / evidence.**

```
# SetupConfigFields.svelte: config is only ever assigned here
onMount(async () => { const s = await fetchSettings(); group = ...; config = s.config; });
export async function save() { return form ? form.save() : false; }   // does not touch `config`
export function current() { return config; }
# MakemkvStep.svelte:14
return fields.current()?.makemkv_key_valid === false ? 'attention' : 'done';
```
Manual: Settings-free fresh install, enter a bogus purchased key, wait for the enrolled drive's ripper to report `invalid` (status strip turns "Key not accepted"), press Continue -> stepper shows "Done".

**Tip check.** Still present at `71129cd9`: `git show origin/integration/all-prs-3:services/ui-neu/frontend/src/lib/components/setup/steps/MakemkvStep.svelte` line 14 is the identical `fields.current()?.makemkv_key_valid === false` expression; `SetupConfigFields.svelte` identical.

**Suggested fix location.** feat/first-run-setup - re-fetch `/api/config` (or take the `MakemkvKeyField`'s polled `cfg`) after `save()` before deciding, or make the decision in the backend when the step is PUT.

**Verification.** Code trace at head (vitest has no test for the makemkv commit path: `steps-behaviour.test.ts` covers Account/System/Drives only). Live confirmation needs an enrolled drive: untested-needs-hardware (run the walkthrough on a dev stack with one optical drive).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/231

### D-110  S4  open  docs  origin #102

**Title.** Docs and Finish summary written in this PR describe a guest-access choice on step 1 that the same PR removed.

**Where.** `docs/user/Setup-Walkthrough.md:21-22`, `docs/user/Getting-Started.md:170-172`, `services/ui-neu/frontend/src/lib/components/setup/steps/FinishStep.svelte:54` at `a725180d`; the removal is commit a30b9de4 (`AccountStep.svelte` lost `GuestAccessField`).

**What.** Setup-Walkthrough.md ("You can also let people on your network view ARM without signing in (read-only)") and Getting-Started.md step 1 ("choose whether guests on your network can look around") tell the operator to expect a guest-access control on the account step; `AccountStep.svelte` renders only the password form (the test `steps-behaviour.test.ts` even asserts "guest access is not part of the step"). FinishStep's account summary still reads "Password changed. Guest access on/off." for a setting the walkthrough never offered. The PR body repeats the claim.

**Repro / evidence.**

```
$ grep -n GuestAccessField services/ui-neu/frontend/src/lib/components/setup -r   # no hits
$ grep -n "network view" docs/user/Setup-Walkthrough.md   # 21: ... let people on your network view ARM without signing in
```

**Tip check.** Still present at `71129cd9`: `git show origin/integration/all-prs-3:docs/user/Setup-Walkthrough.md` lines 21-22 identical; `Getting-Started.md`, `FinishStep.svelte` identical.

**Suggested fix location.** feat/first-run-setup - drop the two doc sentences and the FinishStep guest clause (or restore the field; the owner's reuse memory allows either).

**Verification.** grep + read at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/232

### D-111  S4  open  backend  origin #102

**Title.** Public `/api/setup/status` exposes the ARM version unauthenticated although the UI never reads it and `/api/system/version` is JWT-gated.

**Where.** `services/backend/arm_backend/routers/setup.py:116` and `packages/arm_common/arm_common/schemas/setup.py:14` at `a725180d` (introduced in 3bf6cad3 / 9f1c8512).

**What.** `SetupStatusPublic.arm_version` is returned to anonymous callers with no guest-access check, while the existing `GET /api/system/version` requires `require_jwt` (the login page uses that gating as its "guest enabled" probe). Nothing in `services/ui-neu/frontend/src` consumes `arm_version` (only a test fixture mentions it), so the field is both a dead wire field and a small information disclosure (exact version -> CVE lookup) on an endpoint that is reachable before sign-in by design.

**Repro / evidence.**

```
$ grep -rn arm_version services/ui-neu/frontend/src --include=*.svelte --include=*.ts | grep -v api.gen
services/ui-neu/frontend/src/routes/login/__tests__/login-page.test.ts:105: ... arm_version: '3.1.0' ...
$ curl -sk https://localhost:8081/api/setup/status   # {"first_run":true,"arm_version":"3.x"} with no Authorization header
```

**Tip check.** Still present at `71129cd9`: `routers/setup.py:116` `return SetupStatusPublic(first_run=first_run, arm_version=_app_version())` unchanged.

**Suggested fix location.** feat/first-run-setup - drop the field (regen OpenAPI snapshot + TS types) or move the version to the authenticated `SetupView`.

**Verification.** Code read; `test_status_is_public_and_first_run_when_not_completed` asserts the field is a str but no UI consumer exists.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/233

### D-112  S4  open  backend  origin #102

**Title.** After "Run setup again", resuming from `/setup` lands on the Finish step, not the first step.

**Where.** `services/backend/arm_backend/routers/setup.py:183` (`restart_setup` pops only `finish`) with `_current_step` at `:73-77`, and `services/ui-neu/frontend/src/lib/components/setup/SetupChecklistCard.svelte:43` (`goto('/setup')`) at `a725180d` (introduced in 3bf6cad3).

**What.** A completed walkthrough has every step recorded. `/restart` removes only `finish`, so `_current_step(progress)` returns `finish` and `GET /api/setup` reports `current_step: "finish"`. Settings' button side-steps this with `goto('/setup/system')`, but the dashboard checklist (visible again because `completed_at` is null) says "Resume setup" and navigates to `/setup`, whose loader redirects to `/setup/<current_step>` = the Finish page; so does any later return to `/setup`. The docs promise "walks through the steps again". Workaround: use the stepper.

**Repro / evidence.**

```
$ uv run python -c "from arm_backend.routers.setup import _current_step; from arm_common.enums import SETUP_STEP_ORDER
p={s.value:{'state':'done','at':None} for s in SETUP_STEP_ORDER}; p.pop('finish'); print(_current_step(p))"
finish
```

**Tip check.** Still present at `71129cd9`: `routers/setup.py:183` `progress.pop(SetupStep.FINISH.value, None)` and `_current_step` unchanged; `SetupChecklistCard.svelte:43` unchanged.

**Suggested fix location.** feat/first-run-setup - have `/restart` return/record a `current_step` of `system` (e.g. a `setup_resume_step` or clearing non-attention states), or have the checklist resume at `/setup/system` like Settings does.

**Verification.** Python one-liner above against the head router; UI path by code read.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/234

### D-113  S4  open  ui-neu  origin #102

**Title.** nginx comment for the `/docs-data/` 404 rule now sits above the new `/arm-ca.crt` block.

**Where.** `services/ui-neu/nginx.conf:60-64` at `a725180d` (introduced in 9056efd7).

**What.** The CA-certificate `location = /arm-ca.crt` block was inserted between the pre-existing comment "In-app help bundle (built by the Dockerfile's docs stage). A missing file must be a real 404, not the SPA's index.html." and the `location /docs-data/` it describes, so the comment now reads as describing the CA block. Functionally the exact-match location does not disturb `/docs-data/` prefix matching (the ordering concern raised on #88 does not bite), and the CA file is mounted into `arm-ui` in both the installer (`install.sh:1415`) and the dev template (`docker-compose.yml.example:264`), so the route itself is fine.

**Repro / evidence.**

```
60:    # In-app help bundle (built by the Dockerfile's docs stage). A missing
61:    # file must be a real 404, not the SPA's index.html.
62:    # Public CA certificate for the setup walkthrough's "Download certificate"
65:    location = /arm-ca.crt {
74:    location /docs-data/ {
```

**Tip check.** Still present at `71129cd9`: `git show origin/integration/all-prs-3:services/ui-neu/nginx.conf` lines 60/65/74 identical.

**Suggested fix location.** feat/first-run-setup - move the CA block (and its comment) above the help-bundle comment.

**Verification.** File read at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/235

### D-114  S4  open  ripper  origin #102

**Title.** `backend_client.py` reads `ARM_DRIVE_ID` straight from `os.environ` instead of the ripper's `settings.ARM_DRIVE_ID` every other module uses.

**Where.** `services/ripper/arm_ripper/backend_client.py:192` and `:207` at `a725180d` (introduced in 820135d5 and 1ba9103d).

**What.** `arm_ripper/config.py` declares `ARM_DRIVE_ID: str` as a required pydantic setting and `main.py:62,81` / `iso_extract.py:72` read `settings.ARM_DRIVE_ID`. The two new call sites bypass it with `os.environ.get("ARM_DRIVE_ID")` (optional), so a misconfigured container would send no `drive_id` / `None` here while the rest of the ripper would already have failed on settings validation; the tests pin the env-var access (`monkeypatch.setenv/delenv`) rather than the settings object. Naming/pattern inconsistency only; behaviour is identical in the spawned container (`ripper_manager.py:119` sets the env).

**Repro / evidence.** `grep -rn "ARM_DRIVE_ID" services/ripper/arm_ripper/*.py` shows `settings.ARM_DRIVE_ID` in main.py/iso_extract.py and `os.environ.get` only in backend_client.py.

**Tip check.** Still present at `71129cd9`: `git show origin/integration/all-prs-3:services/ripper/arm_ripper/backend_client.py` lines 192 and 207 identical.

**Suggested fix location.** feat/first-run-setup.

**Verification.** Code read; `uv run pytest -k backend_client_drive` passes at head.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/236

### D-115  S4  open  common  origin #82

**Title.** `DiscFingerprintInput` docstring still calls matrix256 "ARM-native" (and omits `thediscdb`) although the PR body claims the schema comment was updated.

**Where.** `packages/arm_common/arm_common/schemas/ripper.py:74` at `132c5d23`.

**What.** The PR updates the model-side comment in `models/disc_fingerprint.py` to "matrix256v1 structural hash" and the PR body says "Model/schema comments updated"; the wire schema's canonical-algo list was not touched, so the two comments now disagree about the same algo, and the list still misses `thediscdb` which this PR's code emits alongside it. Docstring-only; no runtime effect (and no OpenAPI impact since the field description is not exported).

**Repro / evidence.** `git diff origin/main...origin/feat/matrix256-fingerprint -- packages/arm_common/arm_common/schemas/ripper.py` is empty; line 74 reads `` `musicbrainz` (CD disc id), `matrix256` (ARM-native). ``

**Tip check.** Still present at `71129cd9`: `packages/arm_common/arm_common/schemas/ripper.py:79` — same text.

**Suggested fix location.** feat/matrix256-fingerprint (#82) — same PR that made the claim.

**Verification.** Read the diff and the file at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/237

### D-116  S4  open  docs  origin #103

**Title.** `docs/ops/makemkv.md` "What the install scripts do" still says the script "Scrapes the current MakeMKV version" after this PR makes a pinned version the default.

**Where.** `docs/ops/makemkv.md:52` at `6980e18b`.

**What.** The PR edits two bullets of this file to describe the pin (lines 33-34) but leaves the install-script summary bullet at line 52 describing the pre-PR behaviour ("Scrapes the current MakeMKV version, fetches the GPG-signed sha256sums.txt..."). After this PR the script only scrapes when `MAKEMKV_VERSION` is empty; by default it builds the pinned release and also tries `download/old/`. Same-PR doc drift.

**Repro / evidence.** `git diff origin/main...origin/fix/pin-makemkv-1.18.4 -- docs/ops/makemkv.md` touches lines 33-34 only; line 52 unchanged: `... Scrapes the current MakeMKV version, fetches the GPG-signed \`sha256sums.txt\`, downloads ...`

**Tip check.** Still present at `71129cd9`: the file moved to `docs/user/MakeMKV-Ripper.md` (docs-site PR #88) and line 52 there carries the identical stale sentence; straggler `1dd9c932` ported only the two edited bullets.

**Suggested fix location.** fix/pin-makemkv-1.18.4 (#103) — same file, same PR; the port into `docs/user/MakeMKV-Ripper.md` on the tip needs the same one-line fix.

**Verification.** Read at head and tip.

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/238

### D-117  S3  open  ci  origin: stack-level

**Title.** The integration tip carries 30 commits that are in no open PR; merging the 27 PRs does not reproduce the tested tip.

**Where.** `origin/integration/all-prs-3` at `71129cd9`; list in `docs/plans/DEFECT_REGISTER.md` § Tip-only commits (computed with `git patch-id` against every PR branch).

**What.** The tip was presented as the union of the stack plus two stragglers. After discounting 12 rebased copies of PR commits, it holds 30 non-merge commits whose content is in none of the 28 PR branches, including behavioural fixes the register's tip checks ran into: UDF-only Blu-ray reading via 7-Zip and the `7zip` package in the ripper image (`89a5cf53`, `2837d671` — D-rows for #98 and #101 depend on them), MakeMKV pin build args (`0fe90250`, `98e1fafc`), the log tailer moved off the event loop (`3137c881`), live transfer stats / rip progress (`7bfdc6b3`), backend coverage top-ups (`0048ca44`, `ccd66608`), the ws pre-auth disconnect log fix (`f627024d`), job-page navigation fixes, Playwright snapshot refreshes, five memory/docs commits, and most of PR #104's TV-episode UI (`74dceb16`, `a79a6f2d`, `9e604159`, `065d96d4`, `2568c406`, `53768751`, `6135379f`, `cea3e01e`, `71129cd9`). CI green on the tip therefore does not prove the stack green, and every defect the register marks "fixed only on the tip" reopens when the PRs merge.

**Repro / evidence.**

```
$ cd arm-v3 && for b in <all 28 PR branches>; do git rev-list --no-merges origin/main..origin/$b; done | sort -u | while read c; do git show $c | git patch-id --stable | cut -d' ' -f1; done | sort -u > pr-patchids.txt
$ git rev-list --no-merges origin/integration/all-prs-3 ^origin/<each PR branch> | while read c; do pid=$(git show $c | git patch-id --stable | cut -d' ' -f1); grep -q "^$pid$" pr-patchids.txt || echo $c; done   # 37, of which 12 are rebased copies (same subject + diffstat in a PR branch)
```

**Tip check.** Still present at `71129cd9` by construction. PR #104 (`feat/tv-episode-match-ui`, outside the review scope) is the natural home for the TV-episode group but its head is not an ancestor of the tip and it was not reviewed.

**Suggested fix location.** Open PRs for the tip-only commits grouped by theme: UDF/7-Zip (`89a5cf53`, `2837d671`) onto `feat/iso-source-rip`; MakeMKV build args onto `fix/pin-makemkv-1.18.4`; coverage top-ups onto `feat/phase3-session-routing`/`feat/iso-source-rip`; the TV-episode group via #104; the rest onto `feat/first-run-setup`. Or rebuild the integration branch strictly from the PR heads and re-run CI.

**Verification.** Verified with git patch-id as above (zero-infra).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/239

### D-118  S4  open  ci  origin: stack-level

**Title.** `wolfy/v3-improvments` (upstream only) carries 89 commits of v2-era UI/model work that exist nowhere in the stack; keep-or-kill decision needed.

**Where.** `shitwolfymakes/automatic-ripping-machine` branch `wolfy/v3-improvments` at `5895696d` (not present on `uprightbass360/arm-v3`); merge-base with `main` is `892a5f12` (2025-03-28, pre-cutover v2).

**What.** Not reviewed, by instruction. Inventory for the human decision: 254 commits beyond `main`, of which 89 are not patch-equivalent to anything in the tip (the other 165 landed in some form). Authors: Microtechno9000 (79), 1337-server (3), Mtech (2), github-actions version bumps (5); dated 2023-07-24 .. 2026-04-18. The 89 unique commits touch only pre-cutover v2 paths that no longer exist in the tree: `arm/ui` (378 file-changes), `arm/models` (71), `arm/ripper` (22), `arm/ui_config.py` (21), `docker-compose.yml` (16), `scripts/docker` (11), `arm_wiki/Status-Roadmap.md` (9), `Dockerfile-UI` (8), `requirements.txt`, `arm/config`, `test_ui/conftest.py`, `VERSION`, `devtools/armdevtools.py`, `arm/migrations`, `arm/common`. Subject-line mix: 48 feat, 33 fix, 20 test, 16 docs, 9 chore, 5 automated version bumps. The memory entry `project_backend_coverage_push.md` says the backend coverage push happened on this branch; that part is in the tip. Nothing on it applies to the v3 tree without a port.

**Repro / evidence.**

```
$ git fetch upstream wolfy/v3-improvments
$ git cherry origin/integration/all-prs-3 upstream/wolfy/v3-improvments | grep -c '^+'   # 89
$ git log --oneline --no-merges origin/main..upstream/wolfy/v3-improvments | wc -l         # 254
```

**Tip check.** Not applicable (branch is not part of the stack). Recorded so a human can decide keep-or-kill; recommendation: delete or archive as a tag — the unique commits are v2 code paths.

**Suggested fix location.** n/a — decision row.

**Verification.** Inventory only; no code review performed (by instruction).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/240

### D-120  S4  open  ui-neu  origin: main (anonymous-guest design, pre-stack)

**Title.** With guest access disabled, an unauthenticated visit fires the whole dashboard load before the 401 redirect, and the pollers keep running on `/login`: 20 `401` responses and 20 console errors per cold visit.

**Where.** `services/ui-neu/frontend/src/routes/+layout.svelte` (stores start on mount for every page; the 401 handler only de-duplicates the `goto('/login')`), `src/routes/+layout.ts:25-28` (`hydrateConfig()` before the auth check), `src/lib/api/client.ts:58-68`, at `577d8019`.

**What.** Tokenless is treated as a guest and the backend decides (`auth.py:80-88`). With guest access off (the installed default) every unauthenticated load starts config, jobs, drives, transcodes, transcode stats, ISO prepares, inbox count, version, resources and themes; each 401s and logs a console error; the stores are not stopped by the redirect, so the same calls run again on `/login`. A direct cold load of `/login` still makes three 401 calls. No functional breakage.

**Repro / evidence.** Fresh install from the published `latest` images (2026-10-11), Playwright response log at `networkidle`: cold `/` = 22 API calls, 20 x 401; cold `/login` = 4 calls, 3 x 401; cold `/jobs` = 14 calls, 13 x 401. Full list in the issue.

**Tip check.** Present at `577d8019`; predates the stack (anonymous-guest spec 2026-07-12), unchanged on the integration tip.

**Suggested fix location.** `+layout.svelte`: gate the store starts on `!isAuthPage` and stop them when the 401 handler fires; `+layout.ts`: skip `hydrateConfig()` on the auth pages or make `/api/config` public; one public probe (`/api/setup/status`) can decide guest-or-login before the dashboard loads.

**Verification.** Reproduced on a fresh install (confirmed).

**Issue.** https://github.com/shitwolfymakes/automatic-ripping-machine/issues/242

## Tip-only commits (in no open PR)

Computed at `71129cd9` by `git patch-id` against all 28 PR branches, then de-duplicated by subject + diffstat against rebased copies (12 tip commits turned out to be rebased copies of commits that ARE in #100/#101/#102/#103 — e.g. `5bd2fe9f`→#102, `62d5aa32`/`cd57ff36`/`222bf512`/`ac5a5ff4`/`13344e6d`→#101, `67f81e06`→#100, `0c92aecc`/`e7945cd4`/`f4375669`/`05ee8667`→#102, `1dd9c932`→#103). The 30 commits below have no counterpart in any open PR:

```
71129cd9 | chore(ui-neu): regenerate API types
53768751 | refactor(identify): use arm_common.disc_shape
6135379f | docs: Match Episodes tab, Movie/TV switch, tmdb_kind
2568c406 | fix(ui-neu): episode matching ends on job.identity_updated, not the first job event
74dceb16 | feat(ui-neu): Match Episodes tab and Movie/TV switch on the job page
a79a6f2d | feat(jobs): JobView.looks_episodic and has_series
9e604159 | feat(identify): the chosen TMDb hit carries its IMDb and TVDB ids
065d96d4 | fix(identify): a disc of same-length episodes searches TV first
2837d671 | fix(ripper): the UDF image reader runs 7zz when 7z is not installed
98c0f74c | docs(memory): never restart hifi-server's backend while a passthrough is filing
ccd66608 | test(backend): cover the ISO dump fallback's error branches; drop a dead try/except
3137c881 | fix(backend): the log tailer does its filesystem work off the event loop
7bfdc6b3 | feat: live transfer stats for full-disc copies, and live rip progress on the job page
c28a3938 | style(ui-neu): prettier-format the header theme button
f627024d | fix(ws): a client that disconnects before auth is a debug line, not a traceback
89a5cf53 | feat(ripper): read UDF-only images through 7-Zip for the BD title and matrix256
98e1fafc | build(ripper): resolve a pinned MakeMKV release from makemkv.com/download/old/
0fe90250 | build(ripper): MAKEMKV_VERSION build arg pins the MakeMKV release
5417c349 | fix(ui-neu): back-navigation affordances are real buttons
6da93d4c | style(backend): ruff format after the rip-start test merge
47899a84 | test(ui-neu): refresh setup and settings-metadata visual snapshots after the walkthrough polish
7e06b31f | docs(memory): dev-host validation tips from the 1 October run
fb7e7b48 | test(ui-neu): reset the mocked page id after the job-id navigation test
fe1b372e | fix(ui-neu): job page reloads when client-side navigation changes the job id
c6fa33b7 | fix(ui-neu): label the header theme toggle for screen readers and hover
b7afa298 | fix(devtools): seed-test-data writes per-job logs as the service user
3c9c5320 | test(ui-neu): refresh the Playwright visual suite for the current UI and add setup/settings specs
0048ca44 | test(backend): cover the remaining 45 uncovered statements
616fc059 | docs(memory): setup reuse rule, gap register, PEP 758, offload architecture, Vue removal
cea3e01e | fix(metadata): bound the TMDb external_ids lookup by the provider timeout
```

## Verification on hifi-server (2026-10-03)

Deployed `integration/all-prs-4` @ b8e15ff4 on hifi-server (quark) with `setup-dev.sh up` (DB backed up). No optical drive is enrolled there; disc paths used the ISO library (`/nfs/files/Video/Import/ingress`). Every row carries a `verified/*` label on arm-v3 with the evidence; the runtime results are summarised here. Rows not listed were either static (S4, docs/dead code: the deployed tree is content-identical to the sweep's tip, so the tip check stands), fixed-later (absent from the deployed union by construction), or hardware-gated (labelled `verified/needs-disc`).

| Row | Issue | Verdict | Evidence |
|---|---|---|---|
| D-096 | #98 | confirmed | `PATCH /api/config {"thediscdb_refresh_days": null}` -> 500; backend log `asyncpg NotNullViolationError ... thediscdb_refresh_days`; column unchanged (7). |
| D-044 | #46 | confirmed | `chmod 000` file in `/home/upb/arm/scripts` (mounted `/scripts`) -> `GET /api/notifications/scripts` 500; 200 again after removing it. |
| D-038 | #40 | confirmed (S2) | bash channel with secret input `SMTP_PASS=s3cretXYZ`; `PATCH /api/notifications/channels/{id}` with `config.script="does-not-exist.sh"` and `inputs.SMTP_PASS="<hidden>"` -> 200, `secret_keys=[]`, and both the PATCH response and a following GET return `inputs.SMTP_PASS: s3cretXYZ` in clear. |
| D-039 | #41 | confirmed | `POST /api/notifications/scripts/preview {run:true}` with the same secret: response `inputs` masked (`<hidden>`) but `result.stdout="pass=s3cretXYZ"`, `result.stderr="err=s3cretXYZ"`, and `result.error` repeats the stderr line. |
| D-040 | #42 | confirmed | preview `run:true` of `sleep 8` with `timeout_seconds=1` -> `script timed out after 1s`; a `/proc` scan inside `armv3-backend` immediately after shows `sleep 8` (pid 1296) still alive. |
| D-041 | #43 | confirmed, worse than filed | hook `sleep 8 &; exit 0` with `timeout_seconds=1` -> **HTTP 500**, backend traceback `bash_runner.py:80 run_script -> raise ProcessLookupError()` (bash already exited; the kill targets a gone pid). The register predicted a timeout *result*; on the deployed tip it is an unhandled 500. |
| D-042 | #44 | confirmed | declared input `TO="{job_title:>300000}"` -> preview `run:true` HTTP 500, backend log `OSError: [Errno 7] Argument list too long`. |
| D-003 | #5 | confirmed (S1, live proof) | `fingerprint_records([("../"*N + "tmp/claude-1000/d003/victim.txt", 3), ...])` against the real `arm_ripper.scan.matrix256_fp` truncated the sentinel file outside the temp root from 28 to 3 bytes; the module has no containment check (`relative_to`/`is_relative_to` absent). |
| D-001 | #3 | confirmed (static, deployed tree) | `install.sh` `emit_ripper_block()` body contains no `ARM_DRIVE_ID` while `services/ripper/arm_ripper/config.py` declares `ARM_DRIVE_ID: str` (required). Not runnable on hifi (deployed through setup-dev, not install.sh); the mismatch is unambiguous. |
| D-072 | #74 | confirmed (static, deployed tree) | `install.sh` has 0 references to `ARM_TRANSCODE_IMAGE_(QSV|VAAPI|NVENC)`; `docker-compose.yml.example` has 5. |
| D-034 | #36 | backend half confirmed | `PUT /api/session-routes {media_type: movie, disc_type: null, session_id: ses_builtin_iso_dump}` -> 200 (route accepted across media types). UI half (select shows nothing) needs the browser. Route removed again afterwards. |
| D-100 | #102 | fixed at tip (confirmed via ISO) | `arm-ripper:latest` on hifi has `/usr/bin/7zz`; the Half Baked ISO rip (job_01M409E58N073P5WZSVDT5HRM8) scanned through it: ripper log `matrix256 view=udf-7z files=81`, then `scan complete`, job created as bluray and ripping. Fix lives in #105. |
| D-091 | #93 | fixed at tip (confirmed via ISO) | same rip: the UDF-only image yielded a BDMT name (`bdmt device=/source/oh-halfbaked1998.iso name=...`) via the 7-Zip reader instead of soft-failing to None; `pydvdid compute failed` is logged as expected for a BD. Fix lives in #105 (89a5cf53 + 2837d671). |
| D-101 | #103 | confirmed | hardlink `Half: Baked.iso` -> `POST /api/iso/rips` 500 `could not start the ISO ripper: APIError ... invalid volume specification: '/nfs/.../Half: Baked.iso:/source/Half: Baked.iso:ro'`; the virtual drive row was retired cleanly. (First attempt with MirrorMask was refused 422 up front because that ISO is an incomplete download, 13.8 of 32.0 GB: incidental library finding.) |
| D-060 | #62 | confirmed (static) | seeder returns before the back-fill on a fresh install; hifi's DB is not fresh. |
| D-117 | #119 | resolved, closed | linear restack of 2026-10-03; all-prs-4 equals top-of-stack + #103. |

Incidental findings: the MirrorMask ISO in the library is an incomplete download (13.8 of 32.0 GB) and is refused up front with a 422, which also means D-101 needed a complete image to reach the spawn. The Half Baked ISO rip (job_01M409E58N073P5WZSVDT5HRM8) exercised the 7-Zip UDF reader end to end.
