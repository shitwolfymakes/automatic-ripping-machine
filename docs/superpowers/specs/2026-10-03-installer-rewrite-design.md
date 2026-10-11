# Installer rewrite (`install.sh`, `armctl`, shared deploy library): design

Status: draft for review, 2026-10-03.
Branch: to be decided at planning (see section 15).

## 1. Why

`install.sh` is the production installer, and it has been frozen since
2026-09-05 pending a rewrite. Everything learned since then went into
`devtools/setup-dev.sh` instead. The two have drifted far enough that the
installer no longer describes the stack the backend expects:

- It still enumerates optical drives, emits one `arm-ripper-srN` compose
  service per drive and issues a leaf certificate for each. The backend now
  spawns one ripper per enrolled drive itself and needs `ARM_RIPPER_IMAGE`,
  `CDROM_GID` and the `/dev/disk:/host-disk:ro` mount, none of which the
  installer's compose file passes.
- Its compose file has no `arm-data` volume and no `arm-data-init` service.
- It has no `ARM_TRANSCODE_CAPABLE` and no ripper-only install, and it knows
  nothing of the vendor transcode images (`-intel`, `-amd`) that `release.yml`
  publishes.
- 18 backend environment keys present in `docker-compose.yml.example` are
  missing from its compose file (ripper and dispatcher tuning, notification
  settings, image variants).
- Its udev rule is scoped per drive; `setup-dev.sh` writes a host-wide rule.
- It has no lifecycle. `--start` is `docker compose pull && docker compose up
  -d`. The user docs tell operators to upgrade with those two commands and to
  stop with `docker compose down`, which strands the backend-spawned ripper
  and transcoder containers on the old image.
- A re-run reuses the image tag already in `.env`, so nothing in the
  installer ever moves an install to a newer release.

These findings come from a static comparison of the installer's embedded
compose file and `.env` seeding against `docker-compose.yml.example` and
`setup-dev.sh`. The installer was not run.

The root cause is duplication: two hand-written compose definitions and two
copies of the host-detection and udev functions. This design removes the
duplication instead of re-syncing it.

## 2. Requirements

Agreed with the owner on 2026-10-03.

### 2.1 Audience and end state

- A non-developer on a fresh Debian or Ubuntu host, with no checkout of the
  repository.
- One command ends with the stack running and a URL to open. The UI's
  first-run walkthrough takes over from there.
- Other Linux distros are not refused. They get no automation, only a link to
  Docker's setup docs, and can install ARM if the prerequisites are already
  met.

### 2.2 Host preparation

- If Docker is missing, older than Engine 24, or lacks the Compose v2 plugin,
  the installer offers to install it from Docker's apt repository
  (Debian/Ubuntu only, after a prompt).
- It offers the NVIDIA container toolkit and the udev rule the same way, each
  with consent.

### 2.3 Profiles

- **Full box** (default): rips and transcodes on the same host.
- **Ripper-only**: rips, never transcodes locally.
- **Ripper with remote transcode offload**: transcodes run on another host's
  Docker daemon over SSH. The existing stepped walkthrough (key generation,
  commands to paste on the remote host, per-step verification, completion
  table) stays.
- GPUs are detected, not chosen. The matching transcode image variants are
  pulled.

### 2.4 What the installer asks

- Profile.
- Storage locations for raw rips and finished media, defaulting to folders
  inside the install folder.
- Consent for each host change (Docker, NVIDIA toolkit, udev rule, PATH link
  when it needs sudo).
- The offload inputs, only for that profile.

Everything else is detected or generated: user and group ids, cdrom and
render group ids, GPUs, the release to pin, secrets, certificates.

Rules:

- Every prompt has a flag equivalent, so an unattended run is possible.
- With no terminal and no flags, it takes defaults, skips anything that needs
  consent, and reports what it skipped.
- It runs as the regular user and uses sudo only for host changes. It refuses
  to run as root, because that would record root as the owner of the media
  files, which `arm-data-init` rejects.

### 2.5 Lifecycle

- Start / apply, stop, and upgrade are installer commands.
- Upgrade refuses during an active rip or transcode unless forced, backs up
  the database, pulls, restarts, recreates rippers on the new image, and
  waits for the backend's health check.

### 2.6 Scope limits

- Fresh installs only. There is no migration from the layout the old
  installer produced.
- `devtools/setup-dev.sh` keeps its commands, flags and output exactly as
  they are. Only where its code lives may change. One agreed exception is in
  section 5.5.
- The stack contract, host detection, the udev rule, lifecycle safety and
  certificate generation each have a single definition shared by dev and
  production.
- A change to the compose template must reach production with no extra step
  and no translation rule to add.
- Production's output text and styling are its own and differ from
  `setup-dev.sh`'s.

### 2.7 Non-goals

- No restore, rollback, uninstall or status commands. Those stay in the docs.
- No installer mode for the remote transcode host. It is prepared by pasting
  the printed commands, as today.
- No application settings. Anything the UI walkthrough can set stays there.
- No support for non-Linux hosts or NAS appliances.

## 3. Decisions

| Question | Decision |
|---|---|
| Where the lifecycle lives | A shared library used by both `setup-dev.sh` and production. |
| How a one-file curl install gets shared code | A small bootstrap downloads a release bundle into the install folder and hands over to it. Bundles are assets on GitHub releases. |
| How the operator runs lifecycle commands | A launcher, `armctl`, in the install folder and linked onto the PATH, with guards (section 10). |
| How production's compose file is derived | The dev template is shipped unchanged and layered with a small release overlay. Nothing is translated. |
| Host layout | One folder named `arm` with data directly inside it; configuration under `arm/.armctl/`. |
| After adding the user to the `docker` group | `armctl` restarts itself under the new group with `sg docker`; if that fails it stops and asks the user to log back in and re-run. |
| Production `down` during active work | Refuses unless `--force`. Dev's `down` is unchanged. |
| Rollout | One PR. |

## 4. The pieces and where they live

### 4.1 Repository

| Path | Role |
|---|---|
| `install.sh` (root) | Bootstrap only. From a checkout it runs the `armctl` beside it. From curl it picks the release, downloads that release's bundle into the install folder and hands over. |
| `deploy/armctl` | The launcher: `install`, `up`, `down`, `upgrade`, `compose ...`. |
| `deploy/lib/` | Shared by dev and production (section 5). |
| `deploy/install/` | Production-only: Docker and NVIDIA setup, prompts, storage locations, offload walkthrough, PATH link. |
| `deploy/docker-compose.release.yml` | The overlay naming release images for the services dev builds from source. |
| `docker-compose.yml.example`, `.env.example` | Unchanged. Copied into the bundle as they are. |
| `devtools/setup-dev.sh` | Same commands, flags and output. Its shared functions are loaded from `deploy/lib/`. |
| `.github/workflows/release.yml` | Gains a job that packs the bundle and attaches it to the GitHub release. |

### 4.2 The bundle

The bundle is the contents of `deploy/`, the two unchanged template files and
a version marker, packed as one archive with a checksum file beside it.
Nothing in it is generated or rewritten.

### 4.3 Host layout

```
~/arm/
  armctl                      launcher, also linked onto the PATH
  certs/ db/ raw/ media/ logs/ backups/ scripts/ iso-library/
  .armctl/
    .env                      secrets, pins, profile, detected values
    host-overlay.yml          generated: storage locations, offload settings
    lock                      held while an armctl command runs
    releases/<tag>/           one unpacked bundle per installed release
    current -> releases/<tag>
```

The folder must be named `arm`, because the template writes its paths as
`./arm/...` and `armctl` runs Compose from the folder that contains `arm`. The
location option therefore names where the `arm` folder goes: the default gives
`~/arm`, and `--prefix /srv` gives `/srv/arm`.

Folder permissions follow the current installer: `certs` is 0700; `raw`,
`media` and `logs` are 2775 (setgid, group-writable).

## 5. The shared library

### 5.1 Which version wins

Where both scripts define the same function today, `setup-dev.sh`'s version
becomes the shared one. It is the current model, and using it unchanged is
what keeps dev behavior identical. The installer's older copies are deleted:
GPU detection that probes encoders itself, the per-drive udev rule, drive
enumeration, the embedded compose file.

### 5.2 What moves into `deploy/lib/`

| File | Contents | Comes from |
|---|---|---|
| `common.sh` | prerequisite checks, reading and updating `.env` values | `setup-dev.sh` |
| `detect.sh` | GPU discovery, the NVENC driver floor (`ARM_NVENC_MIN_DRIVER`), render and cdrom group ids | `setup-dev.sh` |
| `certs.sh` | CA and leaf certificate generation | `install.sh` |
| `udev.sh` | the host-wide udev rule and its installation | `setup-dev.sh` |
| `lifecycle.sh` | active-work guard, database backup and pruning, spawned-container cleanup, ripper respawn, retired-service removal, image selection, published-URL lookup, health wait | `setup-dev.sh` |

`ARM_NVENC_MIN_DRIVER` then exists in one shell file. It must still be kept in
step with `NVCODEC_VERSION` in the transcode Dockerfile.

### 5.3 What stays in `setup-dev.sh`

Argument parsing and usage text, the uv, node and npm bootstrap, copying the
template to `docker-compose.yml`, creating `.env` from `.env.example`, writing
`ARM_TRANSCODE_CAPABLE` per run, and the order in which steps run.

### 5.4 How the same functions serve both callers

- **Settings.** The functions already depend on only a few values: the folder
  Compose runs from, the data folder, the `.env` path, the backend and
  database service names, and the three flags (ripper-only, force, no-backup).
  Each caller sets those. The existing variable names are kept so the move is
  cut-and-paste.
- **`compose` helper.** Each caller defines it. `setup-dev.sh` keeps today's
  definition. `armctl` defines it with the template, the overlays, the
  `.env` path and the install folder (section 6).
- **Output helpers.** Shared functions report through caller-supplied helpers
  for status, warning and error lines instead of printing directly.
  `setup-dev.sh` defines them to print exactly what it prints today (`==>`
  lines, `WARNING:` and `ERROR:` to stderr). `armctl` defines them in the
  production style.
- **Command hints.** A few messages name commands that are wrong in
  production, for example `bash devtools/setup-dev.sh up --force` in the
  guard's refusal, or `docker compose logs` in the health wait. Those become
  values each caller supplies.
- **udev rule header.** The rule file names the tool that manages it. That
  name becomes a caller-supplied value, so dev's rule content stays
  byte-identical.

### 5.5 Keeping `setup-dev.sh` identical

Checks:

- Each moved function is compared against its original text at the time of
  the move. Differences are limited to the output-helper and command-hint
  substitutions.
- The existing `devtools/test-setup-dev.sh` assertions pass. That suite reads
  `setup-dev.sh` as text and extracts functions by name, so it has to be
  pointed at the new files. The assertions do not change; the test file does.
- A before-and-after run of `setup-dev.sh` on a dev host, comparing its
  output and the generated `.env` and `docker-compose.yml`.

Agreed exception: `setup-dev.sh` gets its certificates by calling `install.sh
--certs-only`, and that path enumerates drives and issues a leaf certificate
per drive. Nothing uses those certificates, since spawned rippers mount only
the CA. Drive enumeration is removed, so a dev host with drives attached stops
getting those files in `./arm/certs`. `setup-dev.sh` calls the shared
certificate functions directly instead of shelling out to `install.sh`.

## 6. The compose stack in production

### 6.1 Layers

`armctl` always runs Compose with three files, in this order:

1. `docker-compose.yml.example` from the bundle, byte-identical to the
   committed file.
2. `docker-compose.release.yml`: adds `image:` for the services the template
   only builds (`arm-backend`, `arm-data-init`, `arm-ui`), using
   `ARM_IMAGE_PREFIX` and `ARM_IMAGE_TAG`.
3. `host-overlay.yml`: generated per install (section 6.3).

It also passes the project directory (the folder containing `arm`), the
`.env` path, and uses `up --no-build`.

The ripper and transcode images are already variables in the template
(`ARM_RIPPER_IMAGE`, `ARM_TRANSCODE_IMAGE`, `ARM_TRANSCODE_IMAGE_QSV`,
`ARM_TRANSCODE_IMAGE_VAAPI`, `ARM_TRANSCODE_IMAGE_NVENC`). The installer
writes them to `.env` from the prefix and tag. Variant tags follow
`release.yml`: `arm-transcode:<tag>`, `arm-transcode:<tag>-intel`,
`arm-transcode:<tag>-amd`.

### 6.2 Why this needs no translation

A new environment variable, mount or setting added to the template reaches
production on the next release with no further work, because production runs
the template itself.

One residual case: a brand-new service that dev builds from source needs one
`image:` line in the release overlay. A test fails if any service in the
layered production config has no release image (section 11).

### 6.3 The host overlay

Generated by `armctl install` from the saved answers. It holds only:

- **Storage locations**: the `/raw` and `/media` mounts on `arm-backend`,
  when the user chose locations outside the install folder. The matching
  `ARM_HOST_RAW_PATH` and `ARM_HOST_MEDIA_PATH` go into `.env` so spawned
  containers mount the same places.
- **Offload**: the published callback port for `arm-backend` (container port
  8443) and the read-only SSH directory mount. Today's installer splices
  these into its compose file with `awk`; they become overlay entries.

This is the mechanism hifi-server already uses for its NFS paths.

### 6.4 `.env` values that must be explicit

The template defaults `ARM_HOST_RAW_PATH`, `ARM_HOST_MEDIA_PATH`,
`ARM_HOST_LOGS_PATH` and `ARM_HOST_CERTS_PATH` from `${PWD}`, which is the
directory Compose was invoked from. `armctl` can be run from anywhere, so the
installer always writes absolute values for these.

The template sets `name: armv3`, so the project name and the default network
(`armv3_default`) do not depend on the folder Compose runs from.

### 6.5 What was verified, and what was not

A dry run on Docker Compose v5.0.1 with a toy file confirmed:

- With the build folders absent, the layered config passes `config`.
- `pull` fetches every image, including services with `deploy.replicas: 0`.
- `up --no-build` starts cleanly.
- With the project directory set to the parent folder and the compose files
  stored elsewhere, `./arm/raw` resolves to `<parent>/arm/raw`.

Not yet verified, and to be checked first during implementation:

- The same behavior with the real template.
- The same behavior on the oldest Compose v2 release the project supports
  alongside Engine 24.

## 7. Install flow

### 7.1 Bootstrap (`install.sh` from curl)

1. Refuses to run as root.
2. Reads the location and release options and passes every other flag
   through.
3. Picks the release: the named version, or the latest stable on the v3 line
   (the existing `ARM_EXPECTED_MAJOR` check stays).
4. Downloads the bundle and its checksum from the GitHub release, verifies
   it, unpacks it under `.armctl/releases/<tag>/`, sets `current`, and
   creates `armctl`.
5. Hands over to `armctl install` with the terminal attached, so prompts work
   under a curl pipe.

The bootstrap also accepts a local bundle path instead of a download. That is
what the install drill uses, and it allows testing before any GitHub release
exists.

From a checkout, `install.sh` skips steps 3 and 4 and runs `deploy/armctl`
directly.

### 7.2 `armctl install`, in stages

1. **Host**: checks Docker, its version, the compose plugin, the daemon and
   group membership (section 9).
2. **Profile**: full box, ripper-only or remote offload. Offload runs the
   existing walkthrough, moved into `deploy/install/`.
3. **Storage**: asks for the raw and media locations, creates them, checks
   they are writable.
4. **Certificates**: the CA once, then backend, database and UI leaves. The
   backend's leaf carries the offload address when relevant.
5. **Configuration**: writes `.env` (secrets generated once, ids and GPUs
   detected, release pinned, profile recorded, `ARM_TRANSCODE_CAPABLE` set
   from the profile) and the host overlay. Offers the NVIDIA toolkit when an
   NVIDIA GPU is found, and the udev rule.
6. **Start**: runs the same path as `armctl up`, including the health wait.
   On by default, with a flag to skip.
7. **Finish**: the PATH link, the offload verification table when relevant,
   the URL (`https://localhost:8081`), and the first-login and
   certificate-trust hints.

### 7.3 Re-running `armctl install`

- Secrets and the CA are kept. Earlier answers become the defaults, and a run
  with no terminal keeps them.
- Detected values (GPUs, group ids) are refreshed.
- The profile is remembered. This differs from dev, where `--ripper-only`
  applies per run, and the difference is deliberate: a non-developer should
  not have to repeat it on every command.

### 7.4 Flags

- **New**: profile, raw and media locations, accept or decline host changes,
  skip start, version, local bundle path, and the offload inputs.
- **Kept**: location (`--prefix`), `--rotate-ca`, `--release-repo`.
- **Removed**: `--certs-only`, `--no-env`, `--no-compose`, `--no-udev`, which
  existed so `setup-dev.sh` could call the installer. `--start` is removed
  because starting is the default.

An unattended offload install can supply the inputs, but the commands pasted
on the remote host stay manual. The run verifies each step and reports what
is missing.

## 8. Lifecycle commands

### 8.1 `armctl up`

The same order as `setup-dev.sh up`, with pulling in place of building:

1. **Pull** the images this host needs: the base transcode image unless the
   profile is ripper-only, the Intel or AMD variants only when that GPU is
   present, and no variants when transcodes are offloaded. A failed pull
   stops here with the running stack untouched.
2. **Guard**: refuses while a rip or transcode is active, unless `--force`.
3. **Refresh** the detected GPUs in `.env`.
4. **Back up** the database into `~/arm/backups/`, keeping the newest five.
   `--no-backup` skips it.
5. **Remove** the spawned rippers and transcoders, and containers of retired
   services.
6. **Start** from the pulled images, and recreate rippers if the backend kept
   running.
7. **Wait** up to 90 seconds for the backend's health check, then print the
   URL.

### 8.2 `armctl upgrade [--version <tag>]`

1. Picks the target: the latest stable v3, or the named version. If the
   install is already on it, it says so and stops.
2. Downloads, verifies and unpacks the new bundle beside the current one.
   Nothing live has changed yet.
3. Hands over to the new release's `armctl`, which pulls the new images, runs
   the guard and takes the backup. Still nothing live has changed.
4. Switches: records the new version in `.env`, re-applies the saved install
   answers so new settings get their defaults, and points `current` at the
   new release.
5. Removes spawned containers, starts, recreates rippers, waits for health.

The previous release's folder is kept for a manual rollback. Older ones are
pruned.

### 8.3 `armctl down`

Refuses while a rip or transcode is active, unless `--force`. Then removes the
spawned rippers and transcoders and stops the stack.

### 8.4 `armctl compose ...`

Passes any Compose command through with the right files, `.env` and project
directory. `armctl compose ps` and `armctl compose logs arm-backend` replace
the bare `docker compose` forms in the docs, since typing `docker compose` in
the install folder no longer finds the files.

### 8.5 Failure behavior

- **Before the switch**, any failure (network, registry, checksum, active
  work, backup) leaves the running install exactly as it was, and the message
  says so.
- **After the switch**, a failed start or health check is reported with the
  last backend log lines, the location of the backup just taken, and a
  pointer to the rollback page. There is no automatic rollback, because
  database migrations cannot be reversed.
- **One at a time.** A lock in `.armctl/` stops two `armctl` runs overlapping.
- **No terminal** never blocks on a prompt: defaults are taken and skipped
  steps are listed.

## 9. Docker setup

`armctl install` distinguishes these cases and reports which one it found:
Docker not installed, Engine older than 24, compose plugin missing, daemon
not running, user not in the `docker` group.

- **Debian/Ubuntu**: after a prompt, it installs Docker Engine and the
  compose plugin from Docker's apt repository and adds the user to the
  `docker` group.
- **Other distros**: it prints a link to Docker's setup docs and stops. If
  the prerequisites are already met, the install proceeds.
- **Group membership**: the new group only applies to new login sessions.
  `armctl` restarts itself under the group with `sg docker` and continues.
  It applies the same check on every later command, so `armctl up` works
  before the user has logged out and back in. If `sg` is missing or the
  restart fails, it stops, explains that a new login is needed, and prints
  the command to run afterwards; the second run picks up where the first
  stopped.

## 10. PATH link

- Links `armctl` into `~/.local/bin` only when that directory is already on
  the PATH.
- Otherwise offers `/usr/local/bin` with a sudo prompt. With no terminal it
  skips the link.
- Never replaces an existing `armctl` that it did not create.
- Whenever it skips, the end-of-install message prints the full-path form
  (`~/arm/armctl ...`) instead.

## 11. Testing

All of the following are zero-infra and run in CI's shell job.

- **`devtools/test-setup-dev.sh`**: same assertions, pointed at `deploy/lib/`.
- **`devtools/test-install-walkthrough.sh`**: the offload walkthrough tests,
  pointed at the moved code through the same source-only seam.
- **New `armctl` suite**, with Docker, curl and sudo replaced by stand-ins:
  - bootstrap option parsing, release selection and checksum rejection
  - Docker diagnosis for each case in section 9
  - profile and storage answers turning into the right `.env` and host
    overlay
  - the PATH-link guards, the lock, and refusal to run as root
  - upgrade ordering, including that a failure before the switch leaves
    `current` untouched
  - the guard on `down`
- **Stack contract test**: the template layered with the release overlay
  passes `docker compose config`, every service has a release image, and
  every path lands inside the install folder. It falls back to text checks
  when Docker is absent, as the existing suite does.
- **Bundle test**: the packed bundle has the expected files, and the template
  inside is byte-identical to the committed one.
- **shellcheck** covers the new files through the existing pre-commit hook.

Not in CI:

- **Install drill**: a script that packs the bundle locally and installs it
  into a temporary folder against locally built images.
- **The `setup-dev.sh` before-and-after comparison** from section 5.5.

## 12. Release pipeline

- `release.yml` gains a job that packs the bundle, writes its checksum, and
  attaches both to the GitHub release. The workflow has read-only repository
  permission today; this job needs write permission on releases. Actions are
  pinned to commit SHAs as elsewhere.
- CI packs the bundle on every PR, so a packaging break is caught before a
  tag.

## 13. Docs and memory

- **User pages**: Getting Started, Upgrading, Uninstall, Home, FAQ, and
  Configuring ARM (which describes manual steps for a ripper-only production
  install "until the installer rewrite lands").
- **Developer pages**: `06-deployment.md`, `05-cross-cutting.md`
  (certificates), `02-job-lifecycle.md`, and `devtools/README.md`.
- **Comments in `.env.example`** that describe what `install.sh` does.
- **`CLAUDE.md`**: the layout section gains `deploy/`.
- **Project memory**: the "install.sh is legacy" entry is retired. The NVENC
  pin entry names one shell location instead of two. The entries that parked
  installer follow-ups (no-transcode mode, encoder-first presets) are updated
  to say they are done.

The carryover document the legacy memory entry points to
(`../arm-ai/arm-v3/docs/installer-rewrite-carryover.md`) was not found on the
development machine. The parked notes that survive are the ones in those
memory entries: the missing `ARM_TRANSCODE_CAPABLE` passthrough and the
installer's lack of image-variant awareness. Both are covered by this design.

## 14. Rollout

One PR, containing the library extraction, `armctl`, the production install
stages, the release overlay, the release job, the tests and the docs.

Inside the PR the work is ordered so each step can be checked alone:

1. Extract the shared library from `setup-dev.sh`, with output helpers and
   repointed tests. Verified with the before-and-after comparison.
2. `armctl`, the production install stages and the release overlay, with the
   new suites. Root `install.sh` becomes the bootstrap and the old code is
   deleted.
3. The bundle job in `release.yml` and the CI packaging check.
4. Docs and memory.

## 15. Open items for planning

- **Base branch.** The current branch is `integration/all-prs-3`, and step 1
  changes `setup-dev.sh`, which the existing PR stack is also changing.
- **Compose verification** against the real template and the oldest supported
  Compose release (section 6.5).
- **Docker's apt repository steps** for the supported Debian and Ubuntu
  releases, and which releases those are.
- **Checksum scheme** for the bundle (a sha256 file beside the archive is the
  assumption; the images use cosign, which the host is not required to have).
