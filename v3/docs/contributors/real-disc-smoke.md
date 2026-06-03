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
  too) or a working v3 dev stack at `v3/`.

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
bash v3/install.sh --prefix "$TEST" --start

# Wait for backend healthy. First boot logs the admin password to a
# file (in case the terminal scrollback is lost):
docker exec armv3-backend cat /logs/first-boot.log

# Visit https://localhost:8081, log in, change the password.
```

## Run the test (dev stack path)

```bash
cd v3
docker compose up -d
docker compose logs -f arm-ripper-sr0 &        # watch ripper events
```

## What to verify

For each disc you test, fill in a row and capture the artifacts.

| Disc type | Title                             | Job ID                           | Identified                                                      | Tracks ripped | Transcoded                 | Final size | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
|-----------|-----------------------------------|----------------------------------|-----------------------------------------------------------------|---------------|----------------------------|------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| BD        | *Big Buck Bunny* (2008)           | `job_01KT5H0GB1M705C43Z91FX6WDG` | TMDB movie, hit clean                                           | 6/6           | 6/6 H.265 1080p (CPU)      | 1.8 GB     | First end-to-end Blu-ray smoke on the dev stack (LG BP50NB40 USB BD/CD drive). Rip 547 s, transcode 477 s, ~17 min insert→terminal. 6.6 GB raw → 1.8 GB transcoded (73 % reduction). `config.auto_rip_on_insert=false` on this dev box, so the rip was kicked via `POST /api/jobs/manual` rather than auto-fired by the poll loop — same code path as the UI's "Start rip" button. Output at `media/Big Buck Bunny (2008)/Big Buck Bunny (2008) - Track NN - plex-1080p-h-265.mkv`. |
| DVD       | *Sintel* (2010)                   | `job_01KR4D63VQSSHYFZTW7G0EMF08` | OMDB hit (resolved post-rip — original identify left year null) | 5/5           | 5/5 H.265 1080p (CPU)      | 1.1 GB     | DVD rip path proven 4× on Sintel since Phase 12; this row closes the column with the missing transcode evidence. Rip done 2026-05-08 (3.4 GB raw); transcode applied 2026-06-02 via `POST /api/jobs/{id}/transcode` against the Plex 1080p session, 268 s for all 5 tracks (longest = 58 min / 2.1 GB main feature took 268 s alone). 3.4 GB → 1.1 GB (68 % reduction). Output at `media/Sintel (2010)/Sintel (2010) - Track NN - plex-1080p-h-265.mkv`.                            |
| CD        | *Dosage* — Collective Soul (1999) | `job_01KT574VNW9870H2CEEQNX5EQZ` | MusicBrainz disc-id `iSN_Kc5V1YL6.R7ll1zCIFrLk0U-`, hit clean   | 11/11         | 11/11 FLAC (Music session) | 352 MB     | First end-to-end audio-CD smoke. Insert → terminal ~9.5 min on the dev stack (LG BP50NB40 USB BD/CD drive). Two prior apply-session attempts on the same job failed and surfaced bugs fixed in commit `71a86187` (`-f flac` flag for the atomic-rename suffix; `sanitize_path_component` for the `/` in `Crown / She Said`); the third application completed clean. Output at `media/Collective Soul/Dosage/NN - <Title> - flac.flac`.                                              |

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
