# Hardware Transcoding

Transcoding video with HandBrake is the most CPU-intensive thing ARM does. If
your host has an Intel iGPU (Quick Sync), an AMD GPU (VAAPI), or an NVIDIA GPU
(NVENC), you can offload it to the GPU: much faster, at a modest quality cost
versus a slow CPU encode.

> **You do not build HandBrake, install codecs, or edit compose files by hand in
> v3.** The transcode image already ships HandBrake + ffmpeg with the
> QSV/NVENC encoders built in, plus an ffmpeg VAAPI path for AMD. The installer
> detects your GPUs automatically and wires them up; on NVIDIA it also offers
> to install the NVIDIA Container Toolkit. The Backend then probes each device
> with a real test encode and only ever claims one that verified.

## Is my GPU supported?

| Vendor | Path | Minimum hardware |
|---|---|---|
| **Intel** | Quick Sync (QSV) | Gen12+ (Alder Lake / N-series) or newer. Gen 9 through 11 (Skylake through Ice Lake) have no working QSV runtime on this image; see [Why a device verifies nothing](#why-a-device-verifies-nothing) below. |
| **AMD** | VAAPI (via Mesa, ffmpeg) | Radeon RX 400 / 500, Vega / Radeon VII, Navi series or newer, with the `amd` transcode image variant built. |
| **NVIDIA** | NVENC | GeForce GTX Pascal (1050+) or RTX Turing (1650+, 2060+). Older cards need driver >= 418.81. |

CPU-only hosts need none of this: the base stack transcodes on CPU with zero
configuration.

## The encoder catalog

A transcode preset names one **encoder** (not a codec plus a hardware
preference like older builds). ARM derives everything else, including whether
to claim a GPU, from that id:

| Encoder id | Meaning | Engine | Runs on |
|---|---|---|---|
| `preset` | HandBrake preset's own encoder (used as-is) | HandBrake | whatever the preset itself asks for |
| `cpu_h264` / `cpu_h265` / `cpu_av1` | Software encode, never queues for a GPU | HandBrake (x264 / x265 / SVT-AV1) | CPU |
| `any_h264` / `any_h265` / `any_av1` | Prefer a verified GPU; fall back to CPU if none exists on this host | resolved at claim time | best verified GPU, else CPU |
| `qsv_h264` / `qsv_h265` / `qsv_av1` | Intel Quick Sync only | HandBrake | a verified Intel QSV device |
| `nvenc_h264` / `nvenc_h265` / `nvenc_av1` | NVIDIA NVENC only | HandBrake | a verified NVIDIA device |
| `vaapi_h264` / `vaapi_h265` / `vaapi_av1` | AMD (Mesa VAAPI) only | ffmpeg | a verified AMD device |

The preset editor's **Encoder** field is fed from `GET /api/encoders`, which
groups these the same way: HandBrake preset's own, CPU, Any GPU, then one
group per vendor. An encoder your deployment currently cannot satisfy shows
disabled with the reason (for example, "no enabled device has verified
`qsv_h265`").

## Eligibility and the claim

A GPU row is **eligible** for a codec only when it is enabled, has been
probed at least once, and that probe actually verified the codec. An
unprobed device is listed in Settings but can never take GPU work.

What happens when a transcode task reaches the front of the queue depends on
the preset's encoder:

- **`preset` / `cpu_*`**: always spawns on CPU, never waits on hardware.
- **`any_<codec>`**: picks the best eligible device (NVIDIA, then Intel, then
  AMD, then device path) if one is free. If every eligible device is busy,
  the task queues. **If no eligible device exists at all on this host, the
  task runs the CPU encoder for that codec** instead of waiting, so a
  built-in preset that defaults to `any_h265` keeps working on a CPU-only box.
  The HandBrake preset's own settings (scaling, filters, audio) apply when
  the job runs on the CPU, NVENC or QSV, but not when it lands on an AMD
  (VAAPI) device, which encodes through ffmpeg instead.
- **`<vendor>_<codec>`** (a specific `qsv_*`, `nvenc_*` or `vaapi_*` id): picks
  a free eligible device of that vendor if one exists; if all are busy, the
  task queues. If **no** device of that vendor has verified the codec, the
  task is refused rather than silently running elsewhere:
  - **At apply time**, the API returns `422` and never creates the task.
  - **If a device stops being eligible while the task is already queued**
    (disabled, removed, or re-probed without that codec), the task fails
    with `last_error`:

    ```text
    no enabled device has verified <encoder id>; re-probe or enable it in Settings > GPUs
    ```

    It's retryable through the normal retry path once the device is fixed.
- If every eligible device for an encoder (including an `any_*` pick) is
  in the middle of being probed right now, the task queues rather than
  falling back to CPU. It is only unavailable for that tick.
- If no device is eligible yet, but an enabled device that could serve the
  encoder has never been probed and its probe is scheduled or running (the
  boot pass, a re-probe, or enabling the row), the task queues until that
  probe finishes, for `any_*` and vendor-pinned encoders alike, and a
  vendor-pinned apply is not refused meanwhile. Once the probe is done, the
  rules above apply to its result. A never-probed device that no probe is
  scheduled for does not hold work back.
- A preset whose stored encoder id no longer exists in the catalog (a stale
  row from a removed encoder) is refused at apply and fails at dispatch with
  `preset <id> has unknown encoder '<value>'`. Only that task fails; siblings
  in the same session keep running.

## The per-device probe

Capability comes from a **real test encode on the actual container image**,
not from an install-time `HandBrakeCLI --help` scrape. The Backend spawns a
short-lived probe container per GPU row (through the same docker client the
dispatcher uses, so a remote transcode host is covered too), generates a
2-second test clip, and tries every catalog GPU encoder of that row's vendor
against it. Whatever encodes cleanly becomes that row's verified list.

**When a probe runs:**

- **At Backend boot**, a background pass probes every enabled row that was
  never probed, or whose last probe verified nothing, one row at a time. This
  never blocks startup. Every never-probed row the pass will visit counts as
  awaiting its probe from the moment the Backend starts, so work that such a
  row could serve queues until that row's probe finishes (see above) instead
  of running on CPU or failing. This is what happens on the first boot after
  an upgrade, when every row starts unprobed.
- **When you enable a never-probed row** in Settings > GPUs, its probe is
  scheduled in the background.
- **On demand**, from Settings > GPUs: **Re-probe** on one row, or
  **Re-probe all**. Rows refresh live over the `gpu.probed` WebSocket event.

A row already running a transcode, or mid-probe, is skipped by both a new
probe request and the dispatcher's claim, so a probe and a real job never
collide over the same device.

### Why a device verifies nothing

"Verified nothing" is an explicit, visible state (not the same as "never
probed"): the row shows a probed timestamp but an empty verified list, plus
`probe_error` when the probe process itself failed. The two most common
causes:

- **AMD**: HandBrakeCLI is in fact compiled with its own AMD encoder
  (VCE/AMF), the same as QSV and NVENC, but it never runs in any of these
  images: AMD's proprietary AMF runtime isn't packaged for Debian, so it
  isn't installed anywhere, and supporting it is deferred pending hardware
  testing. That's why the AMD path is ffmpeg through Mesa's VAAPI driver
  instead. It needs the `amd` transcode image variant (`mesa-va-drivers`)
  actually present on the docker host; on the base image alone, an AMD row
  verifies nothing. See [Image variants](#image-variants) below.
- **Intel Gen 9 through 11** (Skylake through Ice Lake): these need Intel's
  legacy Media SDK runtime (`libmfx1`), which trixie no longer ships and this
  image does not install. These rows verify nothing on any current image;
  the built-in `any_*` presets still run on CPU for them.

A probe that could not run at all (rather than running and verifying
nothing) records one of these in `probe_error`:

- `probe could not create its test clip: ...`, meaning the container itself
  couldn't generate ffmpeg's test source.
- `probe misconfigured: ...`, meaning the probe was started without the
  vendor or device it needed.
- otherwise, a message telling you to rebuild or pull the image, plus a tail
  of the container's stderr: usually a transcode image that predates the
  `--probe-device` worker mode.

## Image variants

Vendor userspace lives in per-vendor image targets, not the base image:

| Target | Adds | Serves |
|---|---|---|
| `base` | HandBrake (built with QSV/NVENC enabled), system ffmpeg | CPU encoders, NVENC (NVIDIA's driver + Container Toolkit inject the rest at run time) |
| `intel` | `intel-media-va-driver-non-free`, `i965-va-driver`, `libvpl2`, `libmfx-gen1.2` | Intel QSV |
| `amd` | `mesa-va-drivers` | AMD, through ffmpeg's VAAPI encoder |

`devtools/setup-dev.sh` builds the `intel` and/or `amd` variant only for the
vendors it detects on this host (neither with `--ripper-only`). Production
CI builds and publishes all three.

**Naming convention**: the variant tag is `<ARM_TRANSCODE_IMAGE>` with its
tag suffixed `-intel` / `-amd`, for example `arm-transcode:latest-intel`. The
Backend derives this automatically for a QSV or VAAPI claim; NVENC and CPU
spawns always use the base image (there is no NVENC variant to derive, since
NVENC needs nothing baked in beyond the HandBrake build).

**Setting `ARM_TRANSCODE_IMAGE` does not rename the compose-built variants.**
They stay `arm-transcode:latest-intel` / `arm-transcode:latest-amd` unless
you also set `ARM_TRANSCODE_IMAGE_QSV` / `ARM_TRANSCODE_IMAGE_VAAPI` to
match. An explicit per-vendor override always wins:

```bash
ARM_TRANSCODE_IMAGE_QSV=myregistry/arm-transcode:v3.1.0-intel
ARM_TRANSCODE_IMAGE_VAAPI=myregistry/arm-transcode:v3.1.0-amd
ARM_TRANSCODE_IMAGE_NVENC=myregistry/arm-transcode:v3.1.0-nvenc
```

**When the derived or overridden variant is missing** (not present on the
docker host and no override), the Backend pulls it on demand before a spawn
or a probe. A pull that fails is remembered for 10 minutes so a spawn or
probe doesn't retry a dead registry every tick; every attempt in that window
falls back to the base image, where a QSV or AMD device verifies nothing
until the variant is actually available. The Diagnostics page never
triggers a pull itself: it only reports whether a needed variant is present
locally, will be pulled on first use, or recently failed to pull.

### Building variants on a remote transcode host

If `ARM_TRANSCODE_DOCKER_HOST` points at a remote docker daemon (a separate
GPU box), that daemon needs its own copy of the variant images; the Backend
never ships one over. Build them there directly against the remote docker
socket:

```bash
DOCKER_HOST=ssh://user@transcoder-host docker build \
    --target intel -t arm-transcode:latest-intel .
DOCKER_HOST=ssh://user@transcoder-host docker build \
    --target amd -t arm-transcode:latest-amd .
```

Run this from a checkout of this repo (the build context needs
`services/transcode/Dockerfile` and the workspace it copies in), after any
change to the transcode image or on the remote host's own upgrades.

## Enabling GPU transcoding

There's nothing to enable by hand beyond the image build above: **the
installer detects your GPUs and wires them up.** When you run `install.sh`
(or `devtools/setup-dev.sh` for a dev checkout) it enumerates your hardware:

- **Intel QSV / AMD VAAPI**: lists `/dev/dri/renderD*` and reads each card's
  vendor ID (`0x8086` Intel, `0x1002` AMD).
- **NVIDIA NVENC**: runs `nvidia-smi -L`, one entry per GPU.

The result is written to the `ARM_GPUS` line in `~/arm/.env` as a JSON
array, for example:

```bash
ARM_GPUS=[{"vendor":"qsv","device_path":"/dev/dri/renderD128","encoder_kinds":[]}]
```

`encoder_kinds` here is only a hint for the initial seed; every seeded row
starts with `encoder_kinds: []` and `probed_at: NULL`, and the Backend's
boot probe pass verifies it for real on first start. The Backend reads
`ARM_GPUS` at startup to populate its GPU table (only when that table is
still empty), and the dispatcher passes the right device into each
short-lived transcoder container it spawns. No overlay file, no
`COMPOSE_FILE` juggling, no GPU access on the Backend itself.

> **Re-run the installer after any GPU or driver change** (new card, driver
> upgrade) so `ARM_GPUS` is refreshed. Re-probe the affected row from
> Settings > GPUs afterward (or restart the Backend, which probes any
> newly-unprobed row on boot).

A ripper-only dev checkout (`devtools/setup-dev.sh --ripper-only`) skips this
detection entirely and writes `ARM_GPUS=[]` plus `ARM_TRANSCODE_CAPABLE=false`,
since a ripper-only box never spawns a local transcoder to hand a device to.
See [Configuring ARM § Ripper-only installs](Configuring-ARM#ripper-only-installs).

## NVIDIA: the Container Toolkit

NVENC needs the **NVIDIA Container Toolkit** on the host so the docker daemon
can pass GPU devices into the transcoder. When `install.sh` detects an NVIDIA
GPU without the toolkit registered, **it offers to install and configure it
for you** on Debian/Ubuntu hosts (with a confirmation prompt). On other
distros it prints the steps. To do it manually:

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

You also need a working NVIDIA driver on the host (download from
<https://www.nvidia.com/en-us/drivers/>). Intel and AMD need no extra host
packages beyond the matching image variant above; the render-node device is
enough.

## Verifying it worked

Check **Settings > GPUs** in the UI: each row shows its verified encoders,
when it was last probed, and any probe error, with **Re-probe** available per
row. You can also check the backend log:

```bash
docker compose logs arm-backend | grep -i "gpu probe"
```

Transcode presets built around `any_h264` / `any_h265` / `any_av1` prefer a
verified GPU, queue if every matching device is busy, and fall back to CPU
only if this host has no eligible device for that codec at all. A preset
pinned to a specific vendor (`qsv_h265`, and so on) never silently runs
elsewhere: it waits for that hardware, or is refused with a named reason. If
nothing is detected, ARM transcodes on CPU and everything still works.

See [Troubleshooting § GPU isn't detected](Troubleshooting#gpu-isnt-detected) if
detection comes up empty.
