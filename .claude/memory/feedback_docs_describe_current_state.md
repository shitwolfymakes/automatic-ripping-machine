---
name: feedback-docs-describe-current-state
description: Docs, memory entries, comments and CLAUDE.md describe what is true now; a behavior change replaces the old description instead of annotating it
metadata:
  type: feedback
---

Docs, memory entries, code comments and `CLAUDE.md` describe the current state.
When behavior changes, replace the old description with the new one instead of
annotating it ("DONE", "no longer", "used to", "until X lands", "the old
installer"). History belongs in git, the spec and plan files
(`docs/superpowers/`, `docs/plans/`) and `CHANGELOG.md`.

**Why:** a developer reading the docs needs what is true now; transition notes
age into noise. The owner stated this on 2026-10-09, after the installer
rewrite left "DONE" and "no longer" notes behind.

**How to apply:** when a change turns a sentence into a transition note, rewrite
it as the current fact, or delete it if nothing current remains. A finished
item in a follow-up list is removed from the list, not marked done. Sentences
about ARM v2 as a separate, frozen product are current facts and stay.
