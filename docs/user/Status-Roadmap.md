# Roadmap

ARM v3 is the greenfield rebuild that the v2-era roadmap pointed toward. Most of
that plan has now shipped; this page tracks what's done and what's still ahead.
The authoritative, per-phase plan lives in the repo at
[`docs/plans/MASTER_IMPLEMENTATION_PLAN.md`](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/docs/plans/MASTER_IMPLEMENTATION_PLAN.md).

## Shipped in v3

The architectural goals that defined v3 are in place:

- **Service split.** The monolithic v2 container is gone. v3 is a FastAPI
  backend, a SvelteKit UI, Postgres, one ripper container per drive, and an ephemeral
  per-job transcoder — wired together with `docker compose`.
- **Database.** Moved off SQLite. v3 runs on **Postgres** (the v2 roadmap
  guessed MySQL; the rebuild landed on Postgres with async SQLAlchemy/Alembic).
- **Rewrite + tests.** Ripper and UI are new codebases with a `pytest` suite and
  a backend statement-coverage policy.
- **Sessions and presets.** Sessions, rip presets, and transcode presets are
  implemented and user-editable in the UI — including music to FLAC/MP3, data
  copy, and ISO dump from a disc. See [Web UI](Web-UI).
- **One-command install.** A single `install.sh` sets up the whole stack,
  including TLS certs and the `armctl` command that runs it. See
  [Getting Started](Getting-Started).
- **Notifications** via Apprise, configured from the UI.
- **GPU transcoding** for Intel QSV / AMD VAAPI / NVIDIA NVENC via an opt-in
  overlay. See [Hardware Transcoding](Hardware-Transcoding).
- **Ripping from an `.iso` source** (vs a physical disc). The gear menu's
  **Rip from ISO** picker lets an operator pick an `.iso` from a read-only
  library folder on the server; ARM spawns a dedicated virtual ripper for it
  and runs it through the normal scan, identify, rip and transcode pipeline.
  See
  [`docs/developers/architecture/10-iso-source-ripping.md`](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/docs/developers/architecture/10-iso-source-ripping.md).

## In progress / ahead

- **Stabilising the alpha** toward a v3.0 release: published, signed images for
  every supported platform, and CI-built release tags. See
  [Known Issues](Status-Known-Issues).
- **TV-series-aware ripping**: episode matching and the **Match Episodes** tab
  are built (see the Web UI page); naming conventions and further session
  ergonomics, building on the sessions/presets foundation, are still to come.
- **Maintenance tools**: find and remove orphaned media folders and log files,
  clean up finished transcode jobs, and clear the raw rip area from the UI. The
  buttons are hidden until these endpoints exist in v3.
- **First-run setup wizard**: a guided first boot (drive scan, readiness
  checks, settings review). Built in the UI, switched off until the v3 setup
  status endpoints land.
- **Extracted disc folders as a rip source** (a `BDMV` or `VIDEO_TS` folder
  already on disk, rather than an `.iso` file). Next up for the ISO-source
  picker; see the non-goals in the design doc linked above.

## Where to follow along

- Per-phase plan: [`docs/plans/MASTER_IMPLEMENTATION_PLAN.md`](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/docs/plans/MASTER_IMPLEMENTATION_PLAN.md)
- Architecture docs: [`docs/developers/architecture/`](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/docs/developers/architecture/README.md)
- Issues and discussions:
  [issue tracker](https://github.com/automatic-ripping-machine/automatic-ripping-machine/issues) ·
  [discussions](https://github.com/automatic-ripping-machine/automatic-ripping-machine/discussions)

Have an opinion on what should come next? Open a discussion — feature direction
is shaped with the community.
