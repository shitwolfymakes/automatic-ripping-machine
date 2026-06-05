# Known Issues

Current limitations of ARM v3, with workarounds where they exist. For
in-the-weeds debugging see [Troubleshooting](Troubleshooting); for what's planned
see the [Roadmap](Status-Roadmap).

## v3 is in alpha

v3 is under active development. Expect rough edges, breaking changes between
versions, and incomplete docs.

- **Published images may not exist for every tag yet.** `docker compose pull`
  can return 404 during the alpha. Build the images locally from a checkout —
  see
  [Local development in the README](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/README.md#local-development).

## Platform limitations

- **Windows / macOS can't rip.** Docker Desktop can't pass an internal SATA
  optical drive into its Linux VM. You can run the UI + transcoder as a
  library-management frontend (over a WSL2-native path, a named volume, or an SMB
  mount — **not** an NTFS `C:\...` bind mount, where file ownership is faked),
  but ripping requires a Linux host.
- **TrueNAS, Kubernetes/Helm, and Podman are not supported.** TrueNAS in
  particular is explicitly out of scope — please don't file bugs against it.
  Unraid and Synology run stock Docker and work.

## Operational gotchas

- **Desktop hosts need auto-mount disabled to eject.** On a host with a GNOME/
  KDE/XFCE session, `udisks2`/`gvfs` grabs the disc and the ripper can't eject
  after a rip. The installer writes a scoped udev rule to fix this; if you
  installed manually or eject still fails, see
  [Troubleshooting § Disc won't eject](Troubleshooting#disc-wont-eject-after-a-rip).
- **No database schema rollback.** Alembic `downgrade` across versions isn't
  supported — back up Postgres before upgrading if you want a safety net. See
  [Upgrading](Upgrading).
- **MakeMKV beta binary expiry.** MakeMKV beta binaries self-expire (~60 days),
  which blocks Blu-ray/UHD reads (DVDs are unaffected) until upstream ships a new
  beta and the ripper image is rebuilt. No registration key overrides this. See
  [MakeMKV](MakeMKV).

## Not built yet

- **Ripping from an `.iso` file** (vs a physical disc) is designed but not
  implemented as a user-facing feature. ARM can produce an `.iso` *from* a disc
  today. See [Roadmap](Status-Roadmap).

---

Found something not listed here? Search the
[issue tracker](https://github.com/automatic-ripping-machine/automatic-ripping-machine/issues)
and open a new issue if it's not already tracked.
