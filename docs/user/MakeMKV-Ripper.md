# MakeMKV in the ARM v3 ripper

The ripper container builds MakeMKV from the upstream signed source tarballs in a multistage Dockerfile. No license is bundled in the image — every container needs a working `app_Key` at runtime, which is what `update_key.sh` provides.

## Setting the key

`update_key.sh` runs once before every rip (see [When the beta key rotates](#when-the-beta-key-rotates) below) and picks one of three paths each time, in precedence order:

1. **Key configured in the UI** *(recommended)* — set the MakeMKV key in **Config → MakeMKV key** (`Config.makemkv_key`). The ripper fetches it from the backend at the top of each rip and injects it into `update_key.sh` as `MAKEMKV_KEY`, so a UI-set key wins over a host-set env var. This is the only path that survives a `docker compose down`/recreate without re-editing files, and it can be changed without a restart. Any value MakeMKV accepts: a purchased perma-key or a beta you grabbed yourself.
2. **Operator-supplied env key** — set `MAKEMKV_KEY=T-…` in the ripper service environment (typically `.env`). Used when no key is configured in the UI. The script writes it into `~/.MakeMKV/settings.conf`, idempotently.
3. **Scraped monthly beta key** — leave both the UI key and `MAKEMKV_KEY` unset. The script scrapes the current month's beta from the public MakeMKV forum thread (`https://forum.makemkv.com/forum/viewtopic.php?f=5&t=1053`) and writes that. This is the same approach v2 has shipped for years; no MakeMKV terms are violated as long as the beta key is openly published there. The scrape is brittle (the forum sits behind Cloudflare and rate-limits / 525s under load); operators hitting that should switch to path 1 or 2.

The key path is `/home/arm/.MakeMKV/settings.conf` inside the container. The Dockerfile pre-creates the directory and chowns it to UID 1000; the shared entrypoint chowns again on `PUID` changes.

## Verifying the key after start

```sh
docker compose exec ripper grep app_Key /home/arm/.MakeMKV/settings.conf
```

If the file is missing or has no `app_Key` line, check the ripper logs for `update_key:` output — the script logs whether it used `MAKEMKV_KEY` from env or scraped, and prints a warning if the scrape returned nothing.

## When the beta key rotates

The free beta key rotates roughly monthly. The ripper's `JobController` runs `update_key.sh` at the top of each disc's pipeline — before the makemkvcon scan probe, and again before a crash-resumed rip (which skips the scan). This is the v3 port of v2's `prep_mkv`; see [`makemkv_key.py`](../../services/ripper/arm_ripper/makemkv_key.py). A container left up across a key rotation therefore self-heals on the next disc — no restart needed. (Earlier v3 builds scraped only at container boot; that boot-time hook was dropped once the per-rip refresh covered every run.)

The per-rip refresh is non-fatal: a transient forum-scrape failure leaves the existing key in place and lets makemkvcon proceed (it surfaces a genuinely dead key downstream as `App key incorrect` or, for binary expiry, `MSG:5021`). When a key is configured (UI or `MAKEMKV_KEY`), the script writes that operator key instead of scraping, so there is no forum traffic per rip. A backend lookup error while fetching the UI key is also non-fatal — the ripper falls back to the env var / scrape rather than blocking the rip.

## Failure modes

- **Forum scrape returns nothing** — the script logs the scrape failure and exits 0; `settings.conf` keeps whatever key was there. Existing discs with the previous key continue to work; new MakeMKV releases may eventually invalidate the cached key.
- **`MAKEMKV_KEY` is malformed** — MakeMKV rejects it on first scan. Symptom is a `makemkvcon` exit code with `App key incorrect` in the logs. Replace the env var and restart.
- **Binary itself is expired (MSG:5021 "application version is too old")** — MakeMKV beta binaries carry a hard 60-day kill-switch from their release date. *No* registration key overrides this; the binary refuses to do protected-disc work before it even checks `settings.conf`. When upstream is between releases (binary expired, no newer source tarball published yet on <https://www.makemkv.com/download/>) the only fix is to wait for the next beta. Symptom: every `makemkvcon` invocation emits `MSG:5021,131332,1,"This application version is too old…"` and exits before any disc work happens, regardless of what `MAKEMKV_KEY` you set. **DVD reads are unaffected** — only operations that need the AACS-gated bits (BD, UHD, AACS-protected DVDs) trip the check. Workaround: rip DVDs as usual; defer BD/UHD work until the next beta drops, then rebuild the ripper image so `install_makemkv.sh` picks up the new version.
- **`/home/arm` not writable** — only happens if the container runs with a `PUID` that doesn't own `/home/arm`. The shared entrypoint re-chowns on every boot, but if the directory is bind-mounted from a host with mismatched ownership, fix the host permissions.

## DVD vs BD: where the key matters

Useful asymmetry to remember while debugging:

| Disc type | Needs valid MakeMKV key? | Why |
| --- | --- | --- |
| DVD (CSS or unprotected) | No | CSS support is built into the OSS half of MakeMKV; no per-binary licensing gate. |
| BD (AACS) | Yes | AACS support is shipped in the closed-source `makemkv-bin` blob and gated by registration + binary validity. |
| UHD BD (AACS 2.0) | Yes | Same path; also requires a friendly UHD drive. |
| Audio CD | No | Doesn't touch makemkvcon at all; uses `abcde` + cdparanoia. |

If a fresh-host BD/UHD smoke fails with `MSG:5021` but DVD smokes pass on the same stack, the binary is expired and the only fix is upstream. If both DVD and BD fail, the key is wrong or `settings.conf` isn't being read — see the verify step above.

## What the install scripts do

- [services/ripper/install/install_makemkv.sh](../../services/ripper/install/install_makemkv.sh) — port of v2's `temp_install_makemkv.sh` (itself derived from tianon/dockerfiles). Scrapes the current MakeMKV version, fetches the GPG-signed `sha256sums.txt`, downloads `makemkv-oss` and `makemkv-bin` tarballs, verifies both, builds OSS, accepts the bin EULA, installs to `/usr/local`. Runs only in the build stage of the Dockerfile; the runtime image just copies the resulting binary and shared libraries.
- [services/ripper/install/update_key.sh](../../services/ripper/install/update_key.sh) — port of v2's `scripts/update_key.sh`. Idempotent. Run once per disc by the ripper's `JobController` via [`makemkv_key.py`](../../services/ripper/arm_ripper/makemkv_key.py) — the v3 port of v2's `prep_mkv`. (The shared entrypoint no longer invokes it; it only normalizes `/home/arm/.MakeMKV` ownership so the per-rip refresh can write there.)
