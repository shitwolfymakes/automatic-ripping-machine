# arm-transcode

Ephemeral, single-task transcoder container. The Backend's
`TranscodeDispatcher` spawns one container per `transcode_tasks` row via
the Docker socket; each container claims its task, runs HandBrake or
ffmpeg against the raw input, writes the output through the
`*.arm-inprogress` atomic-rename flow, and exits.

## Image contents

`python:3.14-slim-bookworm` plus:

- `tini` — PID 1; reaps the encoder subprocess.
- `gosu` — drops to PUID/PGID before exec.
- `ca-certificates` — base trust store; the entrypoint merges the
  install's internal CA at boot so HTTPS verifies against the Backend's
  internal cert.
- `handbrake-cli` — primary video encoder.
- `ffmpeg`, `flac` — audio re-encoder for music sessions.
- `arm_transcode` (this package) — claim/heartbeat client + encoder
  wrappers.

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

The image is not declared as a runtime compose service — the dispatcher
spawns it on demand. To build it locally:

```sh
docker compose --profile build-transcode build arm-transcode-builder
```

The dispatcher picks the image up by name (`arm-transcode:dev` by
default, override via `ARM_TRANSCODE_IMAGE` in `.env`).

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
install time** (`devtools/setup-dev.sh` / `install.sh`) and handed to the
Backend as the `ARM_GPUS` JSON env var; the Backend just parses it at lifespan
startup to fill the `gpus` table (`arm_backend/gpu_probe.py:load_configured_gpus`).

The only container that touches a GPU is the **ephemeral transcoder**. This
image is the fat, multi-vendor HW image: the VAAPI/QSV userspace (`libva`,
`mesa-va-drivers`, `intel-media-va-driver-non-free`, `i965-va-driver`, oneVPL)
is baked in; NVENC's `libnvidia-encode` is injected at runtime by the host's
nvidia-container-toolkit. The dispatcher passes the matching device into each
spawned container — `devices=/dev/dri/renderD*` for VAAPI/QSV, `runtime: nvidia`
+ `device_requests` for NVENC (`transcode_dispatcher.py:_inject_gpu_run_kwargs`).

NVIDIA hosts need nvidia-container-toolkit installed + registered with docker
(`nvidia-ctk runtime configure`); `install.sh` offers to set this up on apt
hosts. Re-run the installer after a GPU/driver change to refresh `ARM_GPUS`.

`ARM_GPUS` is a JSON array; each entry mirrors a `gpus` row:

| vendor | detected host-side from | encoders advertised |
|--------|-------------------------|---------------------|
| QSV    | `/dev/dri/renderD*` + `/sys vendor=0x8086` | h264, h265 |
| VAAPI  | `/dev/dri/renderD*` + `/sys vendor=0x1002` | h264, h265 |
| NVENC  | `nvidia-smi -L` (per GPU) | h264, h265 |

Each `transcode_presets.codec` (h264 / h265 / av1 / NULL) is matched
against the GPU's `encoder_kinds` array. AV1 is intentionally not on
this list yet — encoder support varies by silicon generation; treat any
AV1 preset as CPU-only for Phase 7b.

`hw_preference` semantics:

| value     | matching GPU available | matching GPU busy | no matching GPU on host |
|-----------|------------------------|-------------------|-------------------------|
| `cpu_only`| CPU                    | CPU               | CPU                     |
| `any`     | GPU                    | CPU               | CPU                     |
| `NULL` (default) | GPU             | queue → GPU when free | CPU                |

The dispatcher injects `ARM_GPU_VENDOR`, `ARM_GPU_DEVICE`, and
`ARM_GPU_CODEC` env vars; `arm_transcode/handbrake.py` maps them to
HandBrake's HW encoder ID and appends `--encoder <id>`. The IDs are
`qsv_h264`/`qsv_h265` (Intel), `nvenc_h264`/`nvenc_h265` (NVIDIA), and
`vce_h264`/`vce_h265` (AMD — HandBrake has no generic "vaapi" encoder, so the
`vaapi` vendor token from the probe bridges to `vce_*`). Verify with the
spawned container's logs:

```sh
docker compose logs arm-transcode-<id> | grep "HandBrakeCLI launching"
```

These encoders are built into the image (see `services/transcode/Dockerfile`,
HandBrakeCLI compiled with `--enable-qsv/nvenc/vce`). HandBrake only *lists* an
encoder when it can initialize the device, so `HandBrakeCLI --help` shows the HW
IDs only with the GPU passed in. There's no silent CPU fallback at the encoder
layer — GPU is only chosen when Backend successfully claimed a `gpus` row.
