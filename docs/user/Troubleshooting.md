# Troubleshooting

Start here when something misbehaves. ARM v3 is a set of containers, so the
single most useful command is almost always the logs:

```bash
armctl compose ps                     # is every service up?
armctl compose logs -f arm-backend    # or arm-ui, arm-db
```

Set `ARM_LOG_LEVEL=debug` in `~/arm/.armctl/.env` and run `armctl up` before
reproducing a problem — the logs get much more detailed. Logs are also written as
JSONL under `~/arm/logs/`, with a `job_id` on each line for correlation.

---

## A disc isn't detected

The ripper polls its drive every ~2 seconds (no udev events needed), so a disc
should show up within a few seconds of the drive spinning up.

1. **Is the ripper running?** The backend starts one container per enrolled
   drive, named `arm-ripper-<serial>-<id>`. List them with
   `docker ps --filter label=arm.drive_id`. If your drive has none, it isn't
   enrolled: enroll it on the **Drives** page and the backend starts its ripper.
2. **Does the ripper see the drive?** Rippers get no `devices:` bind. Each one
   creates `/dev/sr0` to `/dev/sr7` and `/dev/sg0` to `/dev/sg15` itself at
   start and is allowed to open them, so a drive that is unplugged and comes
   back under a new number keeps working. A drive numbered above that range is invisible to
   the ripper; see the next section.
3. **Check the ripper log** while inserting a disc:
   `docker logs -f <ripper-name>`. A brief `DRIVE_NOT_READY` while the
   drive reads the table of contents is **normal**, and ARM keeps polling.

## Every disc "looks unidentifiable"

If video discs all fall through to the data-disc path and MakeMKV reports zero
titles, MakeMKV probably can't reach the drive's **SCSI-generic** node.
MakeMKV enumerates drives over SG ioctls, not the block device, so it needs
`/dev/sgM` *as well as* `/dev/srN`. The numbers don't line up: `sr0` is not
necessarily `sg0`. Find the drive's SG node on the host:

```bash
ls /sys/class/block/sr0/device/scsi_generic/    # e.g. -> sg5
```

The ripper creates `sg0` to `sg15` and `sr0` to `sr7`. On a host with many SCSI
devices the drive can land above that (for example `sg18`). Raise the range in
`~/arm/.armctl/.env` with `ARM_RIPPER_OPTICAL_SG_MAX` (and
`ARM_RIPPER_OPTICAL_SR_MAX` for the block node), then run `armctl up` while
the drive is idle. When the backend starts it recreates every idle ripper whose
settings no longer match `.env`, so the new range applies without removing
anything by hand. A ripper that is mid-rip at that moment keeps its old
settings and is recreated at the next backend start once it is idle. The
ripper logs the range it created at start
(`optical nodes: created ... (sr0..sr7, sg0..sg15)`).

## Disc won't eject after a rip

Symptom: the rip finishes but the disc stays in the drive, and the ripper logs
`eject /dev/srN failed … check host auto-mount config`.

This happens on **desktop** hosts (GNOME/KDE/XFCE), where `udisks2`/`gvfs`
auto-mounts the disc and holds the device, so the container can't eject it.
Server/headless hosts don't run those and aren't affected.

The fix is a host udev rule that disables *auto-mount* for every optical drive
on the host. The drive stays browsable; the desktop just won't grab it on
insert. It covers all `sr*` drives because drives are hot-plugged and enrolled
after install. `armctl install` writes it for you. To do it by hand:

```bash
# /etc/udev/rules.d/99-arm-no-automount.rules
SUBSYSTEM=="block", KERNEL=="sr[0-9]*", ENV{UDISKS_AUTO}="0"
```

```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## The drive dropped off USB during a rip

Symptom: the ripper logs `drive disconnected mid-rip on /dev/srN … waiting up
to 180s for it to return`, often next to a kernel `usb … USB disconnect` line.

USB enclosures sometimes reset, and the drive comes back a second later,
often under a new node (`sr0` becomes `sr1`). For a DVD or Blu-ray rip, ARM
stops MakeMKV straight away, keeps every title that already finished, and once
the drive reports the disc readable again, rips the rest with one more MakeMKV
pass on the new node. The disc stays in the drive until that pass ends. If the
drive doesn't come back within 180 seconds (or drops three times in one rip),
the job ends as partially ripped and the missing titles say the drive
disconnected. Audio CDs and full-disc backups don't resume; they fail as
before.

MakeMKV can only rip a whole disc in one pass, so the resume rips the titles
that already finished again too, into `raw/<job>/resume-1/`, and deletes those
copies once the pass ends. While it runs, `raw/` needs room for about one more
copy of the disc: up to 50 GB for a Blu-ray. If it fills up, the resumed titles
fail with MakeMKV's write error, not the disconnect message, and the job ends
partially ripped.

A drive that keeps dropping out usually needs a powered USB hub, a different
port or cable, or a different enclosure. Check `dmesg` for the disconnects.

## Files have the wrong owner, or the container exits at startup

ARM writes everything as `PUID:PGID` from `~/arm/.armctl/.env`, and it **never**
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

If the warning stays after you trusted the CA and you open the UI by IP, check
that the address is on the certificate:

```bash
openssl x509 -in ~/arm/certs/arm-ui.crt -noout -ext subjectAltName
```

If the address is missing (the host's IP changed after install), run
`armctl down`, then `armctl install` to issue a new certificate.

## "Password change required" / everything returns 403

That's expected on a brand-new install: log in as `admin` / `admin`, set a new
password, and the rest of the UI unlocks. The default credentials are also in
`docker exec armv3-backend cat /logs/first-boot.log`.

## Live updates don't appear (WebSocket)

The dashboard updates over a WebSocket. Same-origin connections are accepted
automatically, so opening the UI by any hostname, LAN IP or port works out of
the box; when live updates are down the UI shows a "Live updates unavailable"
banner while it retries. If the banner persists and you are fronting ARM with
your own reverse proxy on a different origin, add that origin to
`ARM_ALLOWED_ORIGINS` in `~/arm/.armctl/.env`, e.g.:

```bash
ARM_ALLOWED_ORIGINS=https://arm.example.com
```

Then `armctl up`.

## GPU isn't detected

1. Check `ARM_GPUS` in `~/arm/.armctl/.env`. The installer writes it from host-side
   detection and `armctl up` refreshes it; if it's `[]`, nothing was found. Run
   `armctl up` (or `devtools/setup-dev.sh` in a dev checkout) after fixing
   drivers/toolkit.
2. **NVIDIA:** install the NVIDIA Container Toolkit on the host (the installer
   offers to do this on apt hosts) — see
   [Hardware Transcoding § NVIDIA](Hardware-Transcoding#nvidia-the-container-toolkit).
   Without it the transcoder can't get the GPU and the job falls back to CPU.
   Confirm the runtime is registered: `docker info | grep -i nvidia`.
3. **NVIDIA driver older than 530:** the installer and `armctl up` leave NVENC
   out of `ARM_GPUS` and warn `NVIDIA driver <version> is too old for this
   build's NVENC (needs >= 530.x)`. Upgrade the host driver, then run
   `armctl up`.
4. **Intel/AMD:** `/dev/dri/renderD*` must exist on the host. If it's missing,
   the kernel driver for your GPU isn't loaded.
5. Check what the backend loaded: `armctl compose logs arm-backend | grep -i gpu`.

A host with no detectable GPU still transcodes on CPU — this is a speed issue,
not a broken stack.

## MakeMKV key errors

`App key incorrect`, `MSG:5021 application version too old`, or Blu-rays failing
while DVDs work — all covered on the [MakeMKV](MakeMKV) page.

## The image pull returns 404

During the alpha, registry images may not exist for every tag yet. Build the
images locally from a checkout — see
[Local development in CONTRIBUTING.md](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/CONTRIBUTING.md#local-development).

## Still stuck?

Open an issue with the **service name**, the relevant `armctl compose logs`
output captured at `ARM_LOG_LEVEL=debug`, and the disc/hardware involved:
<https://github.com/automatic-ripping-machine/automatic-ripping-machine/issues/new/choose>.
Because ARM drives MakeMKV and HandBrake, it's also worth trying the underlying
tool by hand to rule out an upstream problem.
