---
name: project_vue_ui_deprecated
description: Vue SPA (services/ui) is removed; ui-neu (SvelteKit, image arm-ui) is the only UI, on 8081
metadata:
  type: project
---

Owner directive (2026-09-09): Vue is no longer a supported system for v3.
The Vue 3 SPA at `services/ui/` was removed on 2026-09-27; **`services/ui-neu/`**
(SvelteKit / Svelte 5, published as the `arm-ui` image) is the only UI and now
serves on **8081** (see [[feedback_ui_port_8081]]).

**Why:** owner decision during bug-report triage; ui-neu was already the
tester-facing UI on the wolfy RC line.

**How to apply:**
- A bug report about "the UI" means ui-neu. Don't propose Vue patches or cite
  `services/ui/` paths; a leftover `services/ui/` dir on disk is untracked
  build debris (node_modules, generated.ts), not live code.
- Contracts ui-neu must honor: OpenAPI-generated types
  (`services/ui-neu/openapi.snapshot.json` + `openapi-drift` CI gate), WS topics
  (`ripper.progress.*`, `transcode.progress.*`, `logs.*`), and the
  `ARM_ALLOWED_ORIGINS` WS origin allowlist handshake.
