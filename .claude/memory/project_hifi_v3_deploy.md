---
name: hifi-server v3 deploy (host-specific, not in git)
description: How the v3 stack is deployed on hifi-server, including the NFS uid, cert-key chmod, ripper splice, and allowed-origins facts that live only on the host
metadata:
  type: project
---

The v3 stack runs on **hifi-server** (host `quark`, `192.168.0.68`, user `upb`,
key `~/.ssh/hifi`) at `~/src/automatic-ripping-machine-v3`, cloned from
`origin` (`uprightbass360/arm-v3`, now public). Deployed branch (as of
2026-06-25): **`spike/transcode-progress`** @ 138fbab7 — spike/timed-review-gate
(pausing + LCARS + WS rip-progress) PLUS the cherry-picked transcode_progress
"job done" feature (backend `_summarize_transcode_progress` + ui-neu
`job-status.ts` effective-status) PLUS the cherry-picked QSV fix
(`libmfx-gen1.2`). Verified live: `/api/jobs` returns
`transcode_progress {state,tasks_total,tasks_done,percent}` (a done job reads
`state:'done'`). The local server-only QSV Dockerfile edit is now redundant
(in the branch) and was `git stash`ed before the branch switch.

ACTIVE OVERLAY = **local** (`docker-compose.hifi-local.yml`, `./arm/*` on local
disk, PUID/PGID=1000, ARM_GPUS qsv h264-only). Compose SERVICE names (not
container names): `arm-backend`, `arm-ui-neu`, `arm-transcode`, `arm-ripper-sr0`,
`arm-db`, `arm-ui`. Container names are `armv3-*`. Redeploy a service:
`docker compose -f docker-compose.yml -f docker-compose.hifi-local.yml build <svc>`
then `... up -d --no-deps <svc>`.

Earlier deployed branch `spike/timed-review-gate` is the pre-feature rollback point.

Reached via reverse proxy at **`https://arm.murphbutt.xyz`** → `192.168.0.68:8888`
(self-signed inside; proxy terminates public TLS). Admin login `admin` /
**password was changed to `adminadmin`** on first login.

## Compose

`docker compose -f docker-compose.yml -f docker-compose.hifi.yml ...`
- `docker-compose.yml` is **gitignored** (generated per-host from
  `docker-compose.yml.example`; on hifi it's just the template copied, plus a
  hand-spliced `arm-ripper-sr0` service in the `>>>/<<< arm-ripper services`
  region — see below).
- `docker-compose.hifi.yml` is the **NFS overlay** (scp'd, not committed —
  fork-local deploy infra): repoints backend `/raw`→`completed`→`logs` to NFS,
  publishes ui-neu on **8888** and backend on **8080**, and adds an
  `arm-nfs-check` busybox gate that blocks the backend until the NFS heartbeat
  sentinel exists.

## Host-specific facts that live ONLY on the server (lost on a clean rebuild)

1. **PUID/PGID = 1001/1000.** The NFS export (marvin `192.168.0.132:/mnt/OOS_Pool/Files`
   → `/nfs/files`) owns the Import tree as `sharing` = **uid 1001, gid 1000**,
   mode `drwxrws---` (no "other"). So the containers MUST run as 1001:1000 to
   write. `chown 1001 -R` was run on the Import dirs to settle it. (This matches
   neu's `ARM_UID=1001/ARM_GID=1000`.)
2. **Cert keys chmod 440.** `install.sh --certs-only` writes leaf keys
   `r--------` owned uid 1000, but the backend/ripper run as 1001 → can't read
   their TLS key → crash-loop on `load_cert_chain`. Fix: `chmod 440
   arm-backend.key arm-ripper-sr0.key` (group-readable; gid 1000 matches). Re-run
   after any cert regen.
3. **Ripper service is hand-spliced** into `docker-compose.yml` (lsscsi was
   missing at first; the drive is a Pioneer BD-RW at `/dev/sr0`↔`/dev/sg0`,
   `cdrom` gid **24** not 44). Its `/raw`+`/logs` point at NFS like the backend.
4. **`ARM_ALLOWED_ORIGINS`** must include **both** `https://192.168.0.68:8888`
   AND `https://arm.murphbutt.xyz`. The WS endpoint (`ws/router.py`
   `_origin_allowed`) closes the browser connection with 403 if the
   reverse-proxy origin isn't allowlisted — this is what broke the live WS at
   first. Env change needs `up -d --force-recreate arm-backend`.
5. **GPU = Intel Alder Lake-N QSV.** `ARM_GPUS=[{"vendor":"qsv","device_path":"/dev/dri/renderD128","encoder_kinds":["h264","h265"]}]`,
   `ARM_RENDER_GID=993`.

## Deploy / redeploy

Push to `origin spike/transcode-progress`, then on hifi:
`git fetch origin spike/...:refs/remotes/origin/spike/... --force && git reset --hard origin/spike/...`
(gitignored compose/.env/overlay survive the reset), then rebuild the changed service.

**Fetch gotcha (hit 2026-06-26):** a bare `git fetch origin spike/<b>` only writes
FETCH_HEAD, NOT the tracking ref `origin/spike/<b>` — so a following
`git reset --hard origin/spike/<b>` lands on the STALE old tip. Use the explicit
refspec form above (`origin spike/<b>:refs/remotes/origin/spike/<b> --force`), or
reset to the literal commit SHA, or to `FETCH_HEAD`.

ACTIVE overlay is **local** → rebuild = `docker compose -f docker-compose.yml -f
docker-compose.hifi-local.yml build arm-ui-neu` then `... up -d --no-deps arm-ui-neu`.
Compose service is `arm-ui-neu`; the running CONTAINER is `armv3-ui-neu` (NOT
`armv3-arm-ui-neu` — a `docker ps --filter name=armv3-arm-ui-neu` matches nothing).
(NFS-overlay variant uses `docker-compose.hifi.yml` + `up -d --build <svc>`.)
Stop neu first if reusing its ports: `docker stop arm-ui arm-rippers` (neu is
stopped not removed — rollback = `docker start`).
