# Real-disc smoke test

Cutover (Phase 16) requires evidence that v3 has rip-transcoded at least
one of each disc type — Blu-ray, DVD, audio CD — on a contributor's
machine, against the same code path users will install via
`curl | bash`. This document is the checklist; results land in the PR
that closes Phase 15.

## Prereqs

- Linux host with Docker ≥ 24, an optical drive, and the disc you're
  testing in the drive.
- Either a fresh install made with `install.sh` from a checkout
  (preferred — exercises the installer too) or a working dev stack at the
  repo root. The installer refuses an `arm` folder that has files in it but
  was not made by it, so use a new or empty location.

## One-time host prep

```bash
# Group membership lets the host user inspect the drive directly.
sudo usermod -aG cdrom "$USER" && newgrp cdrom

# Confirm the drive is visible.
ls -l /dev/sr*

# Confirm SCSI-generic pairing exists (silent failure mode if missing).
ls /sys/class/block/sr0/device/scsi_generic/   # expect e.g. sg0 or sg5
```

If the SCSI-generic node is missing, MakeMKV will silently fall back to
data-disc mode and produce no titles. The installer does not look at
drives: you enroll the drive from the UI, and the backend's drive scanner
pairs each `sr` node with its `sg` node when it starts that drive's ripper.
Sanity check the pairing yourself first.

## Run the test (fresh install path — preferred)

`--prefix` names the folder the `arm` folder goes in, so a throwaway
location keeps the test apart from any real install. The install lands in
`$TEST/arm` (unless `$TEST` itself ends in `arm`, in which case it is the
install folder).

A curl install needs a published release, so from a checkout run
`install.sh` directly. It packs a bundle from the checkout, and the images
are named by two separate settings:

- **Tag**: the bundle's version, `v<VERSION>` (the repo's `VERSION` file)
  from a checkout, or whatever `--version <tag>` names. A `--version` tag
  must match `^[A-Za-z0-9][A-Za-z0-9._-]*$`.
- **Prefix** (registry and namespace): `docker.io/automaticrippingmachine`
  unless `--image-prefix <prefix>` is given. It does not change the tag.

It starts the stack by default.

```bash
TEST=/tmp/arm-smoke
ARM="$TEST/arm"
rm -rf "$TEST"
bash install.sh --prefix "$TEST"

# Stack commands go through the install's launcher:
"$ARM/armctl" compose ps

# Wait for backend healthy. First boot logs the admin password to a
# file (in case the terminal scrollback is lost):
docker exec armv3-backend cat /logs/first-boot.log

# Visit https://localhost:8081, log in, change the password, then enroll
# the drive from the UI (the installer does not detect drives).
```

The images that must exist are `<prefix>/arm-backend:<tag>`,
`<prefix>/arm-ui:<tag>` and `<prefix>/arm-ripper:<tag>` (the database uses
`postgres:18`). Unless the profile is ripper-only, so is
`<prefix>/arm-transcode:<tag>`, plus `<prefix>/arm-transcode:<tag>-intel`
or `-amd` only when the host has that GPU vendor and transcodes are not
offloaded.

If those images are not published (a branch build), build and tag them
locally as `<prefix>/arm-...:<tag>`, then install against them with both
settings. [devtools/install-drill.sh](../../../devtools/install-drill.sh) is
the worked example: it builds `arm-drill/arm-backend:drill`,
`arm-ripper:drill` and `arm-ui:drill`, then runs
`bash install.sh --prefix <dir> --bundle <bundle> --version drill --profile ripper-only --image-prefix arm-drill --no-host-changes --no-start`
and `<arm>/armctl up --no-pull`. For a checkout, drop `--bundle` and give
`--version <tag> --image-prefix <prefix> --no-start`, then run
`"$ARM/armctl" up --no-pull`. Without `--version` the tag is `v<VERSION>`, and
`up --no-pull` fails on images tagged anything else.

The settings file is `$ARM/.armctl/.env`; after editing it, run
`"$ARM/armctl" up`. Stop the stack with `"$ARM/armctl" down`.

## Run the test (dev stack path)

```bash
docker compose up -d
docker logs -f arm-ripper-<serial> &          # watch ripper events (enroll the drive from the UI first)
```

## Run the test (ISO fixture — no physical disc needed)

For hosts without a Blu-ray/DVD drive, or for fixture-driven CI-adjacent
runs, use the backend's "Rip from ISO" API
(`docs/developers/architecture/10-iso-source-ripping.md`):
`POST /api/iso/rips` spawns a dedicated, one-shot ripper container for a
chosen `.iso` file. No physical drive is touched or borrowed.
[devtools/iso-smoke.sh](../../../devtools/iso-smoke.sh) drives the whole
flow against the
[matrix256-corpus](https://github.com/shitwolfymakes/matrix256-corpus)
Sintel ISO:

```bash
# .env needs ARM_HOST_ISO_LIBRARY_PATH set; devtools/setup-dev.sh up
# creates arm/iso-library and wires the mount.
docker compose up -d arm-db arm-backend arm-ui       # if not already up
./devtools/iso-smoke.sh
```

The script:

- Pulls `ghcr.io/shitwolfymakes/matrix256-corpus:latest` (falls back to
  Docker Hub, then archive.org) and `docker cp`'s just `sintel.iso`
  out — the BBB layer stays in the registry-side image cache, so only
  ~3.7 GB lands on host disk. SHA-256 is verified against the
  `corpus.lock.json` pin (`7ea69a0…`) on every run; cached at
  `~/arm-corpus/sintel.iso` (override with `ISO_CACHE_DIR`).
- Resolves a MakeMKV key: `MAKEMKV_KEY` env wins (any value MakeMKV
  accepts — a purchased perma-key, a monthly beta you grabbed yourself,
  whatever), otherwise a single forum-scrape attempt. Set `MAKEMKV_KEY`
  explicitly when the forum scrape is flaky (Cloudflare 525s and
  challenge pages, intermittent timeouts) — the in-container scrape
  that the ripper does on boot has the same failure mode.
- Stages the ISO into the ISO library (`ARM_HOST_ISO_LIBRARY_PATH`) and
  calls `POST /api/iso/rips`. The backend creates a virtual drive and
  spawns its own one-shot ripper container (source mode); it never
  pauses or reuses an enrolled drive's container.
- Polls `GET /api/jobs?drive_id=<id>` until the job is ripped, then
  applies the GPU-preferred Plex transcode session and polls until the
  transcode tasks finish.

The ripper container exits on its own once the rip ends. The backend's
watchdog retires the virtual drive within about 30 seconds of the
container exiting; `--no-cleanup` skips the script's own
`DELETE /api/iso/rips/{id}` call and leaves that to the watchdog.

**Gotchas** (already in the matrix's ISO-row notes):

- ~~`mount -o ro,loop /corpus/sintel.iso ...` returns `EPERM` inside the
  container even with `--privileged`, so the CRC64 fingerprint silently
  falls through.~~ **Resolved (commit `fd372371`):** the CRC64 is now read
  straight off the device/ISO via `pydvdid_m.DvdId` (PyCdlib) — no
  loop-mount, no privilege — so the `disc_fingerprints` row and the
  1337server `lookup_by_crc64` fast path now work in the ISO smoke too.
  MakeMKV's `CINFO:1` remains authoritative for `disc_type`.
- The 11.5 GB matrix256-corpus image overflowed `/var/lib/docker` on the
  dev box; the archive.org fallback exists for hosts with the same
  constraint. The fallback is byte-equivalent (corpus.lock pins the same
  archive.org URL the image was built from).
- **BBB BD ISO is blocked between MakeMKV beta releases.** `iso-smoke.sh
  --iso=bbb` is wired up and the ISO extraction path works, but BD scans
  require a non-expired MakeMKV binary — and beta binaries carry a hard
  60-day kill-switch from release date. When upstream is between betas
  (v1.18.3 released 2026-01-25 expired ~2026-03-26 with no v1.18.4 yet
  as of 2026-06-04), every BD scan fails with `MSG:5021 "application
  version is too old"` regardless of `MAKEMKV_KEY`. See
  [MakeMKV in the ripper § Failure modes](../../user/MakeMKV-Ripper.md#failure-modes)
  for the full diagnosis. DVD reads (Sintel) are unaffected because
  CSS doesn't go through the binary's registration gate. The cutover
  criterion at [08-v2-isolation-and-cutover.md § Readiness](../architecture/08-v2-isolation-and-cutover.md#readiness-criteria-for-cutover)
  line 200 is satisfied by the Sintel DVD-ISO row; BBB BD-ISO becomes a
  v3.1 follow-up once a fresh beta binary ships.

## What to verify

For each disc you test, fill in a row and capture the artifacts.

`$ARM` below is the install folder from the fresh-install path (for a dev stack, use the repo's `arm/` folder).

| Disc type | Title                             | Job ID                           | Identified                                                                                                | Tracks ripped | Transcoded                 | Final size | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
|-----------|-----------------------------------|----------------------------------|-----------------------------------------------------------------------------------------------------------|---------------|----------------------------|------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| BD        | *Big Buck Bunny* (2008)           | `job_01KT5H0GB1M705C43Z91FX6WDG` | TMDB movie, hit clean                                                                                     | 6/6           | 6/6 H.265 1080p (NVENC)    | 1.8 GB     | First end-to-end Blu-ray smoke on the dev stack (LG BP50NB40 USB BD/CD drive). Rip 547 s, transcode 477 s, ~17 min insert→terminal. 6.6 GB raw → 1.8 GB transcoded (73 % reduction). `config.auto_rip_on_insert=false` on this dev box, so the rip was kicked via `POST /api/jobs/manual` rather than auto-fired by the poll loop — same code path as the UI's "Start rip" button. **Hardware transcode verified 2026-06-02:** dispatcher claimed `gpu=nvidia://0` (RTX 4070) for every task; spawned `arm-transcode-*` ran with `runtime=nvidia` + `device_requests: [{driver: nvidia, device_ids: [0], capabilities: [gpu, video]}]`; `nvidia-smi -L` visible inside the container; HandBrakeCLI invoked with `--encoder nvenc_h265` appended after `--preset "H.265 MKV 1080p30"`. The `hw_preference=None` `tpr_builtin_plex_1080p_h265` preset already engaged NVENC; re-running the `ses_builtin_movie_plex_1080p_gpu` sibling completed 6 tracks in 470 s wall-clock with identical visual output. Both outputs at `media/Big Buck Bunny (2008)/Big Buck Bunny (2008) - Track NN - plex-1080p-h-265{,-gpu-preferred}.mkv`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| DVD       | *Sintel* (2010)                   | `job_01KR4D63VQSSHYFZTW7G0EMF08` | MakeMKV volume-label fallback (`Sintel_NTSC`, no year), corrected post-rip via the broadened resolve flow | 5/5           | 5/5 H.265 1080p (NVENC)    | 1.1 GB     | DVD rip path proven 4× on Sintel since Phase 12; this row closes the column with the missing transcode evidence. Rip done 2026-05-08 (3.4 GB raw); transcode applied 2026-06-02 via `POST /api/jobs/{id}/transcode` against the Plex 1080p session, 268 s for all 5 tracks (longest = 58 min / 2.1 GB main feature took 268 s alone). 3.4 GB → 1.1 GB (68 % reduction). Title/year were initially patched via SQL because `JobUpdateRequest` only accepted poster overrides — the smoke surfaced that gap as a cutover blocker and the follow-up commit broadens `/resolve` to handle post-rip identity corrections. **Same hardware path as the BD row** — dispatcher claimed `nvidia://0` for every task, `--encoder nvenc_h265` on the HandBrake command line. Output at `media/Sintel (2010)/Sintel (2010) - Track NN - plex-1080p-h-265.mkv`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| CD        | *Dosage* — Collective Soul (1999) | `job_01KT574VNW9870H2CEEQNX5EQZ` | MusicBrainz disc-id `iSN_Kc5V1YL6.R7ll1zCIFrLk0U-`, hit clean                                             | 11/11         | 11/11 FLAC (Music session) | 352 MB     | First end-to-end audio-CD smoke. Insert → terminal ~9.5 min on the dev stack (LG BP50NB40 USB BD/CD drive). Two prior apply-session attempts on the same job failed and surfaced bugs fixed in commit `71a86187` (`-f flac` flag for the atomic-rename suffix; `sanitize_path_component` for the `/` in `Crown / She Said`); the third application completed clean. Output at `media/Collective Soul/Dosage/NN - <Title> - flac.flac`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ISO       | *Sintel* (2010) — DVD ISO         | `job_01KT7B22S48C7M7V64HKZ4C6WA` | MakeMKV CINFO:1 → DVD; OMDB title hit on `Sintel` after `_NTSC` suffix strip                              | 5/5           | 5/5 H.265 1080p (NVENC)    | 1.1 GB     | First fixture-driven smoke (no physical disc). Ticks the cutover criterion at [08-v2-isolation-and-cutover.md § Readiness](../architecture/08-v2-isolation-and-cutover.md#readiness-criteria-for-cutover) line 200 that was deferred to v3.1 as the "BBB ISO rig" — pulled forward into v3.0 via the new `ARM_MANUAL_TRIGGER_ISO` env var on the ripper (commit `b55d977c` + fix `acadeef1`). Sintel ISO from `ghcr.io/shitwolfymakes/matrix256-corpus` (SHA-256 `7ea69a0…`, CC-BY 3.0); downloaded directly from Internet Archive (`https://archive.org/download/sintel_20260427/sintel.iso`, 3.7 GB) because the corpus image at 11.5 GB blew out local Docker storage. Ripper launched with `docker run --privileged -e ARM_MANUAL_TRIGGER_ISO=/corpus/sintel.iso -e MAKEMKV_KEY=<key> -v ~/arm-corpus:/corpus:ro armv3-arm-ripper-sr0` [as run 2026-06-02, predating the drive-lifecycle model; today's equivalent is the enrolled drive's `arm-ripper-<serial>`]. MakeMKV `iso:/corpus/sintel.iso` source URL produced 5 ripping titles + 2 short skips (matches real-disc Sintel exactly). Rip 16 s (3.4 GB raw, sizes match real-disc rip to ~1 byte); NVENC transcode 193 s (5 tracks; longest = 92 s for the 2.2 GB main feature); ~3:30 end-to-end. 3.4 GB → 1.1 GB (68 % reduction). **Gotchas:** (1) loop-mount of the ISO inside the container returned EPERM even with `--privileged` — CRC64 fingerprint didn't compute, but MakeMKV's CINFO:1 was authoritative for disc_type so identify proceeded via OMDB. (2) The MakeMKV-key forum-scrape at container boot is flaky (HTTP 525 from Cloudflare); set `MAKEMKV_KEY` explicitly so the smoke is deterministic. Output at `media/Sintel (2010)/Sintel (2010) - Track NN - plex-1080p-h-265-gpu-preferred.mkv`. |

For each, check:

1. **Disc detection** — within ~10s of insert, ripper logs `drive state
   IDLE -> DISC_OK` and the UI's Jobs tab shows a new row.
2. **Identification** — for video discs, OMDB/community lookup populates
   `title` + `year`; for CDs, MusicBrainz populates artist/album. If
   identification fails, the job sits at `awaiting_user_id` — resolve via
   the UI's "Identify manually" form.
3. **Rip** — after `IDENTIFIED`, status moves to `ripping`. Tracks land
   under `$ARM/raw/<job_id>/` (the `arm` folder you installed into). Track count matches
   what MakeMKV/abcde reports.
4. **Transcode** — Backend dispatches transcode tasks; ephemeral
   `armv3-transcode-*` containers spawn. Final files land under
   `$ARM/media/<title>/...`.
5. **Status terminal** — UI shows `ripped` (or `ripped_partial` if some
   tracks failed). `/api/jobs/<id>` returns the same.
6. **Logs zip** — the per-job log download link returns a non-empty
   `.zip` containing service logs filtered by `job_id` (see Phase 12).

## What to capture

Attach to the PR comment / issue:

- Output of `"$ARM/armctl" compose ps` (proves all 4 services up).
- `$ARM/raw/<job_id>/manifest.json` (or `tree -L 2 $ARM/raw/<job_id>/`).
- `$ARM/media/<title>/...` listing.
- `docker exec armv3-backend cat /logs/arm-backend.log | grep -i error |
  tail -20` (or "(none)" if clean).
- Total elapsed minutes from insert → terminal status.

## Known gotchas

- **MakeMKV beta key expired** — MakeMKV's free beta key rotates every
  ~30 days. If `scan` fails with a licence error, refresh the key in
  `$ARM/.armctl/.env` (`MAKEMKV_KEY=…`) and run `"$ARM/armctl" up`.
- **Audio CD identification can take 30–60s** — MusicBrainz lookups
  with rate-limiting are slow; don't assume the job is stuck.
- **The transcode image is multi-GB.** In dev it's built locally up front
  by `devtools/setup-dev.sh` (tagged `arm-transcode:latest`, never pulled);
  production pulls the versioned image on first dispatch and the Backend logs
  `pulling arm-transcode:…` while the transcode task sits at `queued`.
- **Copy-protected discs.** Some commercial Blu-rays use AACS keys not
  in libaacs's defaults. MakeMKV handles most; some require an updated
  `KEYDB.cfg`. If a rip fails decryption, document it and move to the
  next disc — the v3 priority is the pipeline shape, not the
  copy-protection arms race.

## Done state

Cutover is unblocked when this table has at least one filled row per
disc type and the `Tracks ripped` + `Transcoded` columns are non-empty
for all three.
