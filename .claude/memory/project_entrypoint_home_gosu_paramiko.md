---
name: entrypoint HOME/gosu/paramiko remote-transcode gotcha
description: Why the remote transcode dispatcher needs HOME=/home/arm exported before the gosu drop, and how to verify it live
metadata:
  type: project
---

The shared container entrypoint (`services/_common/docker-entrypoint.sh`) drops
privileges with `gosu arm`, which **switches UID but preserves the inherited
environment** — including `HOME=/root` from the root parent. The transcode
dispatcher's docker-py `ssh://` client uses **paramiko**, which resolves
`~/.ssh/known_hosts` against `$HOME`. With `HOME=/root` it reads the nonexistent
`/root/.ssh/known_hosts` → the remote host key is **"not found in known_hosts"**
→ `_build_docker_client()` returns None → **remote transcode dispatcher silently
disabled** (backend still boots fine). The ssh bundle is correctly mounted at
`/home/arm/.ssh` (key + config + known_hosts) via `docker-compose.transcoder-ssh.yml`
(`/home/upb/arm-ssh/container-ssh:/home/arm/.ssh:ro`); the only problem is HOME.

**Fix (committed, deploy/hifi-20260705 25679964):** `export HOME=/home/arm`
immediately before `exec /usr/bin/tini -- gosu arm "$@"`. This also helps the
ripper's `/home/arm/.MakeMKV` writes. Nothing in any service expects HOME=/root.

**Verifying live — DON'T trust `docker exec ... python3` probes:** `docker exec`
spawns a fresh process that gets the image default `HOME=/root`, NOT PID 1's env,
so `_build_docker_client()` run under plain `docker exec` will ALWAYS report
None even when the real dispatcher is healthy. Authoritative checks instead:
- `docker exec backend sh -c 'tr "\0" "\n" </proc/1/environ | grep ^HOME='` → must be `/home/arm`.
- backend log shows `transcode dispatcher starting: max_parallel=...` with NO
  `dispatcher disabled` / `not found in known_hosts` warning at that boot (the
  dispatcher is only created inside `if docker_client is not None`, so the
  "starting" line proves the client built).
- No per-tick ssh/docker errors after boot.
- To force a positive probe: `docker exec -e HOME=/home/arm backend python3 -c
  '...build_docker_client...'` → prints `remote: transcoder`.

Remote daemon is `ssh://sam@192.168.0.92` (transcoder-server), which mounts the
SAME marvin NFS export (`marvin.murphbutt.xyz:/mnt/OOS_Pool/Files` at `/nfs/files`,
logs dir owned `1001:1000`) as hifi — so remote transcode logs land on the shared
`/logs` the backend LogTailer reads. See [[hifi-server-v3-deploy]].
