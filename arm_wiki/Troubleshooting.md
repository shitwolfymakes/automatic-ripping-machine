# Troubleshooting

Start here when something misbehaves. ARM v3 is a set of containers, so the
single most useful command is almost always the logs:

```bash
cd ~/arm
docker compose ps                     # is every service up?
docker compose logs -f arm-backend    # or arm-ripper-sr0, arm-ui, arm-db
```

Set `ARM_LOG_LEVEL=debug` in `~/arm/.env` and `docker compose up -d` before
reproducing a problem — the logs get much more detailed. Logs are also written as
JSONL under `~/arm/logs/`, with a `job_id` on each line for correlation.

---

## A disc isn't detected

The ripper polls its drive every ~2 seconds (no udev events needed), so a disc
should show up within a few seconds of the drive spinning up.

1. **Is the ripper running?** `docker compose ps` should list
   `armv3-ripper-srN` as up. If it's missing, the drive wasn't enrolled — rerun
   `install.sh` and `docker compose up -d`.
2. **Is the drive in the compose file?** Each drive needs **both** its block
   device and its SCSI-generic node passed in. Rerunning `install.sh` detects
   and wires these automatically.
3. **Check the ripper log** while inserting a disc:
   `docker compose logs -f arm-ripper-sr0`. A brief `DRIVE_NOT_READY` while the
   drive reads the table of contents is **normal** — ARM keeps polling.

## Every disc "looks unidentifiable"

If video discs all fall through to the data-disc path and MakeMKV reports zero
titles, the ripper is almost certainly missing the **SCSI-generic** node.
MakeMKV enumerates drives over SG ioctls, not the block device, so it needs
`/dev/sgM` *as well as* `/dev/srN`. The pairing is **not** lexicographic — `sr0`
does not necessarily pair with `sg0`. Find the right node:

```bash
ls /sys/class/block/sr0/device/scsi_generic/    # e.g. -> sg5
```

The installer detects and wires this for you — rerun `install.sh` and
`docker compose up -d` to fix it.

## Disc won't eject after a rip

Symptom: the rip finishes but the disc stays in the drive, and the ripper logs
`eject /dev/srN failed … check host auto-mount config`.

This happens on **desktop** hosts (GNOME/KDE/XFCE), where `udisks2`/`gvfs`
auto-mounts the disc and holds the device, so the container can't eject it.
Server/headless hosts don't run those and aren't affected.

The fix is a one-time host udev rule that disables *auto-mount* for the ARM
drive(s) only (the drive stays browsable; the desktop just won't grab it on
insert). The installer writes this for you. To do it by hand:

```bash
# Find the drive's stable identifier:
udevadm info /dev/sr0 | grep -E 'ID_PATH=|ID_SERIAL='

# /etc/udev/rules.d/99-arm-no-automount.rules  (use your ID_PATH)
SUBSYSTEM=="block", KERNEL=="sr[0-9]*", ENV{ID_PATH}=="pci-0000:00:14.0-ata-3", ENV{UDISKS_AUTO}="0"
```

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## Files have the wrong owner, or the container exits at startup

ARM writes everything as `PUID:PGID` from `~/arm/.env`, and it **never**
`chown -R`s your mounted volumes. If `raw/` or `media/` is owned by someone
else at startup, the container logs a clear ownership error and **exits** rather
than rewriting your files.

- Set `PUID`/`PGID` to match the owner of `raw/`/`media/` (and ideally your
  media server), then fix the host-side ownership:

  ```bash
  sudo chown -R "$PUID:$PGID" ~/arm/raw ~/arm/media
  ```

- If `raw/` and `media/` are on different storage with different owners (e.g.
  `media/` is a NAS share), reconcile at the mount layer — CIFS with
  `uid=$PUID,gid=$PGID,forceuid,forcegid`, or NFS mapped to `PUID`. See
  [Configuration § File ownership](Configuring-ARM#file-ownership).

## Browser shows a certificate warning

The stack uses its own internal CA, so the first visit warns. Click through, or
import `~/arm/certs/arm-ca.crt` into your browser/OS trust store as a trusted
root once to clear it on every device. See
[Getting Started § Trust the certificate](Getting-Started#trust-the-certificate).

## "Password change required" / everything returns 403

That's expected on a brand-new install: log in as `admin` / `admin`, set a new
password, and the rest of the UI unlocks. The default credentials are also in
`docker exec armv3-backend cat /logs/first-boot.log`.

## Live updates don't appear (WebSocket)

The dashboard updates over a WebSocket whose origin is allow-listed. If progress
never moves, make sure the URL you're using is in `ARM_ALLOWED_ORIGINS` in
`~/arm/.env` — add your LAN hostname/IP if you log in from another device, e.g.:

```bash
ARM_ALLOWED_ORIGINS=https://localhost:8081,https://nas.lan:8081,https://192.168.1.20:8081
```

Then `docker compose up -d`.

## GPU isn't detected

1. Check `ARM_GPUS` in `~/arm/.env`. The installer writes it from host-side
   detection; if it's `[]`, nothing was found. Re-run `install.sh` (or
   `devtools/setup-dev.sh`) after fixing drivers/toolkit — detection only happens
   at install time.
2. **NVIDIA:** install the NVIDIA Container Toolkit on the host (the installer
   offers to do this on apt hosts) — see
   [Hardware Transcoding § NVIDIA](Hardware-Transcoding#nvidia-the-container-toolkit).
   Without it the transcoder can't get the GPU and the job falls back to CPU.
   Confirm the runtime is registered: `docker info | grep -i nvidia`.
3. **Intel/AMD:** `/dev/dri/renderD*` must exist on the host. If it's missing,
   the kernel driver for your GPU isn't loaded.
4. Check what the backend loaded: `docker compose logs arm-backend | grep -i gpu`.

A host with no detectable GPU still transcodes on CPU — this is a speed issue,
not a broken stack.

## MakeMKV key errors

`App key incorrect`, `MSG:5021 application version too old`, or Blu-rays failing
while DVDs work — all covered on the [MakeMKV](MakeMKV) page.

## `docker compose pull` returns 404

During the alpha, registry images may not exist for every tag yet. Build the
images locally from a checkout — see
[Local development in the README](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/README.md#local-development).

## Still stuck?

Open an issue with the **service name**, the relevant `docker compose logs`
output captured at `ARM_LOG_LEVEL=debug`, and the disc/hardware involved:
<https://github.com/automatic-ripping-machine/automatic-ripping-machine/issues/new/choose>.
Because ARM drives MakeMKV and HandBrake, it's also worth trying the underlying
tool by hand to rule out an upstream problem.
