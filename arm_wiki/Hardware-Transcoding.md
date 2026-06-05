# Hardware Transcoding

Transcoding video with HandBrake is the most CPU-intensive thing ARM does. If
your host has an Intel iGPU (Quick Sync), an AMD GPU (VAAPI), or an NVIDIA GPU
(NVENC), you can offload it to the GPU — much faster, at a modest quality cost
versus a slow CPU encode.

> **You do not build HandBrake or install codecs by hand in v3.** The transcode
> image already ships HandBrake + ffmpeg with the QSV/VAAPI/NVENC encoders. All
> you do is (1) expose the GPU to the stack via the **GPU overlay**, and on
> NVIDIA (2) install the NVIDIA Container Toolkit on the host. The backend then
> probes for GPUs at startup and the dispatcher hands each transcode job a free
> one.

## Is my GPU supported?

| Vendor | Path | Minimum hardware |
|---|---|---|
| **Intel** | Quick Sync (QSV) | 6th-gen Core (Skylake) or newer with the Quick Sync feature set. |
| **AMD** | VAAPI | Radeon RX 400 / 500, Vega / Radeon VII, Navi series or newer. |
| **NVIDIA** | NVENC | GeForce GTX Pascal (1050+) or RTX Turing (1650+, 2060+). Older cards need driver ≥ 418.81. |

CPU-only hosts need none of this — the base stack transcodes on CPU with zero
configuration.

## Enabling the GPU overlay

GPU support lives in a separate compose file, `docker-compose.gpu.yml`, kept out
of the base compose so CPU-only hosts get clean startup. (Putting
`runtime: nvidia` in the base file would make `docker compose up` fail outright
on any host without the NVIDIA toolkit.) You opt in two ways:

**Recommended — set it once in `.env`.** Uncomment this line in `~/arm/.env`:

```bash
COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml
```

Now a plain `docker compose up -d` loads both files automatically — no `-f`
flags to remember.

**Or per command:**

```bash
cd ~/arm
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

What the overlay does:

- Mounts `/dev/dri` into the backend so it can detect **Intel QSV** and **AMD
  VAAPI** (it lists `/dev/dri/renderD*` and reads each card's vendor ID —
  `0x8086` Intel, `0x1002` AMD).
- Enables the **NVIDIA runtime** and reserves the GPU devices so the backend can
  detect **NVENC** via `nvidia-smi`.

## NVIDIA: install the Container Toolkit first

`runtime: nvidia` only works if the host has the **NVIDIA Container Toolkit**,
which injects the driver libraries into containers. Without it, `docker compose
up` fails with *"could not select device driver nvidia"*. The installer warns
you when it detects an NVIDIA GPU without the toolkit registered. Install it:

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
packages — the `/dev/dri` mount is enough.

## Trimming the overlay for your hardware

The generated `docker-compose.gpu.yml` assumes a mixed host. If you only have
one vendor, trim it:

- **Intel/AMD only (no NVIDIA):** delete the `runtime: nvidia` line and the
  whole `deploy:` block. Keep the `/dev/dri` device mount.
- **NVIDIA only (no Intel/AMD):** delete the `devices: [/dev/dri:...]` line.
- **Mixed:** leave everything; the probe handles each path independently.

To pin a specific GPU instead of exposing all of them, replace `count: all`
with `device_ids: ["0"]` under the NVIDIA reservation.

## Verifying it worked

After bringing the stack up with the overlay, the backend probes for GPUs at
startup. Confirm detection in the UI's **Diagnostics** page, or check the
backend log:

```bash
docker compose logs arm-backend | grep -i gpu
```

Transcode presets default to *prefer GPU, queue if all GPUs are busy, fall back
to CPU only if no GPU advertises that codec* — so once a GPU is detected, eligible
jobs use it automatically. If nothing is detected, ARM transcodes on CPU and
everything still works.

See [Troubleshooting § GPU isn't detected](Troubleshooting#gpu-isnt-detected) if
the probe comes up empty.
