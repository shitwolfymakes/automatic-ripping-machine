---
name: project-guidelines-audit
description: Codebase-wide refactor to the CLAUDE.md development guidelines, tracked on wolfy #407; how to measure S3776 through SonarQube for IDE's local endpoint and how to resume
metadata:
  type: project
---

Tracker: shitwolfymakes/automatic-ripping-machine #407. One sub-issue per package,
created when its phase starts (arm_common, transcode, site, ripper, backend,
ui-neu), and one sub-issue per unit of work under its package. Commits go
straight to `main`, one per refactoring-skill use (applied by a Sonnet
subagent), with a test-only commit first when a symbol isn't fully covered.
Each unit is pushed once its gate is green.

**Measuring S3776 without the editor:** SonarQube for IDE's embedded server
listens on the first free port in 64120-64130. Send
`POST /sonarlint/api/analysis/files` with `{"fileAbsolutePaths": [...]}` and
the header `Origin: http://localhost`; without the Origin header the server
answers 400. Findings come back as `ruleKey, message, severity, filePath,
textRange`, and the S3776 message carries the complexity number. Two
prerequisites:

- `sonarlint.pathToNodeExecutable` must be set in the gitignored
  `.vscode/settings.json`, or JS/TS analysis is skipped. The server reads it
  only when it starts.
- No unreadable directory may sit under the workspace root. The Python
  plugin's package-root resolver runs a bare `Files.walk` that ignores the
  exclusion settings. A postgres data dir under `arm/db` (uid 999, mode 700)
  aborts all Python analysis.

The server can answer from stale copies of files edited on disk during the
session. Consecutive calls then cycle between versions, and line numbers
point at old positions. To spot it, sample several times and check that
each S3776 range still lands on a function name in the current file. To
clear it, kill the `sonarlint-ls.jar` process; VS Code restarts it, and the
analyzers need about 20 s to warm up. The server only analyses files it
already knows about. Fresh copies, paths outside the workspace, and
git-ignored paths all return HTTP 500.

SonarJS doesn't analyse `.svelte`, so Svelte script blocks are out of scope
for the complexity rule (owner decision).

**Why:** the owner wants the guidelines applied to existing code, with SonarQube
for IDE as the complexity authority.

**How to apply:** to resume, read #407 and find the open unit sub-issue that
has a "started" comment. Then check `git status` and `git log origin/main..main`.
Related: [[project-backend-coverage-push]].
