# Drive hotplug drill (quark, real hardware)

Proves the ripper survives unplug/replug with no intervention AND rips
afterwards. Run before merging Plan 1.

## Setup
1. Build: `docker build -f services/ripper/Dockerfile -t armv3-local/arm-ripper:lifecycle .`
2. In `~/arm/docker-compose.override.yml` for `arm-ripper-sr0`:
   - image `armv3-local/arm-ripper:lifecycle`
   - `device_cgroup_rules: ["b 11:* rmw", "c 21:* rmw"]`; **no** `devices:` (also removed from the base file)
   - volumes: `/dev/disk:/host-disk:ro` (remove any `/dev:/host-dev` bind)
   - environment: `ARM_DRIVE_ID=drv_drill`, `ARM_DRIVE_BY_ID=usb-PIONEER_BD-RW_BDR-S12JX_AAAABBBB000E-0:0`, `ARM_DRIVE_DEV=/dev/sr0`, `ARM_HOST_DISK_ROOT=/host-disk`; remove `ARM_DEV_ROOT`
   - the entrypoint pre-creates `sr0..N` / `sg0..N` up to `ARM_OPTICAL_SR_MAX` / `ARM_OPTICAL_SG_MAX`. Watch `ARM_OPTICAL_SG_MAX` in particular: `sg` minors are shared with every SCSI disk on the host, so a drive that replugs behind a pile of disks can land above the default bound and resolve to nothing. A `drive node ... is not present under /dev` warning in the log means exactly that — raise the bound
3. `docker compose up -d --no-deps arm-ripper-sr0`

## Checks — each must pass
| # | Action | Expect (container log unless noted) |
|---|---|---|
| 1 | start, drive attached | entrypoint prints `optical nodes: created 24 (...)`; `drive present at /dev/sr0 via by_id` |
| 2 | `docker exec … ls -la /dev/sr0 /dev/sg0` | both are real nodes, `0660`, owned by root and the CDROM group (major 11 / 21). When `CDROM_GID` matches no group inside the image the entrypoint creates one named `cdrom-host`, so the group column reads `cdrom-host` rather than `cdrom` — that is correct, not a fault |
| 3 | insert a known-good DVD | scan finds titles (`TCOUNT` > 0 in makemkv output; job created) — **this is the check the old branch failed** |
| 4 | unplug USB | exactly one `drive absent (...)` line; container stays `Up`; UI (once Plan 2 lands) shows detached; until then `docker logs` shows heartbeats continuing |
| 5 | wait 2 min | **no** further absent/ioctl lines |
| 6 | replug | one `drive present at /dev/srN via by_id (reattached)`; then `boot probe after reattach on /dev/srN`; the `device-path` PATCH is attempted before the probe and, until Plan 2 lands, logs `device-path endpoint absent (404); node /dev/srN not reported` at INFO (not a warning, and not a fault) |
| 7 | insert a different disc (or re-seat the same one) | a new job starts with no restart, no `compose up` |
| 8 | `sudo dmesg -T \| grep 'usb 4-1: reset'` | no reset storm (≤1 reset around the replug itself) |

Do NOT kill `makemkvcon` with `timeout` during the drill; interrupted SCSI commands make the drive reset (seen 2026-09-03).

## Record
Paste the log excerpts for checks 1, 3, 4, 6, 7 into the PR description.
