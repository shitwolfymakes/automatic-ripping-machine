---
name: uineu-preflight-endpoint-mismatch
description: OPEN BUG — ui-neu's SystemHealth panel + first-run ReadinessCheckStep call POST /api/system/preflight(/fix), which no backend line serves; port them to GET /api/system/diagnostics
metadata:
  type: project
---

`services/ui-neu/frontend/src/lib/api/system.ts` still carries the neu-era
client: `runPreflight()` → `POST /api/system/preflight` and `fixPreflight()`
→ `POST /api/system/preflight/fix`. No v3 backend line has ever served those
(the old router had only `GET /preflight`; since the 2026-07-16 neu-ports
absorb, every line serves `GET /api/system/diagnostics` instead — no fix
endpoint by design: the backend heals silently via `ensure_roots`, and
diagnostics is read-only).

Consumers: `settings/SystemHealth.svelte` and `setup/ReadinessCheckStep.svelte`
— both catch the failure and show "Failed to run health checks", so the
breakage is quiet. Pre-existing on deploy/hifi (NOT a regression from the
neu-ports reconciliation).

**Fix when picked up:** point system.ts at `GET /api/system/diagnostics`,
adapt `PreflightResult` → `SystemDiagnosticsResponse` (checks + paths, no
`fixable`/fix flow), drop the Fix button, author on the PR line.
