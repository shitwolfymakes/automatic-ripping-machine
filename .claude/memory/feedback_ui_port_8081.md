---
name: feedback_ui_port_8081
description: ARM v3 UI port is 8081; the installer is the canonical source of truth for deployment values
metadata:
  type: feedback
---

The ARM v3 UI is served on host port **8081** (mapped to container `443` over HTTPS). Keep `install.sh` (generated compose + `ARM_ALLOWED_ORIGINS`), the dev `docker-compose.yml`, `.env.example`, and all docs on `https://localhost:8081`. Do **not** "reconcile" this to 8080 — 8080 was v2's old HTTP port, and the cutover plan's step to "move back to 8080" was explicitly dropped (see [08-v2-isolation-and-cutover.md](08-v2-isolation-and-cutover.md) § Ports).

**Why:** When deployment values (ports, paths, hostnames) disagree across the repo, the **installer** is the source of truth — it produces the real, TLS-secured deployment users actually run, and the whole CA/HTTPS security build-out lives in that path. The owner runs ARM via a real dev install on `https://localhost:8081`; a dev-compose value or a planning doc does not outrank the installed deployment.

**How to apply:** Reconcile *to* what `install.sh` generates, not away from it. If a value must change, change the installer first and let everything else follow.
