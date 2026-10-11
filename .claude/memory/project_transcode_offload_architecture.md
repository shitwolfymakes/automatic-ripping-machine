---
name: transcode offload architecture — neu transcoder vs v3 ephemeral-spawn
description: Architecture comparison for moving transcode off the N97 (#69); two opposite models, one already deployed on transcoder-server
metadata:
  type: project
---

Investigation (2026-06-30) for "move transcode off the N97" ([[project_nuc_transcode_crash]] #69).
Two genuinely opposite architectures achieve it; they are not variants of one design.

## A standalone neu transcoder is ALREADY running on transcoder-server
`uprightbass360/arm-transcoder:latest-nvidia` is up 2 weeks healthy on
[[project_transcoder_server_host]] (compose project `automatic-ripping-machine-transcoder`,
`docker-compose.nvidia.yml`). Local repo: `~/src/automatic-ripping-machine-transcoder`
(origin `uprightbass360/automatic-ripping-machine-transcoder`, **neu ecosystem**, NOT v3).

## neu transcoder = long-running HTTP offload service
- Ingress: **`POST /api/v1/webhook/arm`** — ARM pushes `{job_id,title,input_path,output_path,preset_slug,config_overrides,tracks[]}`, `X-Api-Version: 2` (versioned in `src/version.py`; v2=preset-based), authed `X-Webhook-Secret`.
- Own **SQLite queue + N async workers** (`MAX_CONCURRENT` 3-5 NVIDIA), survives restart.
- Egress: callback **`POST {ARM_CALLBACK_URL}/api/v1/jobs/{job_id}/transcode-callback`** `{status,error}` via a durable retry drainer (`pending_callbacks` table, permanent-vs-retriable).
- GPU **auto-detected at startup** (`nvidia-smi`, `gpu_monitor.py`); picks encoder/preset itself; live telemetry on `/workers`.
- Storage: reads `/raw`, writes `/completed` over NFS; **local-scratch copy→transcode→move**.
- **Owns the preset catalog**: `GET/POST /api/v1/presets`, `/scheme`. UI talks to it directly.

## v3 transcode = backend-orchestrated ephemeral container
- No standalone service. `transcode_dispatcher.py` reads `transcode_tasks` and
  **spawns a fresh arm-transcode container per task** on the backend's LOCAL docker
  socket (`containers.run(auto_remove=True)`), injects `ARM_BACKEND_URL=https://arm-backend:8443`
  (line 367), GPU kwargs (`_inject_gpu_run_kwargs`), NFS mounts.
- Pull-by-**claim**: worker `POST /register` + `POST /claim` (CAS, refuse unless IN_PROGRESS),
  WS `transcode.progress.{task_id}`, atomic `.arm-inprogress`→rename (`atomic.py`).
- GPU from the backend `gpus` table. Presets native to v3 (`transcode_presets`, `transcode_apply`).

## The two ways to move transcode off the N97
1. **Use the neu transcoder as-is (HTTP offload).** v3 dispatcher stops spawning
   containers, becomes an HTTP client: POST the v2 webhook to transcoder-server, expose
   a `transcode-callback` endpoint, map status → `transcode_tasks` row. Reuses the
   already-deployed proven service. COST: v3 inherits neu's webhook/callback contract +
   must reconcile TWO preset catalogs (v3 sessions vs neu presets). An integration that
   imports a different ecosystem's contract into v3.
2. **Remote-spawn v3's own transcoder (spike Approach A, #90 = GO).** Keep v3's model,
   spawn the container on transcoder-server's daemon (`DOCKER_HOST=ssh://sam@transcoder-server`,
   routable `ARM_BACKEND_URL=https://192.168.0.68:8080`, drop `network=armv3_default`).
   COST: small dispatcher change (spike-validated), but the running neu transcoder goes
   unused and TWO transcoder codebases coexist on that box.

## The tension (resolved 2026-06-30 → Approach A)
neu transcoder is the purpose-built, already-running answer, but it's a DIFFERENT
ecosystem's contract. Approach A keeps v3 architecturally consistent (clean claim-based
contract). Owner chose A; the neu transcoder on the box was spun down (retained on disk).

## Approach A — BUILT (code complete 2026-06-30, Task #91)
Branch **feat/tier25-remote-transcode-offload** (off feat/tier24-probe-race; worktree
`.claude/worktrees/tier25-remote-transcode`). Spec + plan in
`../arm-ai/arm-v3/docs/superpowers/{specs,plans}/2026-06-30-remote-nvenc-transcode-offload*`.
Final opus whole-branch review = READY TO MERGE (0 Crit/0 Imp); full suite 1631 passed.

Commits: 308b8053 (2 settings) → f22935b2 (`_build_docker_client(docker_host)` remote
ssh:// + `docker[ssh]` dep) → 5097e94c (host-aware `_spawn_container`: routable URL +
`network=None` when remote) → 13ac4b1c (warn on remote-host+empty-URL misconfig).

Two OPT-IN backend settings (empty = local behavior byte-for-byte):
- `ARM_TRANSCODE_DOCKER_HOST=ssh://sam@transcoder-server` → dispatcher's docker client
  targets that daemon; also gates the two spawn adjustments.
- `ARM_TRANSCODE_BACKEND_URL=https://192.168.0.68:8080` → routable ARM_BACKEND_URL
  injected into the remote container (else the unroutable in-network arm-backend:8443).

## Approach A — DEPLOYED to N97 (2026-07-01, control plane PROVEN end-to-end)
N97 checkout `~/src/automatic-ripping-machine-v3` on `spike/transcode-progress` @ e7628371
(the 4 tier25 commits grafted on). Stack up on **3 overlays**:
`docker-compose.yml -f docker-compose.hifi.yml -f docker-compose.transcoder-ssh.yml`.

Deploy wiring done (all on the N97 unless noted):
- `.env`: `ARM_TRANSCODE_DOCKER_HOST=ssh://sam@192.168.0.92` (IP, NOT the alias — container
  can't resolve `transcoder-server`), `ARM_TRANSCODE_BACKEND_URL=https://192.168.0.68:8080`,
  `ARM_GPUS=[{"vendor":"nvenc","device_path":"nvidia://0","encoder_kinds":["h264","h265"]}]`.
  Backup at `.env.bak.pre-tier25`.
- **NEW override `docker-compose.transcoder-ssh.yml`** (fork-local, gitignored-style): passes
  the two `ARM_TRANSCODE_*` env keys THROUGH to arm-backend (base compose only passes a fixed
  subset — setting them in `.env` alone does NOTHING) + mounts the SSH bundle
  `/home/upb/arm-ssh/container-ssh` → `/home/arm/.ssh:ro`.
- **Dedicated SSH key** `~/arm-ssh/backend_to_transcoder` (ed25519, generated ON the N97,
  authorized in `sam@transcoder-server:~/.ssh/authorized_keys`). Container bundle
  `~/arm-ssh/container-ssh/{id_ed25519,known_hosts,config}` owned uid1000. known_hosts pins
  `192.168.0.92 ssh-ed25519 …OG2Q`. paramiko reads it ONLY when run as `arm` (gosu, HOME=/home/arm)
  — root (HOME=/root) fails; the real dispatcher runs as arm so it's fine.
- **Backend TLS leaf re-minted** with `IP:192.168.0.68` (+ DNS quark/localhost, IP 127.0.0.1)
  in SANs, signed by the EXISTING CA (reused arm-backend.key), swapped into arm/certs/, backend
  restarted. Was needed because the stock leaf had ONLY `DNS:arm-backend`; the remote transcoder
  connects by IP. Backup `arm-backend.crt.bak`. (Upstream fix: teach install.sh make_leaf to
  emit `IP:` SANs + add box-routable SAN to arm-backend.)
- **ARM CA cert placed on the BOX** at `/home/upb/src/automatic-ripping-machine-v3/arm/certs/arm-ca.crt`
  (SHA 07a4f34f…, matches N97). The dispatcher mounts `{ARM_HOST_CERTS_PATH}/arm-ca.crt` →
  `/etc/ssl/arm/arm-ca.crt`; that host path must EXIST ON THE BOX or docker auto-creates it as
  an empty DIR (which happened → broke TLS). Placed via a root alpine container (`sam` in docker
  group, no sudo).

**PROVEN working end-to-end (test: applied `ses_builtin_movie_plex_1080p_gpu` to ripped
`job_01KWB5RD8X52Y4PPB7YQ0TRJ61` Total Recall):** container `arm-transcode-<id>` SPAWNED ON THE
BOX via `http+docker://ssh`; box watcher saw it Up; backend logs show `POST /register` from
192.168.0.92 → 200, `ws auth ok principal=…kind='transcoder'` (TLS+WS verified), `POST /claim`
→ 200. **The N97 no longer runs the encode.** #69 solved for the compute path.

**LAST BLOCKER — NFS `/completed` owner must EQUAL the container uid (marvin TrueNAS ACL):**
transcoder failed `[Errno 13] Permission denied: '/media/<Title>'` at `atomic.py:33`
(`final_path.parent.mkdir`). ROOT CAUSE (fully proven): marvin is **TrueNAS**; export
(`marvin.murphbutt.xyz`, 192.168.0.132, `/mnt/OOS_Pool/Files/Video/Import/{raw,completed,logs}`,
NFSv3 sec=sys, **root-squash ON**) carries **NFSv4 ACLs** where `add_subdirectory` is granted to
the **OWNER uid only, NOT the group** — the `drwxrws--- 2770` group-rwx bits are cosmetic. So the
container uid must EQUAL the dir's owner uid. TrueNAS user `sharing`=**uid 1001**, group
`sharing`=**gid 1000**. `raw`/`logs`/`.arm-nfs-heartbeat` are owner **1001** → ripper works.
`completed` kept reverting to owner **1000** → transcode (default PUID 1000) mismatched → DENIED.
The entrypoint's `chown arm:arm /media` is a **squashed no-op** (root→nobody over NFS) so it can't
self-heal OR damage ownership.

FIX (two halves, both needed):
1. **Code (committed):** `ARM_TRANSCODE_PUID`/`ARM_TRANSCODE_PGID` settings — dispatcher injects
   `PUID`/`PGID` into the spawned container env; entrypoint reads `PUID="${PUID:-1000}"` → drops
   to that uid. Empty = image default (unchanged). Worktree branch feat/tier25-remote-transcode-offload
   commit **a1b31062**; grafted to deploy line spike/transcode-progress **79163274** (pushed origin).
   Files: config.py, transcode_dispatcher.py (env dict), .env.example. 16 tests pass.
2. **Ops (marvin-side, USER does it):** `chown` completed → **1001** (sharing) on TrueNAS. Holds
   now because the transcoder runs as PUID=1001=owner (matches) and root-chown is squashed.

DEPLOYED on N97: `.env` `ARM_TRANSCODE_PUID=1001`/`PGID=1000`; override passes them through;
backend rebuilt+recreated @79163274; VERIFIED the spawned container env has `PUID=1001 PGID=1000`.
**PENDING: user's final `chown completed→1001` on TrueNAS, then re-apply session + confirm NVENC +
job=done.** N97 admin admin/adminadmin; trigger = `POST /api/jobs/{id}/transcode
{"session_id":"ses_builtin_movie_plex_1080p_gpu","overwrite":true}` on
job_01KWB5RD8X52Y4PPB7YQ0TRJ61. Watch `nvidia-smi --query-gpu=utilization.encoder` on the box.

Also still TODO: PR as a wolfy tier (tier-25 label taken by SDF #38 — next free number).
Relates to #7 (truthful NVENC h265).
