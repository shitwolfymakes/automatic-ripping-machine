---
name: armv3-tracking-fork
description: uprightbass360/arm-v3 is the tracking repo for the v3 PR stack (issues, labels, defect register, recut top-of-stack branches); PRs still merge via shitwolfymakes
metadata:
  type: project
---

Since 2026-10-02, `uprightbass360/arm-v3` (local remote `armv3`) is the
tracking repo for the stacked v3 PRs. The 26-PR stack (#61 → #102), #104,
the off-stack branches and `integration/all-prs-3` are mirrored there under
the same branch names. The PRs themselves stay open on
`shitwolfymakes/automatic-ripping-machine` (`origin`), which is where they
merge; that fork has issues disabled.

Defect tracking lives on arm-v3: labels `defect`, `sev/S1..S4`,
`status/{open,fixed-later,move-down,untested-needs-hardware}`,
`area/{backend,ripper,transcode,ui-neu,common,migrations,devtools,ci,docs}`.
The committed register is `docs/plans/DEFECT_REGISTER.md` (D-xxx ids, same
convention as [[project_automation_gap_register]]); one arm-v3 issue per row.

On 2026-10-03 the integration-only commits were re-cut onto stack branches on
arm-v3 (draft PRs #122–#128 there, none on wolfy yet). Top of the stack:
`feat/iso-source-rip` (#101) → `feat/iso-udf-7zip` (7-Zip UDF reader + merge
of #82; fixes D-100) → `feat/first-run-setup` (#102, rebased) →
`chore/stack-convergence` (merges #95/#96 and #104, plus two small commits) →
`fix/identity-followups` → `fix/ui-neu-nav-a11y` → `feat/live-rip-progress` →
`test/backend-coverage-100`. Off-stack `fix/pin-makemkv-1.18.4` carries three
commits (#103 completed). Two tests existed only inside the integration
branch's own merge resolutions and were re-homed as explicit commits. The
Playwright visual-suite refresh was deliberately NOT re-cut (owner: test
artifacts). Method: cherry-pick with eof-append / keep-both resolution, merge
conflicts resolved from the integration tip, verified by tree-diff against
`integration/all-prs-3` plus pytest.

**Why:** the owner wanted more latitude than the wolfy fork allows (issues,
labels, projects, freedom to experiment) while still landing changes there.

**How to apply:** push with `env -u GITHUB_TOKEN git push armv3 ...` (see
[[github-push-env-token]]). Re-mirror stack branches with
`--force-with-lease` after fetching `armv3`; check that arm-v3 has no unique
commits first. File defects as arm-v3 issues keyed by D-id, never as
comments on the wolfy PRs. Any commit made directly on
`integration/all-prs-3` is a liability: cut it onto a stack branch promptly.
