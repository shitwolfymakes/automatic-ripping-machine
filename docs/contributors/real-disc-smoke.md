# Real-disc smoke test

Cutover (Phase 16) requires evidence that v3 has rip-transcoded at least
one of each disc type — Blu-ray, DVD, audio CD — on a contributor's
machine, against the same code path users will install via
`curl | bash`. This document is the checklist; results land in the PR
that closes Phase 15.

## Prereqs

- Linux host with Docker ≥ 24, an optical drive, and the disc you're
  testing in the drive.
- Either a fresh `~/arm/` install (preferred — exercises the installer
  too) or a working dev stack at the repo root.

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
data-disc mode and produce no titles. The installer skips drives with
no `scsi_generic` node and warns; the dev compose hardcodes one drive
and offers no warning. Sanity check this first.

## Run the test (fresh install path — preferred)

Use a throwaway prefix so the test doesn't co-mingle with any
in-progress real install.

```bash
TEST=/tmp/arm-smoke
rm -rf "$TEST"
bash install.sh --prefix "$TEST" --start

# Wait for backend healthy. First boot logs the admin password to a
# file (in case the terminal scrollback is lost):
docker exec armv3-backend cat /logs/first-boot.log

# Visit https://localhost:8081, log in, change the password.
```

## Run the test (dev stack path)

```bash
docker compose up -d
docker compose logs -f arm-ripper-sr0 &        # watch ripper events
```

## Run the test (ISO fixture — no physical disc needed)

For hosts without a Blu-ray/DVD drive, or for fixture-driven CI-adjacent
runs, the ripper accepts an `ARM_MANUAL_TRIGGER_ISO` env var that bypasses
the poll loop and runs scan → identify → rip exactly once against an
`.iso` file. [devtools/iso-smoke.sh](../../devtools/iso-smoke.sh)
orchestrates the full flow against the
[matrix256-corpus](https://github.com/shitwolfymakes/matrix256-corpus)
Sintel ISO:

```bash
cd v3
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
- Stops the live `arm-ripper-sr0` (the ISO-mode ripper registers as the
  same `drive_id`, so the two would conflict) and launches a one-shot
  `docker run --privileged` of the ripper image with the ISO bind-mounted
  at `/corpus`.
- Tails the container logs until the `rip-complete` milestone fires,
  then prints the `job_id` along with the `curl` to apply a GPU-preferred
  Plex transcode session and the cleanup commands.

The ripper container idles after the one-shot pipeline (the WS
subscription stays open for cancellation) and the live ripper service
stays stopped — bring it back with
`docker compose up -d arm-ripper-sr0` once you're done with the ISO
smoke.

**Gotchas** (already in the matrix's ISO-row notes):

- `mount -o ro,loop /corpus/sintel.iso ...` returns `EPERM` inside the
  container even with `--privileged`. The CRC64 fingerprint silently
  falls through; MakeMKV's `CINFO:1` from the `iso:` source URL is
  authoritative for `disc_type`, so identify still proceeds via OMDB.
  Loop-mount path needs follow-up work if you rely on the 1337server
  community DB lookup.
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
  [../ops/makemkv.md § Failure modes](../ops/makemkv.md#failure-modes)
  for the full diagnosis. DVD reads (Sintel) are unaffected because
  CSS doesn't go through the binary's registration gate. The cutover
  criterion at [08-v2-isolation-and-cutover.md § Readiness](../arch/08-v2-isolation-and-cutover.md#readiness-criteria-for-cutover)
  line 200 is satisfied by the Sintel DVD-ISO row; BBB BD-ISO becomes a
  v3.1 follow-up once a fresh beta binary ships.

## What to verify

For each disc you test, fill in a row and capture the artifacts.

| Disc type | Title                             | Job ID                           | Identified                                                                                                | Tracks ripped | Transcoded                 | Final size | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
|-----------|-----------------------------------|----------------------------------|-----------------------------------------------------------------------------------------------------------|---------------|----------------------------|------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| BD        | *Big Buck Bunny* (2008)           | `job_01KT5H0GB1M705C43Z91FX6WDG` | TMDB movie, hit clean                                                                                     | 6/6           | 6/6 H.265 1080p (NVENC)    | 1.8 GB     | First end-to-end Blu-ray smoke on the dev stack (LG BP50NB40 USB BD/CD drive). Rip 547 s, transcode 477 s, ~17 min insert→terminal. 6.6 GB raw → 1.8 GB transcoded (73 % reduction). `config.auto_rip_on_insert=false` on this dev box, so the rip was kicked via `POST /api/jobs/manual` rather than auto-fired by the poll loop — same code path as the UI's "Start rip" button. **Hardware transcode verified 2026-06-02:** dispatcher claimed `gpu=nvidia://0` (RTX 4070) for every task; spawned `arm-transcode-*` ran with `runtime=nvidia` + `device_requests: [{driver: nvidia, device_ids: [0], capabilities: [gpu, video]}]`; `nvidia-smi -L` visible inside the container; HandBrakeCLI invoked with `--encoder nvenc_h265` appended after `--preset "H.265 MKV 1080p30"`. The `hw_preference=None` `tpr_builtin_plex_1080p_h265` preset already engaged NVENC; re-running the `ses_builtin_movie_plex_1080p_gpu` sibling completed 6 tracks in 470 s wall-clock with identical visual output. Both outputs at `media/Big Buck Bunny (2008)/Big Buck Bunny (2008) - Track NN - plex-1080p-h-265{,-gpu-preferred}.mkv`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| DVD       | *Sintel* (2010)                   | `job_01KR4D63VQSSHYFZTW7G0EMF08` | MakeMKV volume-label fallback (`Sintel_NTSC`, no year), corrected post-rip via the broadened resolve flow | 5/5           | 5/5 H.265 1080p (NVENC)    | 1.1 GB     | DVD rip path proven 4× on Sintel since Phase 12; this row closes the column with the missing transcode evidence. Rip done 2026-05-08 (3.4 GB raw); transcode applied 2026-06-02 via `POST /api/jobs/{id}/transcode` against the Plex 1080p session, 268 s for all 5 tracks (longest = 58 min / 2.1 GB main feature took 268 s alone). 3.4 GB → 1.1 GB (68 % reduction). Title/year were initially patched via SQL because `JobUpdateRequest` only accepted poster overrides — the smoke surfaced that gap as a cutover blocker and the follow-up commit broadens `/resolve` to handle post-rip identity corrections. **Same hardware path as the BD row** — dispatcher claimed `nvidia://0` for every task, `--encoder nvenc_h265` on the HandBrake command line. Output at `media/Sintel (2010)/Sintel (2010) - Track NN - plex-1080p-h-265.mkv`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| CD        | *Dosage* — Collective Soul (1999) | `job_01KT574VNW9870H2CEEQNX5EQZ` | MusicBrainz disc-id `iSN_Kc5V1YL6.R7ll1zCIFrLk0U-`, hit clean                                             | 11/11         | 11/11 FLAC (Music session) | 352 MB     | First end-to-end audio-CD smoke. Insert → terminal ~9.5 min on the dev stack (LG BP50NB40 USB BD/CD drive). Two prior apply-session attempts on the same job failed and surfaced bugs fixed in commit `71a86187` (`-f flac` flag for the atomic-rename suffix; `sanitize_path_component` for the `/` in `Crown / She Said`); the third application completed clean. Output at `media/Collective Soul/Dosage/NN - <Title> - flac.flac`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ISO       | *Sintel* (2010) — DVD ISO         | `job_01KT7B22S48C7M7V64HKZ4C6WA` | MakeMKV CINFO:1 → DVD; OMDB title hit on `Sintel` after `_NTSC` suffix strip                              | 5/5           | 5/5 H.265 1080p (NVENC)    | 1.1 GB     | First fixture-driven smoke (no physical disc). Ticks the cutover criterion at [08-v2-isolation-and-cutover.md § Readiness](../arch/08-v2-isolation-and-cutover.md#readiness-criteria-for-cutover) line 200 that was deferred to v3.1 as the "BBB ISO rig" — pulled forward into v3.0 via the new `ARM_MANUAL_TRIGGER_ISO` env var on the ripper (commit `b55d977c` + fix `acadeef1`). Sintel ISO from `ghcr.io/shitwolfymakes/matrix256-corpus` (SHA-256 `7ea69a0…`, CC-BY 3.0); downloaded directly from Internet Archive (`https://archive.org/download/sintel_20260427/sintel.iso`, 3.7 GB) because the corpus image at 11.5 GB blew out local Docker storage. Ripper launched with `docker run --privileged -e ARM_MANUAL_TRIGGER_ISO=/corpus/sintel.iso -e MAKEMKV_KEY=<key> -v ~/arm-corpus:/corpus:ro armv3-arm-ripper-sr0`. MakeMKV `iso:/corpus/sintel.iso` source URL produced 5 ripping titles + 2 short skips (matches real-disc Sintel exactly). Rip 16 s (3.4 GB raw, sizes match real-disc rip to ~1 byte); NVENC transcode 193 s (5 tracks; longest = 92 s for the 2.2 GB main feature); ~3:30 end-to-end. 3.4 GB → 1.1 GB (68 % reduction). **Gotchas:** (1) loop-mount of the ISO inside the container returned EPERM even with `--privileged` — CRC64 fingerprint didn't compute, but MakeMKV's CINFO:1 was authoritative for disc_type so identify proceeded via OMDB. (2) The MakeMKV-key forum-scrape at container boot is flaky (HTTP 525 from Cloudflare); set `MAKEMKV_KEY` explicitly so the smoke is deterministic. Output at `media/Sintel (2010)/Sintel (2010) - Track NN - plex-1080p-h-265-gpu-preferred.mkv`. |

For each, check:

1. **Disc detection** — within ~10s of insert, ripper logs `drive state
   IDLE -> DISC_OK` and the UI's Jobs tab shows a new row.
2. **Identification** — for video discs, OMDB/community lookup populates
   `title` + `year`; for CDs, MusicBrainz populates artist/album. If
   identification fails, the job sits at `awaiting_user_id` — resolve via
   the UI's "Identify manually" form.
3. **Rip** — after `IDENTIFIED`, status moves to `ripping`. Tracks land
   under `~/arm/raw/<job_id>/` (or your prefix). Track count matches
   what MakeMKV/abcde reports.
4. **Transcode** — Backend dispatches transcode tasks; ephemeral
   `armv3-transcode-*` containers spawn. Final files land under
   `~/arm/media/<title>/...`.
5. **Status terminal** — UI shows `ripped` (or `ripped_partial` if some
   tracks failed). `/api/jobs/<id>` returns the same.
6. **Logs zip** — the per-job log download link returns a non-empty
   `.zip` containing service logs filtered by `job_id` (see Phase 12).

## What to capture

Attach to the PR comment / issue:

- Output of `docker compose ps` (proves all 4 services up).
- `~/arm/raw/<job_id>/manifest.json` (or `tree -L 2 ~/arm/raw/<job_id>/`).
- `~/arm/media/<title>/...` listing.
- `docker exec armv3-backend cat /logs/arm-backend.log | grep -i error |
  tail -20` (or "(none)" if clean).
- Total elapsed minutes from insert → terminal status.

## Known gotchas

- **MakeMKV beta key expired** — MakeMKV's free beta key rotates every
  ~30 days. If `scan` fails with a licence error, refresh the key in
  `~/arm/.env` (`MAKEMKV_KEY=…`).
- **Audio CD identification can take 30–60s** — MusicBrainz lookups
  with rate-limiting are slow; don't assume the job is stuck.
- **First HandBrake transcode pulls a multi-GB image lazily** —
  `arm-transcode:dev` (or `:v3.x`) is built/pulled on first dispatch.
  The Backend logs `pulling arm-transcode:…` while the user-visible
  transcode task sits at `queued`.
- **Copy-protected discs.** Some commercial Blu-rays use AACS keys not
  in libaacs's defaults. MakeMKV handles most; some require an updated
  `KEYDB.cfg`. If a rip fails decryption, document it and move to the
  next disc — the v3 priority is the pipeline shape, not the
  copy-protection arms race.

## Done state

Cutover is unblocked when this table has at least one filled row per
disc type and the `Tracks ripped` + `Transcoded` columns are non-empty
for all three.
