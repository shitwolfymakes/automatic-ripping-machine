---
name: feedback_nvenc_header_driver_pin
description: Transcode image's NVENC must be pinned to nv-codec-headers compatible with the distro-shipped NVIDIA driver; coupling spans 3 files.
metadata:
  type: feedback
---

The transcode image builds HandBrakeCLI from source with `--enable-nvenc`. The
host NVIDIA driver is **injected at runtime** by the NVIDIA Container Toolkit
(never installed in the image); what the image controls is which **NVENC API
version the build requires**, via the `nv-codec-headers` version HandBrake's
contrib system fetches. If headers demand a newer API than the host driver
provides, every GPU encode dies `rc=3` at `avcodec_open` ("Driver does not
support the required nvenc API version") — HandBrake scans the title fine (no GPU
needed) then fails the instant it opens the encoder.

HandBrake 1.11.x defaults to nv-codec-headers **13.0.19.0 → needs driver 570+**.
But v3 targets Linux + Docker, and stable distros lag: **Debian 13 (trixie)
ships driver 550** from `nvidia-driver`, and going off-package is not advisable.
So [services/transcode/Dockerfile](../../services/transcode/Dockerfile) re-pins
the contrib `nv-codec-headers` (sed on `contrib/nvenc/module.defs`, version +
sha256, with a `grep` assert) to **12.1.14.0** — accepted by the bundled FFmpeg
8.0.1 (floor `ffnvcodec >= 12.1.14.0`) and requiring only driver **530.41.03**.
NVENC is backward-compatible, so the binary still runs on 570+ hosts; ARM only
uses h264/h265, which 12.x fully covers.

**Why:** without the pin, HW transcode is broken on the single supported
platform ([[project_linux_docker_only]]). **How to apply:** when bumping
`HANDBRAKE_VERSION`, re-verify (a) the bundled FFmpeg's `ffnvcodec >=` floor in
its `configure`, and (b) the chosen header tag's min driver (nv-codec-headers
`README` at that tag), then keep three things in lockstep: `NVCODEC_VERSION` /
`NVCODEC_SHA256` in the Dockerfile, and `ARM_NVENC_MIN_DRIVER` (the header's
driver floor, currently 530) in **both** [install.sh](../../install.sh) and
[devtools/setup-dev.sh](../../devtools/setup-dev.sh). That constant gates the
host-side GPU probe: a too-old driver is dropped from `ARM_GPUS` (warn to stderr,
never stdout — it would corrupt the JSON) so the host cleanly falls back to CPU
instead of failing every task. The gate only runs at install/setup time, so
re-run setup after a driver change. Separately, encoder errors land in
`transcode_tasks.last_error` via handbrake.py's stderr tail (1000 lines) — keep
the tail from the **end**, the decisive NVENC line prints last.
