---
name: hifi-server v3 deploy (host-specific, not in git)
description: How the v3 stack is deployed on hifi-server, including the NFS uid, cert-key chmod, ripper splice, and allowed-origins facts that live only on the host
metadata:
  type: project
---

The v3 stack runs on **hifi-server** (host `quark`, `192.168.0.68`, user `upb`,
key `~/.ssh/hifi`) at `~/src/automatic-ripping-machine-v3`, cloned from
`origin` (`uprightbass360/arm-v3`, now public). Deployed branch:
`deploy/hifi-20260705`; checkout at **`93e0f062`** since 2026-07-20:
**render-gid self-derivation deployed** (PR #56 line merged): arm-transcode +
arm-backend rebuilt; verified explicit + derivation paths in real containers,
drill reports {"qsv":["h264","h265"]} with zero flags, remote NVENC spawn OK.
**`ARM_RENDER_GID` is now UNSET in .env by design** — the entrypoint derives
gid 993 from /dev/dri/renderD128 itself; do not "fix" the empty value.
Note: /raw holds three ORPHAN job dirs (deleted jobs); Total Recall's raw is
gone, so re-applying transcode sessions to old jobs fails with HandBrake rc=2
"open … failed" — data state, not a bug (3 failed tasks from 2026-07-20 are
this).
Previous checkout **`33e0470b`** since 2026-07-17:
**tier-stack absorb deployed** — the manual 0016_1/0016_2 DDL was applied
first via psql (drives.serial + jobs.drive_serial added, drive_id nullable,
FK → ON DELETE SET NULL; alembic stays stamped 0028, upgrade head no-ops),
then backend+ripper-sr0+ui-neu rebuilt under all 3 overlays. Verified:
diagnostics/stats/resources/drives/jobs all 200, ui-neu + public proxy 200,
offload env (8 ARM_TRANSCODE_* keys) + ssh bundle intact, ripper
re-registered. Drive serial is NULL (ARM_DRIVE_SERIAL not spliced into the
hand-generated ripper block — coalesce-safe; splice udevadm
ID_SERIAL_SHORT later if wanted).
Previous checkout **`76234b4c`** since 2026-07-16:
**arm-backend + arm-ui-neu rebuilt** there (neu-ports reconciliation:
/api/system/diagnostics replaces preflight/paths, notification unions,
ensure_roots lifespan, ISO feature retained, mobile drawer Menu/Stats;
verified diagnostics/resources/iso-scan probes + live drawer post-rebuild).
Previous checkout **`a4c0f666`** since 2026-07-14
(tier34-themes reconciliation merge: 3 new builtin themes winamp-classic /
hifi-deck / gruvbox + Tier-32/33 ancestry joined; arm-ui-neu rebuilt,
arm-backend recreated same-image with all three overlays — offload intact;
themes verified live via /themes/<id>.css 200 + Playwright screenshots).
Previous checkout **`69366c9d`** since 2026-07-06:
**arm-ripper-sr0 rebuilt** there (carries the abandon-now-ejects fix
`c247c9bd` + entrypoint gid-adopt; verified `_spawn_eject` present in the
running container). Backend/ui/transcode images still from the `31d88ef1`
build — no functional delta for them in the 2026-07-06 commits.
**Deploy gotcha (hit 2026-07-06, ROOT-CAUSED + FIXED 2026-07-14): hifi's
remote-tracking refs went stale because the clone's fetch refspec was pinned
single-branch to `spike/timed-review-gate`** — a bare `git fetch origin` there
fetched nothing useful and `reset --hard origin/<branch>`/an explicit new SHA
failed with "Could not parse object". Fixed with `git config
remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'`; still verify with
`git log --oneline -1` after any reset. `git fetch origin <branch> && git
reset --hard FETCH_HEAD` remains the belt-and-suspenders recipe.
Previous state (tip `31d88ef1` as of 2026-07-05 redeploy — carries the
GEP encoder-probe + installer fixes F-A/F-F/F-G; rebuilt+recreated
arm-backend/arm-ui-neu/arm-transcode:latest under all 3 overlays, offload
verified writing NFS as 1001:1000 via remote `transcoder`) — the disconnected-PR deploy branch
`deploy/hifi-20260704` (bulk-delete filter + orphaned-session reconciler + QSV
libmfx fix) with **tier33 per-container-stats** merged on top (backend+ripper
host resource tabs; migration `0027` hosts table). Rebuilt+recreated
arm-backend/arm-ripper-sr0/arm-ui-neu on 2026-07-04; migration 0027 auto-applied
by the backend lifespan (`main.py` `_run_migrations()` → `alembic upgrade head`
on startup — no manual step). Verified: /api/system/resources 200 to the
authed proxy, hosts manifest populating (backend self-register + arm-ripper-sr0
heartbeat ~30s), public UI 200. NOTE: each backend restart leaves an orphan
`backend`-role hosts row keyed by the random Docker container ID; only the live
one refreshes, stale ones drop from tabs after the 5-min STALE_AFTER (harmless).

Prior deployed branch was `spike/timed-review-gate` (pausing feature + LCARS
theme + WS rip-progress).

Reached via reverse proxy at **`https://arm.murphbutt.xyz`** → `192.168.0.68:8888`
(self-signed inside; proxy terminates public TLS). Admin login `admin` /
**password was changed to `adminadmin`** on first login.

## Compose

**Use ALL THREE overlays — omitting the ssh one silently breaks remote offload:**
```
docker compose \
  -f docker-compose.yml \
  -f docker-compose.hifi.yml \
  -f docker-compose.transcoder-ssh.yml \
  up -d --force-recreate --no-deps <svc>
```
- `docker-compose.yml` is **gitignored** (generated per-host from
  `docker-compose.yml.example`; on hifi it's just the template copied, plus a
  hand-spliced `arm-ripper-sr0` service in the `>>>/<<< arm-ripper services`
  region — see below).
- `docker-compose.hifi.yml` is the **NFS overlay** (scp'd, not committed —
  fork-local deploy infra): repoints backend `/raw`→`completed`→`logs` to NFS,
  publishes ui-neu on **8888** and backend on **8080**, and adds an
  `arm-nfs-check` busybox gate that blocks the backend until the NFS heartbeat
  sentinel exists.
- `docker-compose.transcoder-ssh.yml` is the **OFFLOAD overlay** (scp'd, not
  committed): passes the 4 `ARM_TRANSCODE_*` env keys through from `.env` and
  mounts the ssh bundle `/home/upb/arm-ssh/container-ssh:/home/arm/.ssh:ro`.
  **GOTCHA (hit 2026-07-05):** recreating arm-backend with only the first two
  `-f` files DROPS the offload env + ssh mount → backend's docker client falls
  back to the LOCAL daemon (`quark`) instead of the remote `transcoder`, silently
  disabling offload. Always include this third `-f` when recreating arm-backend.

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
