---
name: project-guidelines-audit
description: The finished codebase-wide refactor to the CLAUDE.md development guidelines (wolfy #407); how to measure S3776 through SonarQube for IDE's local endpoint, and the coverage-measuring traps it hit
metadata:
  type: project
---

Tracker: shitwolfymakes/automatic-ripping-machine #407, finished 2026-11-10.
Every first-party package (arm_common, transcode, site, ripper, backend,
ui-neu) has a closed sub-issue with its audit table and units. Sonar reports
no S3776 in any of the 554 in-scope source files (77 at the 2026-11-05
baseline). The tracker lists the defects found while pinning, which were filed
and not fixed, and the deferred items that need an owner decision.

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

**A touched symbol's coverage includes its closures.** coverage.py reports a
nested function as its own region (`outer.inner`), and V8 reports every
function separately. A per-symbol check that reads only the named region
calls a closure-heavy function fully covered when its closures aren't. That
hid real gaps in the ripper's `_execute_rip` (#453). Fold nested regions into
the named symbol before judging it.

**A file no test loads is not covered.** With `--coverage.include`, Vitest
still lists a file no test imported, with empty statement, function and
branch maps. A checker that counts missing entries calls it 100%. Treat empty
maps as "not loaded" and fail. `vitest related` also misses tests that reach
a component only through a route or a dynamic import (the setup step pages),
so name the test files explicitly for those.

**Svelte fallbacks that can't run.** A `$derived(x ? f(x) : [])` that is only
read once `x` has loaded leaves its fallback arm unreachable. Work the value
out inside the loaded branch (`{@const v = f(x)}`), or let the function take
the possibly missing value through `x?.field`. V8 does not count optional
chaining as a branch. Svelte also compiles `<option value>` and `{expr}` into
`?? ''` arms that pin headers name rather than chase.

**Why:** the owner wants the guidelines applied to existing code, with SonarQube
for IDE as the complexity authority.

**How to apply:** for new work, use the same endpoint and the coverage rules
above to meet the CLAUDE.md gate. Related: [[project-backend-coverage-push]].
