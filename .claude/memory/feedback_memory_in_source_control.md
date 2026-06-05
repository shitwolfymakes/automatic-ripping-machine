---
name: Memory for this repo lives in source control
description: All project memory for automatic-ripping-machine is stored at .claude/memory/ in the repo and committed, so every device and teammate gets the same guidance.
type: feedback
---

Project memory for this repo is tracked in source control at `.claude/memory/` rather than in the per-user `~/.claude/projects/<slug>/memory/` path that Claude Code's auto-memory system uses by default. The loader mechanism is a short instruction at the top of `CLAUDE.md` telling Claude to `Read` `.claude/memory/MEMORY.md` at session start and read individual entries on demand — not a filesystem symlink.

**Why:** The user wants memory to synchronize across all their devices and be visible to teammates cloning the repo. The per-user path is machine-local and can't do that; committing memory into the repo does, and a CLAUDE.md instruction makes it portable to every contributor without per-device setup.

**How to apply:**

- Save new memory files under `<repo>/.claude/memory/` and add an index line to `<repo>/.claude/memory/MEMORY.md`.
- Commit both alongside the related code change.
- Do **not** write to `~/.claude/projects/<slug>/memory/` for this repo — it's an empty directory by design.
- If the user ever says a memory is private to them / their machine, fall back to the per-user path.
