# MakeMKV in the ARM v3 ripper

The ripper container builds MakeMKV from the upstream signed source tarballs in a multistage Dockerfile. No license is bundled in the image — every container needs a working `app_Key` at runtime, which is what `update_key.sh` provides.

## Setting the key

There are two paths, picked at container start:

1. **Operator-supplied key** — set `MAKEMKV_KEY=T-…` in the ripper service environment (typically `v3/.env`). Any value MakeMKV accepts: a purchased perma-key, a monthly beta you grabbed yourself, whatever — the entrypoint just writes it into `~/.MakeMKV/settings.conf` on every boot, idempotently.
2. **Scraped monthly beta key** — leave `MAKEMKV_KEY` unset. The entrypoint scrapes the current month's beta from the public MakeMKV forum thread (`https://forum.makemkv.com/forum/viewtopic.php?f=5&t=1053`) and writes that. This is the same approach v2 has shipped for years; no MakeMKV terms are violated as long as the beta key is openly published there. The scrape is brittle (the forum sits behind Cloudflare and rate-limits / 525s under load); operators hitting that should switch to path 1.

The key path is `/home/arm/.MakeMKV/settings.conf` inside the container. The Dockerfile pre-creates the directory and chowns it to UID 1000; the shared entrypoint chowns again on `PUID` changes.

## Verifying the key after start

```sh
docker compose exec ripper grep app_Key /home/arm/.MakeMKV/settings.conf
```

If the file is missing or has no `app_Key` line, check the ripper logs for `update_key:` output — the script logs whether it used `MAKEMKV_KEY` from env or scraped, and prints a warning if the scrape returned nothing.

## When the beta key rotates

The free beta key rotates roughly monthly. The entrypoint runs `update_key.sh` on every container start, so a `docker compose restart ripper` (or any image rebuild) refreshes the key automatically. If you go a few months without restarting, MakeMKV will start refusing to scan protected discs until the next restart.

## Failure modes

- **Forum scrape returns nothing** — the script logs the scrape failure and exits 0; `settings.conf` keeps whatever key was there. Existing discs with the previous key continue to work; new MakeMKV releases may eventually invalidate the cached key.
- **`MAKEMKV_KEY` is malformed** — MakeMKV rejects it on first scan. Symptom is a `makemkvcon` exit code with `App key incorrect` in the logs. Replace the env var and restart.
- **`/home/arm` not writable** — only happens if the container runs with a `PUID` that doesn't own `/home/arm`. The shared entrypoint re-chowns on every boot, but if the directory is bind-mounted from a host with mismatched ownership, fix the host permissions.

## What the install scripts do

- [services/ripper/install/install_makemkv.sh](../../services/ripper/install/install_makemkv.sh) — port of v2's `temp_install_makemkv.sh` (itself derived from tianon/dockerfiles). Scrapes the current MakeMKV version, fetches the GPG-signed `sha256sums.txt`, downloads `makemkv-oss` and `makemkv-bin` tarballs, verifies both, builds OSS, accepts the bin EULA, installs to `/usr/local`. Runs only in the build stage of the Dockerfile; the runtime image just copies the resulting binary and shared libraries.
- [services/ripper/install/update_key.sh](../../services/ripper/install/update_key.sh) — port of v2's `scripts/update_key.sh`. Idempotent. Called by the shared docker entrypoint when both `update_key.sh` and `makemkvcon` are present, so backend / transcode containers no-op past it.
