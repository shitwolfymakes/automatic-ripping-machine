---
name: Ripper uses one makemkvcon invocation per disc, not per title
description: v3 ripper deliberately invokes `makemkvcon mkv ... all <outdir>` once per disc; per-title invocations (`title=N`) were tried and reverted because they let the drive idle between titles, which surfaced kernel autosuspend + SCSI NOT_READY failures on USB Blu-ray drives.
type: feedback
---

The DVD/BD rip flow shells out exactly once per disc: `makemkvcon mkv -r --progress=-stdout --minlength=N dev:<device> all <outdir>`. Per-title outcomes are reconstructed from the robot stream (`MSG:5018`/`MSG:5003` + post-exit `title_tNN.mkv` walk). **Do not re-introduce per-title invocations** even if the per-track DB attribution looks cleaner that way.

**Why:** Phase 3 originally shipped a Python loop calling `rip_title(title_index=N)` once per selected title. Between titles the drive briefly idled; on the user's LG BP50NB40 USB-BD drive (and likely other USB-BD drives), the kernel would autosuspend the device or the medium would report SCSI `NOT_READY: LOGICAL UNIT IS IN PROCESS OF BECOMING READY` for 30–60s. Four production rips over a week ended in partial failures or hangs. Each fix shipped (`_wait_for_drive_ready`, the `CDROM_DRIVE_STATUS` ioctl, then a `verify_read=True` real-`os.read()` probe) was a bandaid. v2 never had this failure mode because it ran `makemkvcon mkv ... all` exactly once per disc — drive stays open, no gap, no autosuspend window.

**How to apply:**
- Any rip mode (TRACKS, MAIN_FEATURE, ARCHIVE) goes through `rip_disc` with the appropriate `--minlength`. TRACKS-mode rips of a few selected titles waste IO ripping unselected ones (deleted post-rip). The user accepted that tradeoff explicitly.
- The host-side baseline lives at `ARM_MIN_LENGTH_SECONDS` (default 600); `Session.overrides_json["min_length_seconds"]` overrides per-rip. Manual rips inherit the baseline — no per-rip UI override yet.
- `drive_status.probe_drive_media` is ioctl-only. **Do not re-add `verify_read`** — its only caller (the between-titles wait) no longer exists. The probe is still used by the heartbeat task and the manual-trigger pre-check, neither of which needs it.
- If a future failure mode looks like "drive misbehaves between rips" (cold-start autosuspend, etc.), that's a separate concern from the within-rip gap this phase fixed; explore host-side `usbcore.autosuspend=-1` or per-device `power/control=on` rules before adding any in-process polling.

The full reversion narrative lives at [v3/docs/plans/MASTER_IMPLEMENTATION_PLAN.md § Phase 15.5](../../v3/docs/plans/MASTER_IMPLEMENTATION_PLAN.md). The original `rip_title` and `_wait_for_drive_ready` code can be recovered from git history before commit `<this-commit>` if comparison context is ever needed.
