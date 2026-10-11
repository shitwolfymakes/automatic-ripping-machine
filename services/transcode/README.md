# arm-transcode

Ephemeral, single-task transcoder container. The Backend's
`TranscodeDispatcher` spawns one container per `transcode_tasks` row via
the Docker socket; each container claims its task, runs HandBrake or
ffmpeg against the raw input, writes the output through the
`*.arm-inprogress` atomic-rename flow, and exits.

## Image contents

`python:3.14-slim-trixie` plus:

- `tini` — PID 1; reaps the encoder subprocess.
- `gosu` — drops to PUID/PGID before exec.
- `ca-certificates` — base trust store; the entrypoint merges the
  install's internal CA at boot so HTTPS verifies against the Backend's
  internal cert.
- `handbrake-cli` — primary video encoder.
- `ffmpeg`, `flac` — audio re-encoder for music sessions.
- `arm_transcode` (this package) — claim/heartbeat client + encoder
  wrappers.

The Dockerfile builds three runtime targets from that common `base`:

| target  | tag (dev)                    | adds on top of `base`                                                              | used for                     |
|---------|------------------------------|------------------------------------------------------------------------------------|------------------------------|
| `base`  | `arm-transcode:latest`       | nothing: CPU encoders + NVENC (`libnvidia-encode` is injected by the host toolkit) | CPU, NVENC, and the fallback |
| `intel` | `arm-transcode:latest-intel` | `intel-media-va-driver-non-free`, `i965-va-driver`, `libvpl2`, `libmfx-gen1.2`     | QSV (Intel)                  |
| `amd`   | `arm-transcode:latest-amd`   | `mesa-va-drivers`                                                                  | VAAPI (AMD)                  |

The Backend spawns the variant matching the GPU's vendor when that image exists
and falls back to `base` otherwise. `ARM_TRANSCODE_IMAGE_QSV`,
`ARM_TRANSCODE_IMAGE_VAAPI` and `ARM_TRANSCODE_IMAGE_NVENC` override the image
per vendor. A plain `docker build` with no `--target` produces `base`.

`abcde` is **not** in the transcode image — that's a ripping tool, used
by `arm-ripper` to pull a CD into `track_NN.wav` files. The transcoder
re-encodes those WAVs to FLAC/MP3 via ffmpeg.

## Environment variables (set by the dispatcher at spawn time)

- `ARM_TRANSCODE_TASK_ID` — ULID of the row to register/claim/run.
- `ARM_BACKEND_URL` — e.g. `https://arm-backend:8443`.
- `ARM_SERVICE_TOKEN` — REST `Authorization: Bearer` and WS auth.
- `ARM_LOG_LEVEL` — JSON-line logger level.
- `PUID` / `PGID` — entrypoint drops privileges to this UID/GID before
  the encoder runs, so files in `/media` land owned by the user (the
  same pattern as the ripper container).
- `HOSTNAME` — set by docker via `--hostname`; the transcoder echoes it
  on register so the Backend can stamp `claimed_by`.

## Volumes

- `/raw:ro` — the rip-stage outputs (`title_tNN.mkv`, `track_NN.wav`,
  `dump.iso`).
- `/media:rw` — final library destination. The transcoder writes
  `<final>.arm-inprogress`, fsyncs the parent dir, then `rename(2)` to
  `<final>` on success. On crash or kill, partial files stay for the
  Backend startup sweep.
- `/etc/ssl/arm/arm-ca.crt:ro` — internal CA, merged into the system
  trust store by the entrypoint.
- `/logs:rw` — shared with the Backend; reserved for per-task log capture
  in Phase 12.

## Dev rebuild

In dev, the `arm-transcode` compose service carries `deploy.replicas: 0`: a
normal `docker compose up -d --build` (or `docker compose build`) **builds** the
image as `arm-transcode:latest` but **never starts** a container — the dispatcher
spawns short-lived containers from it on demand. To (re)build just this image:

```sh
docker compose build arm-transcode
docker compose build arm-transcode-intel   # Intel QSV variant
docker compose build arm-transcode-amd     # AMD VAAPI variant
```

`bash devtools/setup-dev.sh up` always builds `arm-transcode` and builds the
`-intel` / `-amd` variants only when it detects an Intel / AMD GPU on the host
(none with `--ripper-only`; neither variant when `ARM_TRANSCODE_DOCKER_HOST`
points at a remote transcode host, which builds its own).

The dispatcher picks the image up by name. In dev it's built locally and tagged
`arm-transcode:latest` (never pulled); production overrides `ARM_TRANSCODE_IMAGE`
with the versioned image pulled from the registry.

## Lifecycle (single task per container)

```text
 spawn (Backend)
      │
      ▼
 register     POST /api/transcoder/register   (verifies task is still expected)
      │
      ▼
 claim        POST /api/transcoder/tasks/{id}/claim
      │       (atomic queued → in_progress; emits session.started + task.started)
      ▼
 encode       HandBrakeCLI / ffmpeg / passthrough
      │       (heartbeat REST every 30s; transcode.progress.* WS every ~1s)
      ▼
 complete     PATCH /api/transcoder/tasks/{id}/complete
              (or /fail on error / cancel)
      │
      ▼
 exit (auto_remove=True)
```

Cancellation: the dispatcher emits `task.cancel` on
`transcoder.commands.{task_id}` over WS; the transcoder's main loop
catches it via the WS subscription and SIGTERMs the encoder. After a
10s grace, the dispatcher falls back to `docker stop`.

## GPU transcoding (Phase 7b)

There is **no GPU overlay** and the Backend is **GPU-free** — it ships no
`nvidia-smi` and gets no GPU device access. GPUs are detected **host-side at
install time** (`devtools/setup-dev.sh` / `armctl install`) and handed to the
Backend as the `ARM_GPUS` JSON env var; the Backend just parses it at lifespan
startup to fill the `gpus` table (`arm_backend/gpu_probe.py:load_configured_gpus`).

The only container that touches a GPU is the **ephemeral transcoder**. The
vendor VAAPI/QSV userspace is baked into the matching image target (see
[Image contents](#image-contents)): Intel's drivers + oneVPL into `intel`,
`mesa-va-drivers` into `amd`; every target carries the `libva` loader. NVENC's
`libnvidia-encode` is injected at runtime by the host's
nvidia-container-toolkit, so NVENC runs from `base`. The dispatcher passes the matching device into each
spawned container — `devices=/dev/dri/renderD*` for VAAPI/QSV, `runtime: nvidia`
+ `device_requests` for NVENC (`transcode_dispatcher.py:_inject_gpu_run_kwargs`).

NVIDIA hosts need nvidia-container-toolkit installed + registered with docker
(`nvidia-ctk runtime configure`); `armctl install` offers to set this up on apt
hosts. Re-run the installer after a GPU/driver change to refresh `ARM_GPUS`.

`ARM_GPUS` is a JSON array; each entry seeds one `gpus` row, detected host-side:

| vendor | detected host-side from |
|--------|-------------------------|
| QSV    | `/dev/dri/renderD*` + `/sys vendor=0x8086` |
| VAAPI  | `/dev/dri/renderD*` + `/sys vendor=0x1002` |
| NVENC  | `nvidia-smi -L` (per GPU) |

A seeded row's `encoder_kinds` is only a hint (empty array, `probed_at: NULL`);
the Backend's per-device probe (`gpu_probe_runner.py`) spawns this image's
`--probe-device` mode against the real device to find out what it can
actually encode, and that result, not the seed, is what the dispatcher's
claim reads.

A transcode preset names a catalog **encoder** id (`arm_common.encoders`,
for example `qsv_h265`, `any_h265`, `cpu_h265`), not a codec plus a
`hw_preference` switch. The dispatcher resolves the id to a GPU claim (or a
CPU spawn) and injects `ARM_TRANSCODE_ENCODER=<id>` into this container;
`ARM_GPU_VENDOR`, `ARM_GPU_DEVICE` and `ARM_GPU_CODEC` are also set for a
GPU claim. They are a harmless fallback, not an upgrade path: an image older
than `--probe-device` can never verify a row, so it is never handed a GPU in
the first place. This worker reads `ARM_TRANSCODE_ENCODER`; to upgrade a
host, rebuild or pull the transcode image. See
[docs/developers/architecture/02-job-lifecycle.md § Encoder claim and apply-time refusal](../../docs/developers/architecture/02-job-lifecycle.md#encoder-claim-and-apply-time-refusal)
for the full claim, queue and refusal rules.

Engine dispatch reads the catalog id: `qsv_*` and `nvenc_*` run through
HandBrake with `--encoder <engine_encoder>` appended after `--preset`;
`vaapi_*` runs through the ffmpeg VAAPI engine
(`arm_transcode/engines/ffmpeg_vaapi.py`) instead. HandBrakeCLI is in fact
compiled with its own AMD encoder (VCE/AMF) built in, same as QSV and
NVENC, but it can't run in any of these images: AMD's proprietary AMF
runtime isn't packaged for Debian, so it's not installed anywhere.
Supporting it is deferred pending hardware testing (a catalog and image
change only, no claim/model change). That gap is exactly why AMD is routed
through ffmpeg's VAAPI encoder on Mesa instead. Verify with the spawned
container's logs:

```sh
docker compose logs arm-transcode-<id> | grep -iE "HandBrakeCLI launching|ffmpeg_vaapi start"
```

The QSV/NVENC/AMD encoders are all built into HandBrakeCLI itself (see
`services/transcode/Dockerfile`, compiled with
`--enable-qsv --enable-nvenc --enable-vce`); whether QSV or NVENC actually
initializes depends on the matching vendor image variant
being present (`intel` / `base`, see [Image contents](#image-contents)) and
the device being passed through. There is no silent CPU fallback at the
encoder layer for a vendor-pinned encoder: a GPU is only chosen when the
Backend's claim, backed by a real per-device probe result, hands one to this
container.
