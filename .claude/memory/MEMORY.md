# Memory

- [Memory for this repo lives in source control](feedback_memory_in_source_control.md) — memory is committed under `.claude/memory/`; CLAUDE.md instructs Claude to read MEMORY.md at session start. Don't write to the per-user `~/.claude/projects/<slug>/memory/` path.
- [DB enums stored as VARCHAR](feedback_db_enums_as_varchar.md) — never use Postgres CREATE TYPE enums; validate enums in the app layer at write time.
- [Ripper: one makemkvcon per disc, never per title](feedback_ripper_no_per_title.md) — `rip_disc` shells `makemkvcon mkv ... all` once; per-title invocations cause USB-BD drive autosuspend / SCSI NOT_READY failures between titles.
- [Backend test harness](project_backend_test_harness.md) — two tiers (fast fake-session router tests vs real-DB e2e under tests/e2e/); env/argon2/metadata gotchas; pre-existing test_dispatcher.py whole-suite collision.
- [Backend coverage push](project_backend_coverage_push.md) — 70%→94% status; which modules still have gaps and the pattern to finish them; no CI gate yet.
- [Ripper disc-insert detection](project_ripper_insert_detection.md) — poll loop (no udev) + drive quirk (TRAY_OPEN ~2s flash, settles NOT_READY→DISC_OK) and the InsertDetector fix.
- [ISO-source ripping = ephemeral spawned workers](project_iso_source_ripping.md) — rip-from-.iso is designed as transcode-style ephemeral containers spawned per ISO, NOT a long-running service; owner directive; future UI-upload front door; design at docs/arch/10-iso-source-ripping.md.
- [Pin GitHub Actions to commit SHAs](feedback_pin_actions_to_sha.md) — every `uses:` must be a 40-char SHA + `# vX.Y.Z`, never a tag/branch; dependabot keeps them bumped.
