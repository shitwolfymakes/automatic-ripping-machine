---
name: hifi-server v3 deploy (host-specific, not in git)
description: How the v3 stack is deployed on hifi-server, including the NFS uid, cert-key chmod, ripper splice, and allowed-origins facts that live only on the host
metadata:
  type: project
---

The v3 stack runs on **hifi-server** (host `quark`, `192.168.0.68`, user `upb`,
key `~/.ssh/hifi`) at `~/src/automatic-ripping-machine-v3`, cloned from
`origin` (`uprightbass360/arm-v3`, now public). Deployed branch:
`spike/timed-review-gate` (pausing feature + LCARS theme + the WS rip-progress
work, all rebased on top of Tier-12 `feat/ui-neu-combined`).

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

Push to `origin spike/timed-review-gate`, then on hifi:
`git fetch origin spike/... && git reset --hard origin/spike/...` (gitignored
compose/.env/overlay survive the reset), then rebuild the changed service:
`docker compose -f docker-compose.yml -f docker-compose.hifi.yml up -d --build <svc>`.
Stop neu first if reusing its ports: `docker stop arm-ui arm-rippers` (neu is
stopped not removed — rollback = `docker start`).
