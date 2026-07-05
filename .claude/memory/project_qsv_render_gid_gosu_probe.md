---
name: qsv-render-gid gosu-drop probe blocker
description: Why QSV/VAAPI hardware encode (and the encoder-capability probe) needs RENDER_GID as an ENV var, not docker --group-add — gosu resets supplementary groups
metadata:
  type: project
---

**QSV/VAAPI HW encode in the transcode container needs the render GID passed as
an ENV var (`RENDER_GID`), NOT a docker `--group-add`.** The entrypoint drops to
`arm` via `gosu`, and **gosu RESETS supplementary groups** — so a Docker
`--group-add <gid>` on the initial (root) process does NOT survive into the `arm`
process. Verified on hifi: `docker run --group-add 993 … id` → `groups=1000(arm)`
(993 gone); `docker run -e RENDER_GID=993 … id` → `groups=1000(arm),993(render-host)`
(entrypoint added it to /etc/group before the gosu drop → survives).

Same gosu-drops-inherited-state class as [[project_entrypoint_home_gosu_paramiko]]
(HOME=/root surviving the drop). Mechanism: `docker-entrypoint.sh` adds `arm` to
`RENDER_GID` in /etc/group BEFORE `exec … gosu arm`; the dispatcher passes
`RENDER_GID` as env (`transcode_dispatcher.py:510-514`) precisely because a docker
group_add wouldn't survive.

**Consequence for the encoder-capability probe (`probe_encoder_caps` in install.sh
/ setup-dev.sh):** it runs `docker run --device /dev/dri … --probe-encoders`
WITHOUT `-e RENDER_GID`, so HandBrake (as `arm`) can't open `/dev/dri/renderD128`
→ QSV/VAAPI stack fails to init → HandBrake hides all `qsv_*`/`vce_*` tokens →
probe returns `{}` (a FALSE negative on every Intel/AMD host). Fix: probe must pass
`-e RENDER_GID=<detect_render_gid>` for the render-node (Intel/AMD) case. NVENC uses
`--gpus all`, unaffected. (Tracked as F-G in
`../arm-ai/arm-v3/docs/reviews/2026-07-05-install-sh-composed-review.md`.)

**hifi N97 hardware truth (task #7):** Intel N97 / Alder Lake-N (`8086:46d1`)
**genuinely supports QSV H.264 AND H.265 HW encode** — `vainfo` inside the real
`arm-transcode:latest` image shows `VAProfileH264Main/High` +
`VAProfileHEVCMain/Main10 : VAEntrypointEncSlice/EncSliceLP`, iHD driver 23.1.1.
So `encoder_kinds:["h264","h265"]` was CORRECT for this chip — there was never a
codec over-claim on the N97. The rc=3 transcode failures were a device-ACCESS
problem (missing render group), not codec advertisement. **No driver update
needed** — QSV works once the render GID reaches the process.
