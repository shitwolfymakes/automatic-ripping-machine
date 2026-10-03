---
name: feedback_ui_port_8081
description: ARM v3 UI ports - ui-neu (the only UI, image arm-ui) is 8081 everywhere, the backend is 8080; the Vue SPA was removed 2026-09-27; the installer is canonical for deployment values
metadata:
  type: feedback
---

Host ports for ARM v3 (all HTTPS):

- **UI (ui-neu, SvelteKit) on `https://localhost:8081`** (container `443`),
  everywhere: the installer, `docker-compose.yml.example`, `setup-dev.sh`, and
  the docs. Its compose service and image are both `arm-ui`; the source stays
  in `services/ui-neu/`. The Vue SPA (`services/ui/`) was removed 2026-09-27,
  so there is no second UI and no 8082. Do not "reconcile" 8081 to 8080: 8080
  was v2's old HTTP port, and the cutover step to "move back to 8080" was
  explicitly dropped (see [08-v2-isolation-and-cutover.md](08-v2-isolation-and-cutover.md) § Ports).
- **Backend API on `https://localhost:8080`** (health at `/api/health`).

**Why:** When deployment values (ports, paths, hostnames) disagree across the
repo, the **installer** is the source of truth: it produces the real,
TLS-secured deployment users run. install.sh already generates `arm-ui` on
`8081:443`, so publishing ui-neu under the `arm-ui` image name moved installed
deployments to ui-neu with no installer change.

**How to apply:** Reconcile *to* what `install.sh` generates, not away from it
(the installer is `deploy/armctl.sh`; root `install.sh` is its bootstrap). When a message or doc says "open the
UI", it means ui-neu on 8081. Any 8082 left in the tree is an arbitrary example
(e.g. test origins in `test_ws_origin.py`), not a UI port.
