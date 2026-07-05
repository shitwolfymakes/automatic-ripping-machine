---
name: feedback_entrypoint_guard_mountpoints
description: The _common entrypoint writability guard gates only mountpoints, not any present dir — incidental base-image dirs like the ripper's /media must be skipped
metadata:
  type: feedback
---

The shared container entrypoint (`services/_common/docker-entrypoint.sh`,
`require_writable()`) **verifies** the drop-uid (`arm`, PUID) can write each data
dir and **fails fast** instead of chowning — the v3 invariant (never chown a
user-mounted volume; see [[feedback_ripper_unprivileged_no_mount]] and
`docs/arch/06-deployment.md`). It loops `/logs /raw /media`.

**Why:** the original guard skipped a dir only when absent (`[[ -d "$d" ]]`).
But some base images ship an incidental **root-owned `/media`** that a service
never mounts — the ripper writes rips to `/raw`, not `/media`. Present-but-not-
mounted `/media` (owner `0:0`) then tripped the guard → `FATAL: /media is not
writable … dir owner is 0:0` → crash-loop on a *correctly configured* ripper.

**Rule:** gate only **actual mountpoints**. A mounted data volume is always a
mountpoint; an incidental image dir is not. The guard now does
`"${MOUNT_TEST[@]}" "$d" || return 0` after the `-d` check, where
`MOUNT_TEST=(mountpoint -q)` by default. `MOUNT_TEST` is an array seam with a
`declare -p` guard mirroring `WRITE_TEST`, so `test-entrypoint-guard.sh` can stub
it (`MOUNT_TEST=(true)` for temp dirs; `MOUNT_TEST=(false)` exercises the skip).

**Why an array seam, not `command -v mountpoint`:** the test sources the
entrypoint via `ARM_ENTRYPOINT_SOURCE_ONLY=1` and drives `require_writable`
against `mktemp -d` dirs, which are not mountpoints — without the stub every
test case would skip. Keep the seam.

Fixed on Tier-26 (wolfy #41, `feat/tier25-remote-transcode-offload`), cascaded up
the stack. Diagnosed live on hifi when a lint-clean redeploy crash-looped the
ripper. See [[project_hifi_v3_deploy]].
