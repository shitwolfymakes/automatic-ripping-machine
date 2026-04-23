# Memory

- [Memory for this repo lives in source control](feedback_memory_in_source_control.md) — memory is committed under `.claude/memory/`; CLAUDE.md instructs Claude to read MEMORY.md at session start. Don't write to the per-user `~/.claude/projects/<slug>/memory/` path.
- [DB enums stored as VARCHAR](feedback_db_enums_as_varchar.md) — never use Postgres CREATE TYPE enums; validate enums in the app layer at write time.
