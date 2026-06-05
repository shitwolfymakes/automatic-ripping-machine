# TODO

Tracked follow-ups that don't yet have an issue. Keep this short — promote an
item to a GitHub issue once it's actively being worked.

## Installer: pin compose to the newest stable release

The install script will (long term) generate/update the user's
`docker-compose.yml` to pull the service images for the **latest stable v3
release**, rather than `:latest`.

- `:latest` tracks `main` HEAD (rolling, rebuilt nightly) and is **not** a
  support target — see [SECURITY.md](SECURITY.md). Production installs must run
  a stable tag.
- Resolve "latest GitHub release" to the **newest stable `v3.*` tag, skipping
  pre-releases** (`-RC` / `-alpha` / `-beta`) — mirror the tag-selection logic
  in [.github/workflows/weekly-rebuild.yml](.github/workflows/weekly-rebuild.yml)
  (`git tag --list 'v3.*' --sort=-v:refname | grep -v -- '-' | head -n1`).
- Re-running the installer should bump the pinned tag to the newest stable
  release.

## ISO-source ripping (from PR #2)

First-class "rip from an `.iso` as a source" — distinct from the existing
`output_mode='iso'` (which produces an ISO *from* a disc).

- Design proposal: [docs/arch/10-iso-source-ripping.md](docs/arch/10-iso-source-ripping.md).
- Implement as **ephemeral, backend-spawned worker containers** (the
  transcode-dispatcher model), **not** a long-running service.
- Eventual front door is UI file upload.
- Six open decisions in the doc to settle before implementation.

## MakeMKV permanent key in Config (from PR #2)

Persist the MakeMKV registration key as a Config setting, settable from the UI,
so rippers don't depend on the `MAKEMKV_KEY` env var or the monthly beta-key
forum scrape.
