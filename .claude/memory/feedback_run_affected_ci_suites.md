---
name: feedback-run-affected-ci-suites
description: Before pushing a change that alters a CI job's toolchain (Node/Python version, flags), run that job's suite locally on the new toolchain; vitest broke on Node 26
metadata:
  type: feedback
---

A change to how a CI job runs (its Node or Python version, a flag, an env var)
must be verified by running that job's suite locally on the new toolchain, not
only the suites whose files changed.

**Why:** 2026-10-20, D-225 moved CI from Node 24 to 26 (`.nvmrc`); the local box
had Node 24 and vitest was not run, and CI then failed 136 vitest tests because
Node 25+ ships a global `localStorage` that shadows jsdom's. Fixed with
`execArgv: ['--no-experimental-webstorage']` in `vitest.config.ts`.

**How to apply:** run a different Node without installing it via
`npx -y -p node@26 -- node node_modules/vitest/vitest.mjs run` in
`services/ui-neu/frontend`. Check `gh pr checks` after every push.
