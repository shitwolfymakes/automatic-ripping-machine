# Roadmap

ARM v3 is the greenfield rebuild that the v2-era roadmap pointed toward. Most of
that plan has now shipped; this page tracks what's done and what's still ahead.
The authoritative, per-phase plan lives in the repo at
[`docs/plans/MASTER_IMPLEMENTATION_PLAN.md`](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/docs/plans/MASTER_IMPLEMENTATION_PLAN.md).

## Shipped in v3

The architectural goals that defined v3 are in place:

- **Service split.** The monolithic v2 container is gone. v3 is a FastAPI
  backend, a Vue UI, Postgres, one ripper container per drive, and an ephemeral
  per-job transcoder — wired together with `docker compose`.
- **Database.** Moved off SQLite. v3 runs on **Postgres** (the v2 roadmap
  guessed MySQL; the rebuild landed on Postgres with async SQLAlchemy/Alembic).
- **Rewrite + tests.** Ripper and UI are new codebases with a `pytest` suite and
  a backend statement-coverage policy.
- **Sessions and presets.** Sessions, rip presets, and transcode presets are
  implemented and user-editable in the UI — including music to FLAC/MP3, data
  copy, and ISO dump from a disc. See [Web UI](Web-UI).
- **One-command install.** A single `install.sh` generates the whole stack,
  including TLS certs and per-drive service blocks. See
  [Getting Started](Getting-Started).
- **Notifications** via Apprise, configured from the UI.
- **GPU transcoding** for Intel QSV / AMD VAAPI / NVIDIA NVENC via an opt-in
  overlay. See [Hardware Transcoding](Hardware-Transcoding).

## In progress / ahead

- **Stabilising the alpha** toward a v3.0 release: published, signed images for
  every supported platform, and CI-built release tags. See
  [Known Issues](Status-Known-Issues).
- **Ripping from an `.iso` source** (vs a physical disc) — designed but not yet
  built as a user feature. Design doc:
  [`docs/arch/10-iso-source-ripping.md`](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/docs/arch/10-iso-source-ripping.md).
- **TV-series-aware ripping** (episode detection and naming conventions) and
  further session ergonomics, building on the sessions/presets foundation.

## Where to follow along

- Per-phase plan: [`docs/plans/MASTER_IMPLEMENTATION_PLAN.md`](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/docs/plans/MASTER_IMPLEMENTATION_PLAN.md)
- Architecture docs: [`docs/arch/`](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/docs/arch/README.md)
- Issues and discussions:
  [issue tracker](https://github.com/automatic-ripping-machine/automatic-ripping-machine/issues) ·
  [discussions](https://github.com/automatic-ripping-machine/automatic-ripping-machine/discussions)

Have an opinion on what should come next? Open a discussion — feature direction
is shaped with the community.
