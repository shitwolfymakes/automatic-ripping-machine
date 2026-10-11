# Upgrading

ARM v3 upgrades are image-pulls — you don't rebuild or re-clone anything. The
backend runs any pending database migrations on startup, so the schema moves
forward automatically.

> Coming from **ARM v2**? There is no in-place upgrade path. v3 shares no code,
> no database, and no config format with v2. Treat it as a fresh install
> ([Getting Started](Getting-Started)); v2 stays frozen and
> the two stacks can even run side by side (their containers and volumes are
> namespaced `armv3-*` vs `arm-*`).

## Upgrade

```bash
armctl upgrade
```

That moves the install to the latest stable release. In order, it:

1. downloads the new release's installer bundle and checks it;
2. pulls the new images;
3. refuses to go further while a rip or transcode is running;
4. backs up the database into `~/arm/backups/` (the newest five are kept);
5. switches to the new release, restarts the stack and recreates the rippers;
6. waits for the backend to report healthy.

Until step 5, nothing about the running install has changed, so a failed
download, a failed pull or an active rip leaves it exactly as it was. Run the
command again when the cause is fixed.

Options:

| Option | Effect |
|---|---|
| `--version v3.1.0` | Move to that release instead of the latest stable one. The tag may contain only letters, digits, `.`, `_` and `-`, and must start with a letter or digit. |
| `--force` | Go ahead while a rip or transcode is running. It is killed. |
| `--no-backup` | Skip the database backup. |

If `armctl` is not on your PATH, use `~/arm/armctl upgrade`.

If the start or the health check fails after the switch, `armctl` says so and
prints which release the install is now on, that it was **not** rolled back,
the database backup taken in that run (or that none was taken), and where the
previous release is kept. Once the cause is fixed, `armctl up` tries the start
again. See [Rolling back](#rolling-back).

If an upgrade stops part way (a power cut, for example), what to run depends
on where it stopped:

- During the switch, after `current` points at the new release but before
  `.env` is replaced: run the same command again, with the same `--version`
  if you gave one (`armctl upgrade --version <tag>`). It notices and finishes
  the upgrade. A plain `armctl upgrade` would aim at the latest stable
  release, which may not be the one you were moving to. `armctl up` refuses
  to start in this state and prints the command to run.
- After the switch, while the stack was starting: run `armctl up`. The install
  is already on the new release. `armctl upgrade` does not start it: it prints
  "already on <tag>; nothing to upgrade" when that is the latest stable
  release, refuses to move to the latest stable when the installed release is
  a newer pre-release, and upgrades again when a newer stable release exists.

With no `--version`, `armctl upgrade` never moves to an older release than the
one installed (for example from a pre-release to an older stable one). Name the
release with `--version <tag>` to do that on purpose.

To change an answer you gave at install time (profile, storage folders),
run `armctl install` again. It keeps your secrets and certificate authority
and asks the same questions with your earlier answers as the defaults.

## Before you upgrade

- **No schema rollback.** Alembic `downgrade` is not supported across versions.
  `armctl upgrade` takes a database backup before it switches; the files are in
  `~/arm/backups/` and contain plaintext secrets, so treat them like a password
  export.

- **Watch the release notes / [CHANGELOG](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/CHANGELOG.md)**
  for any manual steps a specific release calls out.

## Rolling back

There is no automatic rollback, because a database migration cannot be
reversed. `armctl upgrade` keeps the previous release in
`~/arm/.armctl/releases/` and the backup it took in `~/arm/backups/`.

If the schema did not change between the two releases, going back is:

    armctl upgrade --version <previous tag>

If it did, restore the backup taken before the upgrade into a fresh database
first, then run the same command.
