# Hardware Transcoding

Transcoding video with HandBrake is the most CPU-intensive thing ARM does. If
your host has an Intel iGPU (Quick Sync), an AMD GPU (VAAPI), or an NVIDIA GPU
(NVENC), you can offload it to the GPU — much faster, at a modest quality cost
versus a slow CPU encode.

> **You do not build HandBrake, install codecs, or edit compose files by hand in
> v3.** The transcode image already ships HandBrake + ffmpeg with the
> QSV/VAAPI/NVENC encoders. The installer **detects your GPUs automatically** and
> wires them up; on NVIDIA it also offers to install the NVIDIA Container Toolkit.
> The dispatcher then hands each transcode job a free GPU. CPU-only hosts need
> nothing at all.

## Is my GPU supported?

| Vendor | Path | Minimum hardware |
|---|---|---|
| **Intel** | Quick Sync (QSV) | 6th-gen Core (Skylake) or newer with the Quick Sync feature set. |
| **AMD** | VAAPI | Radeon RX 400 / 500, Vega / Radeon VII, Navi series or newer. |
| **NVIDIA** | NVENC | GeForce GTX Pascal (1050+) or RTX Turing (1650+, 2060+). Older cards need driver ≥ 418.81. |

CPU-only hosts need none of this — the base stack transcodes on CPU with zero
configuration.

## Enabling GPU transcoding

There's nothing to enable by hand — **the installer detects your GPUs and wires
them up.** When you run `install.sh` (or `devtools/setup-dev.sh` for a dev
checkout) it enumerates your hardware:

- **Intel QSV / AMD VAAPI** — lists `/dev/dri/renderD*` and reads each card's
  vendor ID (`0x8086` Intel, `0x1002` AMD).
- **NVIDIA NVENC** — runs `nvidia-smi -L`, one entry per GPU.

The result is written to the `ARM_GPUS` line in `~/arm/.env` as a JSON array, for
example:

```bash
ARM_GPUS=[{"vendor":"qsv","device_path":"/dev/dri/renderD128","encoder_kinds":["h264","h265"]}]
```

The backend reads `ARM_GPUS` at startup to populate its GPU table, and the
dispatcher passes the right device into each short-lived transcoder container it
spawns. No overlay file, no `COMPOSE_FILE` juggling, no GPU access on the backend
itself.

> **Re-run the installer after any GPU or driver change** (new card, driver
> upgrade) so `ARM_GPUS` is refreshed — detection happens at install time, not on
> every boot.

## NVIDIA: the Container Toolkit

NVENC needs the **NVIDIA Container Toolkit** on the host so the docker daemon can
pass GPU devices into the transcoder. When `install.sh` detects an NVIDIA GPU
without the toolkit registered, **it offers to install and configure it for you**
on Debian/Ubuntu hosts (with a confirmation prompt). On other distros it prints
the steps. To do it manually:

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
packages — the render-node device is enough.

## Verifying it worked

Confirm detection in the UI's **Diagnostics** page, or check the backend log:

```bash
docker compose logs arm-backend | grep -i gpu
```

You can also inspect `ARM_GPUS` in `~/arm/.env` directly — if it's `[]`, the
installer found no GPUs (re-run it after fixing drivers/toolkit).

Transcode presets default to *prefer GPU, queue if all GPUs are busy, fall back
to CPU only if no GPU advertises that codec* — so once a GPU is detected, eligible
jobs use it automatically. If nothing is detected, ARM transcodes on CPU and
everything still works.

See [Troubleshooting § GPU isn't detected](Troubleshooting#gpu-isnt-detected) if
detection comes up empty.
