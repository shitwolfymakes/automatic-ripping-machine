---
name: feedback_ui_port_8081
description: ARM v3 UI ports - ui-neu (the supported UI) is 8082, the deprecated Vue SPA is 8081, the backend is 8080; the installer is canonical for deployment values
metadata:
  type: feedback
---

Host ports for ARM v3 (all HTTPS, container `443` for the UIs):

- **ui-neu (SvelteKit) on `https://localhost:8082`.** The supported,
  tester-facing UI. User-facing text (setup-dev next steps, docs, bug triage)
  points here first.
- **Vue SPA on `https://localhost:8081`.** Deprecated (2026-09-09); kept only
  until `services/ui/` is removed. Do not "reconcile" 8081 to 8080: 8080 was
  v2's old HTTP port, and the cutover step to "move back to 8080" was
  explicitly dropped (see [08-v2-isolation-and-cutover.md](08-v2-isolation-and-cutover.md) § Ports).
- **Backend API on `https://localhost:8080`** (health at `/api/health`).

**Why:** When deployment values (ports, paths, hostnames) disagree across the
repo, the **installer** is the source of truth: it produces the real,
TLS-secured deployment users run. Updated 2026-09-26: this note used to say
"the UI is 8081", which predates ui-neu replacing Vue.

**How to apply:** Reconcile *to* what `install.sh` generates, not away from it
(install.sh itself is legacy and frozen). When a message or doc says "open the
UI", it means ui-neu on 8082.
