# Transcode dispatcher spawns transcoders without PUID/PGID → can't write NFS `completed/`

## Summary

When the Backend's transcode dispatcher spawns an ephemeral transcoder
container, it does **not** pass `PUID`/`PGID` into the container's environment.
The transcoder therefore drops to its image-default uid (`1000`), regardless of
the identity the rest of the stack runs as. On any deployment whose media
storage is owned by a different uid (e.g. an NFS export owned by `1001`), the
transcoder cannot create the output directory and every task fails with:

```
[Errno 13] Permission denied: '/media/<TITLE>'
```

The rip side is unaffected (ripper + backend get their uid from compose `.env`);
only the **dispatcher-spawned** transcoders are wrong.

## Environment

- ARM v3 (FastAPI backend + ephemeral transcoder spawned via the docker socket).
- Media on NFS: `/media` (→ `completed/`) owned by uid **1001** (`sharing`),
  mode `drwxrws---` (no "other" access). The stack runs `PUID=1001 PGID=1000`.
- Rip works: MKVs land in `/raw`. Apply session → 2 transcode tasks spawn →
  both fail immediately.

## Observed

```
Job #sap_01KVVYX0...  arm-transcode-2TWE8CKGTWBE
  [Errno 13] Permission denied: '/media/HIDDEN_AGENDA_AND_LIFEPOD'   (Failed)
Job #sap_01KVVYX0...  arm-transcode-N65ERDWNGTDG
  [Errno 13] Permission denied: '/media/HIDDEN_AGENDA_AND_LIFEPOD'   (Failed)
```

The transcoder process runs as uid 1000; the NFS `completed/` dir is owned 1001
with no world-write → `mkdir`/create denied.

## Root cause

`services/backend/arm_backend/transcode_dispatcher.py`, `_spawn_container()`
builds the spawned container's `environment` dict and **omits `PUID`/`PGID`**:

```python
env = {
    "ARM_TRANSCODE_TASK_ID": task.id,
    "ARM_BACKEND_URL": "https://arm-backend:8443",
    "ARM_SERVICE_TOKEN": self._settings.ARM_SERVICE_TOKEN,
    "ARM_LOG_LEVEL": self._settings.ARM_LOG_LEVEL,
    "ARM_SERVICE_NAME": f"arm-transcode-{task.id[-12:]}",
}
# ... RENDER_GID IS passed for VAAPI/QSV (~L391), but PUID/PGID are not.
container = self._docker.containers.run(
    image=self._settings.ARM_TRANSCODE_IMAGE,
    environment=env,
    volumes={ ... ARM_HOST_MEDIA_PATH: {"bind": "/media", "mode": "rw"} ... },
    ...
)
```

The shared entrypoint (`services/_common/docker-entrypoint.sh`) drops to
`PUID="${PUID:-1000}"` / `PGID="${PGID:-1000}"`. With no `PUID` in the spawned
env, the transcoder always runs as 1000 — even though the Backend container
itself already has `PUID=1001 PGID=1000` in *its* environment (verified:
`docker exec armv3-backend sh -c 'echo $PUID $PGID'` → `1001 1000`).

So the value is right there in the Backend's env; it just isn't forwarded to the
children. Note `RENDER_GID` *is* forwarded (for QSV/VAAPI render-node access),
which shows the env-passthrough mechanism exists — PUID/PGID were simply missed.

## Suggested fix

1. Read `PUID`/`PGID` into Backend settings (`config.py`), defaulting to `1000`
   to preserve current behavior:
   ```python
   PUID: str = "1000"
   PGID: str = "1000"
   ```
2. Forward them in `_spawn_container`'s `env`, alongside the existing entries:
   ```python
   env = {
       ...,
       "PUID": self._settings.PUID,
       "PGID": self._settings.PGID,
   }
   ```

That makes the ephemeral transcoder drop to the same identity as the rest of the
stack, so it can write to media storage owned by a non-1000 uid. Default-1000
keeps single-user / `${PWD}/arm` installs unchanged.

## Repro

1. Deploy with media on storage owned by a uid ≠ 1000 (e.g. NFS uid 1001), and
   set the stack `PUID/PGID` to match (1001/1000) so rips succeed.
2. Rip a disc, apply a session that transcodes to `/media`.
3. Every transcode task fails with `Permission denied: '/media/<title>'` because
   the transcoder ran as 1000, not the configured 1001.

## Acceptance

- A transcode task spawned by the dispatcher runs as the configured `PUID/PGID`
  and successfully writes its output under `/media` on storage owned by that
  uid. Single-user installs (PUID 1000) are unchanged.
