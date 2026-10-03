---
name: feedback_setup_reuses_settings_components
description: First-run setup walkthrough must compose the same components/field metadata as Settings - never re-implement a setting in setup
metadata:
  type: feedback
---

The first-run setup walkthrough (and any other secondary surface that edits settings) composes the **same** shared components and `CONFIG_FIELD_META` field metadata that Settings uses. It never hand-writes inputs, labels, validation or key-test logic for a setting.

**Why:** the owner said (2026-10-01) "we should re-use components so that we are implementing existing features instead of having to update initial setup on all changes". A parallel implementation drifts every time a setting changes.

**How to apply:**
- Config fields in a setup step are selected through `ConfigFieldMeta.setup_step` and rendered through `SchemaConfigForm step=... deferred`.
- Feature UIs (drives, GPUs, health checks, password, notification channel) are the Settings components, with a `variant` or `deferred` + `save()` where needed.
- When the setup design improves a visual, change the shared component and let Settings adopt it.
- Setup-only code is shell, stepper, footer, checklist and step glue.

Spec: `../arm-ai/arm-v3/docs/superpowers/specs/2026-10-01-first-run-setup-design.md` §7. Related: [[feedback_standard_ui_patterns]].
