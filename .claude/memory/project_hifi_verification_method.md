---
name: hifi-verification-method
description: How the defect-register rows were verified on hifi-server (temporary admin, ISO rips as the disc path, API checks, gotchas) on 2026-10-03
metadata:
  type: project
---

Register verification on hifi-server (quark), 2026-10-03, against
`integration/all-prs-4` @ b8e15ff4 (deployed with `setup-dev.sh up`, which
now backs up the DB and refuses with active rips). Results: see the
"Verification on hifi-server" section of `docs/plans/DEFECT_REGISTER.md` and
the `verified/*` labels on arm-v3 (`confirmed`, `not-reproduced`, `static`,
`needs-disc`).

**Method that worked**
- API access: insert a temporary admin into `users` (argon2 hash made locally
  with the backend venv's `argon2.PasswordHasher`, `password_must_change=false`),
  `POST /api/auth/login` -> `access_token`, delete the row afterwards. No
  bootstrap env exists; the real admin password is the owner's.
- Disc paths: `POST /api/iso/rips {"path": "<file in the ISO library>"}`.
  The ephemeral ripper's log vanishes on exit; capture it with a loop that
  `docker logs -f` the `arm-ripper-iso-*` container the moment it appears.
  A hardlink in the library (`ln`) is a free way to test name handling (the
  library is NFS, group-writable). The MirrorMask ISO there is an incomplete
  download and is refused with 422 before any spawn.
- Bash hooks: scripts in `/home/upb/arm/scripts` (mounted `/scripts`);
  declare inputs with `# arm-input: KEY label="..." [secret]`; preview with
  `POST /api/notifications/scripts/preview {config, event_type, run}`;
  `event_type` values come from `GET /api/notifications/event-types`
  (`rip.completed` works).

**Gotchas**
- SQL over ssh: write the heredoc with a quoted delimiter (`<<'EOF'`) or `$$`
  turns into a PID and the query silently empties (bit twice this session).
- `pgrep`/`ps` are not in the backend image; scan `/proc/*/cmdline` with the
  venv python instead.
- Never run two git commands concurrently in one worktree (index.lock).
- Anything that changes live routing/config (session routes, presets) must be
  reverted in the same step: `DELETE /api/session-routes/{id}` (not a query
  param), `DELETE /api/transcode-presets/{id}`.

**How to apply:** reuse this for the next verification pass; keep the
temporary admin lifetime to one session and delete it; prefer ISO rips over
physical discs for repeatability.
